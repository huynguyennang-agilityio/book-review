"""Chạy thật storyboard (Gemini) → sheet nhân vật → ảnh cảnh (Fal) cho sách golden.

    uv run python scripts/run_scene_images.py nha-gia-kim hoang-tu-be

Chế độ manual (không gọi Fal, không cần FAL_KEY): nạp ảnh từ thư mục, gán theo thứ tự prompt
(nhân vật trước, rồi ảnh cảnh), qua node `manual_images` như web. `--make-samples` tự tạo ảnh mẫu
9:16 vào thư mục nếu còn thiếu. Ghi storyboard kèm đường dẫn ảnh ra `images/storyboard_<slug>.json`
để `run_media.py` dựng video.

    uv run python scripts/run_scene_images.py --manual-dir var/manual --make-samples nha-gia-kim

Cần GOOGLE_API_KEY và FAL_KEY trong .env (FAL_KEY chỉ cho chế độ auto).
Sheet đầu tiên của mỗi nhân vật được coi là đã duyệt.
Ảnh ghi vào `<MEDIA_DIR>/images/scenes/`; mỗi sách ra thêm `contact_<slug>.jpg` (lưới ảnh) để
chấm tay độ nhận ra nhân vật. In số ảnh, số lần gọi Fal và chi phí.
"""

import json
import sys
import uuid
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from PIL import Image, ImageDraw

from book_review_api.config import get_settings
from book_review_api.graph.nodes.characters import make_character_sheets_node, slugify
from book_review_api.graph.nodes.manual_images import make_manual_images_node
from book_review_api.graph.nodes.scene_images import make_scene_images_node
from book_review_api.graph.state import BookReviewState
from book_review_api.providers.image_fal import FalImageProvider
from book_review_api.providers.llm_gemini import make_chat_model, make_embeddings
from book_review_api.rag.golden import load_golden
from book_review_api.rag.memory import InMemoryRetriever
from book_review_api.storyboard.images import make_prompt_writer
from book_review_api.storyboard.runner import make_storyboard_runner
from book_review_api.uploads import process_image, upload_dir, upload_rel_path

GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "golden"
COLS = 6
THUMB = (180, 320)
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def contact_sheet(media_dir: Path, paths: list[str], out: Path) -> None:
    rows = (len(paths) + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * THUMB[0], rows * THUMB[1]), "white")
    for i, p in enumerate(paths):
        img = Image.open(media_dir / p).convert("RGB").resize(THUMB)
        sheet.paste(img, ((i % COLS) * THUMB[0], (i // COLS) * THUMB[1]))
    sheet.save(out, quality=88)


def make_samples(directory: Path, count: int) -> None:
    """Ảnh mẫu 9:16, mỗi ảnh một màu và số thứ tự, để chạy thử không cần ảnh thật."""
    directory.mkdir(parents=True, exist_ok=True)
    have = len([p for p in directory.iterdir() if p.suffix.lower() in IMAGE_EXT])
    for i in range(have, count):
        hue = (i * 47) % 255
        img = Image.new("RGB", (720, 1280), (hue, 255 - hue, (i * 90) % 255))
        ImageDraw.Draw(img).text((340, 620), f"{i + 1:03d}", fill="white")
        img.save(directory / f"{i + 1:03d}.png")


def run_manual(book_state: BookReviewState, settings: Any, directory: Path, samples: bool) -> dict:
    """Chạy node manual_images qua một graph nhỏ, giống web: lấy prompt, tải ảnh, resume."""
    graph = StateGraph(BookReviewState)
    graph.add_node("manual_images", make_manual_images_node(settings))
    graph.add_edge(START, "manual_images")
    graph.add_edge("manual_images", END)
    app = graph.compile(checkpointer=InMemorySaver())
    project = uuid.uuid4()
    cfg: Any = {"configurable": {"thread_id": str(project), "project_id": str(project)}}
    app.invoke(book_state, cfg)
    payload = app.get_state(cfg).interrupts[0].value
    required: list[str] = payload["required"]
    if samples:
        make_samples(directory, len(required))
    files = sorted(p for p in directory.iterdir() if p.suffix.lower() in IMAGE_EXT)
    if len(files) < len(required):
        sys.exit(f"Cần {len(required)} ảnh trong {directory}, mới có {len(files)}")
    dest = upload_dir(settings.media_dir, project)
    dest.mkdir(parents=True, exist_ok=True)
    uploads: dict[str, str] = {}
    for key, f in zip(required, files, strict=False):
        done = process_image(f.read_bytes())
        (dest / done.name).write_bytes(done.data)
        uploads[key] = upload_rel_path(project, done.name)
    print(f"manual: {len(payload['characters'])} nhân vật + {len(payload['scenes'])} ảnh cảnh")
    out = app.invoke(Command(resume={"uploads": uploads}), cfg)
    return dict(out)


def run_book_manual(book: Any, settings: Any, directory: Path, samples: bool) -> None:
    media_dir = Path(settings.media_dir)
    model, embeddings = make_chat_model(settings), make_embeddings(settings)
    runner = make_storyboard_runner(
        model, InMemoryRetriever(book.chunks(), embeddings), settings, spoiler_free=True
    )
    out = runner(
        {
            "book": {"title": book.title, "author": book.author, "year": book.year},
            "kind": book.kind,
        }
    )
    if "storyboard" not in out:
        print("storyboard thất bại:", out.get("error_code"))
        return
    state: BookReviewState = {
        "book": {"title": book.title},
        "storyboard": out["storyboard"],
        "cost": out.get("cost", {}),
    }
    res = run_manual(state, settings, directory, samples)
    if res.get("status") == "failed":
        print("manual thất bại:", res.get("error_code"))
        return
    refs = res.get("asset_refs", {})
    print("ảnh cảnh:", sum(k.startswith("image:") for k in refs), "| chi phí ảnh:", res["cost"])
    target = media_dir / "images" / f"storyboard_{slugify(book.slug)}.json"
    target.write_text(json.dumps(res["storyboard"], ensure_ascii=False), encoding="utf-8")
    print("storyboard:", target.resolve())


def main(args: list[str]) -> None:
    settings = get_settings()
    samples = "--make-samples" in args
    manual_dir = None
    if "--manual-dir" in args:
        manual_dir = Path(args[args.index("--manual-dir") + 1])
    slugs = [
        a
        for i, a in enumerate(args)
        if not a.startswith("--") and (i == 0 or args[i - 1] != "--manual-dir")
    ]
    if manual_dir:
        for book in (b for b in load_golden(GOLDEN) if not slugs or b.slug in slugs):
            print(f"\n=== {book.title} (manual)")
            run_book_manual(book, settings, manual_dir, samples)
        return
    if not settings.fal_key:
        sys.exit("Thiếu FAL_KEY")
    media_dir = Path(settings.media_dir)
    model, embeddings = make_chat_model(settings), make_embeddings(settings)
    provider = FalImageProvider(settings.fal_key, concurrency=settings.fal_concurrency)
    sheets = make_character_sheets_node(provider, settings, approved_lookup=lambda s, n: None)
    scenes = make_scene_images_node(provider, settings, prompt_writer=make_prompt_writer(model))
    total = 0.0
    for book in (b for b in load_golden(GOLDEN) if not slugs or b.slug in slugs):
        print(f"\n=== {book.title}")
        runner = make_storyboard_runner(
            model, InMemoryRetriever(book.chunks(), embeddings), settings, spoiler_free=True
        )
        out = runner(
            {
                "book": {"title": book.title, "author": book.author, "year": book.year},
                "kind": book.kind,
            }
        )
        if "storyboard" not in out:
            print("storyboard thất bại:", out.get("error_code"))
            continue
        state: BookReviewState = {"storyboard": out["storyboard"], "cost": out.get("cost", {})}
        res: dict[str, Any] = sheets(state)
        approved = {
            slug: {"name": c["name"], "sheet_path": c["images"][0]}
            for slug, c in res.get("character_candidates", {}).items()
            if c["images"]
        }
        cost = res.get("cost", {}).get("usd", 0.0)
        print("nhân vật:", {k: v["name"] for k, v in approved.items()}, "chi phí sheet:", cost)
        state = {**state, "characters_approved": approved}
        res = scenes(state)
        refs = res.get("asset_refs", {})
        print(
            "ảnh cảnh:",
            len(refs),
            "| trạng thái:",
            res.get("status", "ok"),
            res.get("error_code", ""),
        )
        print("chi phí ảnh cảnh:", res.get("cost"))
        cost += res.get("cost", {}).get("usd", 0.0)
        for scene in (res.get("storyboard") or {}).get("scenes", []):
            for k, im in enumerate(scene["images"]):
                print(f"  cảnh {scene['id']}.{k} [{scene['scene_type']}] {im['prompt_en'][:90]}")
        order = sorted(refs, key=lambda k: tuple(int(x) for x in k.split(":")[1:]))
        contact = media_dir / "images" / f"contact_{slugify(book.slug)}.jpg"
        contact_sheet(media_dir, [refs[k] for k in order], contact)
        for slug, v in approved.items():
            print(f"  sheet {slug}: {(media_dir / v['sheet_path']).resolve()}")
        print("contact sheet:", contact.resolve())
        total += cost
    print(f"\nTổng chi phí ảnh: {total:.2f} USD")


if __name__ == "__main__":
    main(sys.argv[1:])
