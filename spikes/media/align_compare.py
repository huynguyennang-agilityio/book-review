"""Spike Ngày 1: so sánh word timing của forced alignment (stable-ts) với WordBoundary edge-tts.

Chạy sau tts_wordboundary.py, trong venv riêng vì cần torch:
    pip install stable-ts
    python spikes/media/align_compare.py [--model base]

Đọc out/tts/<voice>/<name>.mp3 và <name>.words.json, căn văn bản gốc trong samples/<name>.txt.
Ra: out/align/<voice>/<name>.aligned.json và out/align/summary.json
(lệch start giữa hai nguồn, theo từng cặp từ khớp nhau).
"""

import argparse
import difflib
import json
import pathlib
import re
import statistics

import stable_whisper

HERE = pathlib.Path(__file__).parent
TTS = HERE / "out" / "tts"
OUT = HERE / "out" / "align"


def normalize(token: str) -> str:
    return re.sub(r"[^\w]", "", token.lower())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="base", help="model whisper dùng để align")
    ns = ap.parse_args()

    model = stable_whisper.load_model(ns.model)
    summary = []
    for words_path in sorted(TTS.glob("*/*.words.json")):
        voice = words_path.parent.name
        name = words_path.name.removesuffix(".words.json")
        text = (HERE / "samples" / f"{name}.txt").read_text(encoding="utf-8").strip()
        result = model.align(str(words_path.with_name(f"{name}.mp3")), text, language="vi")
        aligned = [
            {"text": w.word.strip(), "start_ms": round(w.start * 1000), "end_ms": round(w.end * 1000)}
            for w in result.all_words()
        ]
        dest = OUT / voice / f"{name}.aligned.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(aligned, ensure_ascii=False, indent=2), encoding="utf-8")

        wb = json.loads(words_path.read_text(encoding="utf-8"))
        a_tok = [normalize(w["text"]) for w in aligned]
        b_tok = [normalize(w["text"]) for w in wb]
        matcher = difflib.SequenceMatcher(a=a_tok, b=b_tok, autojunk=False)
        diffs = []
        for blk in matcher.get_matching_blocks():
            for k in range(blk.size):
                diffs.append(abs(aligned[blk.a + k]["start_ms"] - wb[blk.b + k]["offset_ms"]))
        row = {
            "voice": voice,
            "sample": name,
            "aligned_words": len(aligned),
            "wordboundary_words": len(wb),
            "matched": len(diffs),
            "start_diff_mean_ms": round(statistics.mean(diffs)) if diffs else None,
            "start_diff_p90_ms": round(statistics.quantiles(diffs, n=10)[-1]) if len(diffs) > 1 else None,
            "start_diff_max_ms": round(max(diffs)) if diffs else None,
        }
        summary.append(row)
        print(row)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
