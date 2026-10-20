"""Spike Ngày 1: kiểm tra WordBoundary của edge-tts với 2 giọng vi-VN.

Chạy (cần mạng tới speech.platform.bing.com):
    pip install edge-tts
    python spikes/media/tts_wordboundary.py spikes/media/samples/*.txt

Ra: out/tts/<voice>/<name>.mp3, <name>.words.json, và out/tts/summary.json.
In ra: số từ mất so với văn bản gốc, và độ lệch giữa offset cuối và thời lượng ffprobe.
"""

import asyncio
import difflib
import json
import pathlib
import re
import subprocess
import sys

import edge_tts

VOICES = ["vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural"]
OUT = pathlib.Path(__file__).parent / "out" / "tts"


def normalize(token: str) -> str:
    # Bỏ dấu câu, giữ nguyên dấu tiếng Việt để kiểm tra đúng chữ có dấu.
    return re.sub(r"[^\w]", "", token.lower())


async def synth(text: str, voice: str, mp3_path: pathlib.Path) -> list[dict]:
    comm = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    words: list[dict] = []
    with mp3_path.open("wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                # edge-tts trả offset/duration theo đơn vị 100ns, đổi sang ms.
                words.append(
                    {
                        "text": chunk["text"],
                        "offset_ms": chunk["offset"] / 10_000,
                        "duration_ms": chunk["duration"] / 10_000,
                    }
                )
    return words


def probe_ms(path: pathlib.Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(out) * 1000


def missing_words(source: str, returned: list[dict]) -> list[str]:
    src = [normalize(t) for t in source.split() if normalize(t)]
    got = [normalize(w["text"]) for w in returned if normalize(w["text"])]
    matcher = difflib.SequenceMatcher(a=src, b=got, autojunk=False)
    missing = []
    for tag, i1, i2, _, _ in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            missing.extend(src[i1:i2])
    return missing


async def main(paths: list[str]) -> None:
    summary = []
    for voice in VOICES:
        (OUT / voice).mkdir(parents=True, exist_ok=True)
        for p in paths:
            src = pathlib.Path(p)
            text = src.read_text(encoding="utf-8").strip()
            mp3 = OUT / voice / f"{src.stem}.mp3"
            words = await synth(text, voice, mp3)
            (OUT / voice / f"{src.stem}.words.json").write_text(
                json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            duration = probe_ms(mp3)
            last_end = words[-1]["offset_ms"] + words[-1]["duration_ms"] if words else 0.0
            missing = missing_words(text, words)
            row = {
                "voice": voice,
                "sample": src.name,
                "words_returned": len(words),
                "words_missing": missing,
                "ffprobe_ms": round(duration),
                "last_word_end_ms": round(last_end),
                "drift_ms": round(duration - last_end),
            }
            summary.append(row)
            print(row)
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Cách dùng: python tts_wordboundary.py <file.txt> [...]")
    asyncio.run(main(sys.argv[1:]))
