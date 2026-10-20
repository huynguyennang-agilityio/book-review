"""Spike Ngày 1: so sánh model chỉnh ảnh tham chiếu trên Fal.

Cùng 1 ảnh nhân vật, cùng 4 prompt cảnh, chạy qua từng model.
Cần FAL_KEY trong môi trường và `pip install fal-client`.

    python spikes/media/fal_compare.py --ref spikes/media/ref/character.jpg

Ra: out/fal/<model>/<scene>.jpg, out/fal/results.json (thời gian, URL)
và out/fal/scores.csv (chấm tay: giống nhân vật, 9:16, lỗi, giá).

Lưu ý: ID endpoint và tên tham số đã kiểm tra ngày 2026-10-20; kiểm tra lại nếu lâu không chạy,
vì Fal đổi tên model khá thường xuyên.
"""

import argparse
import csv
import json
import pathlib
import time
import urllib.request

import fal_client

OUT = pathlib.Path(__file__).parent / "out" / "fal"

# Đã đối chiếu OpenAPI của Fal ngày 2026-10-20: Kontext nhận `aspect_ratio`,
# Qwen và Seedream nhận `image_size` (preset hoặc {width, height}).
MODELS = {
    "flux-kontext": {"endpoint": "fal-ai/flux-pro/kontext", "multi": False, "size": {"aspect_ratio": "9:16"}},
    "qwen-image-edit": {"endpoint": "fal-ai/qwen-image-edit", "multi": False, "size": {"image_size": {"width": 720, "height": 1280}}},
    # Seedream yêu cầu diện tích tối thiểu 921600 px.
    "seedream-edit": {"endpoint": "fal-ai/bytedance/seedream/v4/edit", "multi": True, "size": {"image_size": {"width": 1080, "height": 1920}}},
}

SCENES = {
    "scene1_kitchen": "the same character cooking in a bright kitchen, medium shot, warm light",
    "scene2_street": "the same character walking on a rainy city street at night, full body",
    "scene3_desk": "the same character reading a book at a wooden desk by the window",
    "scene4_outdoor": "the same character standing on a hill at sunrise, wind in the hair",
}


def build_args(model: dict, ref_url: str, prompt: str) -> dict:
    args = {"prompt": f"{prompt}, vertical 9:16 composition, keep the same face and outfit as the reference"}
    if model["multi"]:
        args["image_urls"] = [ref_url]
    else:
        args["image_url"] = ref_url
    args.update(model["size"])
    return args


def download(url: str, dest: pathlib.Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as r, dest.open("wb") as f:
        f.write(r.read())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="ảnh nhân vật tham chiếu (jpg/png)")
    ap.add_argument("--only", nargs="*", choices=list(MODELS), help="chỉ chạy một số model")
    ns = ap.parse_args()

    ref_url = fal_client.upload_file(ns.ref)
    results = []
    for name, cfg in MODELS.items():
        if ns.only and name not in ns.only:
            continue
        for scene, prompt in SCENES.items():
            t0 = time.time()
            res = fal_client.subscribe(cfg["endpoint"], arguments=build_args(cfg, ref_url, prompt))
            elapsed = round(time.time() - t0, 1)
            images = res.get("images") or [res.get("image")]
            url = images[0]["url"]
            dest = OUT / name / f"{scene}.jpg"
            download(url, dest)
            row = {"model": name, "scene": scene, "seconds": elapsed, "url": url, "file": str(dest)}
            results.append(row)
            print(row)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    with (OUT / "scores.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["model", "scene", "likeness_1to5", "ratio_9x16_ok", "artifacts", "seconds", "price_usd", "notes"])
        for r in results:
            w.writerow([r["model"], r["scene"], "", "", "", r["seconds"], "", ""])


if __name__ == "__main__":
    main()
