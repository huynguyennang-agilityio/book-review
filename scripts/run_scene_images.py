"""Chạy thật storyboard (Gemini) → sheet nhân vật → ảnh cảnh (Fal) cho sách golden.

    uv run python scripts/run_scene_images.py nha-gia-kim hoang-tu-be

Cần GOOGLE_API_KEY và FAL_KEY trong .env. Sheet đầu tiên của mỗi nhân vật được coi là đã duyệt.
Ảnh ghi vào `<MEDIA_DIR>/images/scenes/`; mỗi sách ra thêm `contact_<slug>.jpg` (lưới ảnh) để
chấm tay độ nhận ra nhân vật. In số ảnh, số lần gọi Fal và chi phí.
"""

import sys
from pathlib import Path
from typing import Any

from PIL import Image

from book_review_api.config import get_settings
from book_review_api.graph.nodes.characters import make_character_sheets_node, slugify
from book_review_api.graph.nodes.scene_images import make_scene_images_node
from book_review_api.graph.state import BookReviewState
from book_review_api.providers.image_fal import FalImageProvider
from book_review_api.providers.llm_gemini import make_chat_model, make_embeddings
from book_review_api.rag.golden import load_golden
from book_review_api.rag.memory import InMemoryRetriever
from book_review_api.storyboard.images import make_prompt_writer
from book_review_api.storyboard.runner import make_storyboard_runner

GOLDEN = Path(__file__).resolve().parent.parent / "evals" / "golden"
COLS = 6
THUMB = (180, 320)


def contact_sheet(media_dir: Path, paths: list[str], out: Path) -> None:
    rows = (len(paths) + COLS - 1) // COLS
    sheet = Image.new("RGB", (COLS * THUMB[0], rows * THUMB[1]), "white")
    for i, p in enumerate(paths):
        img = Image.open(media_dir / p).convert("RGB").resize(THUMB)
        sheet.paste(img, ((i % COLS) * THUMB[0], (i // COLS) * THUMB[1]))
    sheet.save(out, quality=88)


def main(slugs: list[str]) -> None:
    settings = get_settings()
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
