"""Gọi thật endpoint AG-UI `/agent` như web: tạo project, chạy graph, in event tiến độ.

    export DATABASE_URL=... SUPABASE_JWT_SECRET=dev-secret-...
    uv run uvicorn book_review_api.main:app --port 8001
    uv run python scripts/run_agent.py "Nhà giả kim" [--api http://localhost:8001] [--pick 0]

Script tự thêm một người dùng thử vào `auth.users` của DB local rồi ký JWT HS256 bằng
`SUPABASE_JWT_SECRET` (chỉ dùng với Postgres local, không dùng với Supabase thật).
Nếu graph dừng ở `identify_confirm` thì chọn ứng viên `--pick` và chạy tiếp (resume).

Tab "Từ bài review có sẵn": `--review evals/review-text/nha-gia-kim.md` gửi bài (`.md` có
`## Hook` / `## Ý chính` / `## Nhận xét` thì tách 3 ô) thay cho research.
"""

import argparse
import json
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import jwt
import psycopg
from run_review_text import split_fields

from book_review_api.config import get_settings
from book_review_api.graph.build import NODES

GRAPH_NODES = set(NODES)


def event_lines(resp: httpx.Response) -> list[dict[str, Any]]:
    return [json.loads(line[5:]) for line in resp.iter_lines() if line.startswith("data:")]


def run(
    client: httpx.Client, headers: dict[str, str], body: dict[str, Any]
) -> list[dict[str, Any]]:
    with client.stream("POST", "/agent", json=body, headers=headers, timeout=600) as resp:
        resp.raise_for_status()
        events = event_lines(resp)
    for e in events:
        t = e["type"]
        if t == "STEP_STARTED":
            if e["stepName"] in GRAPH_NODES:
                print(f"  → {e['stepName']}")
        elif t == "CUSTOM":
            v = e.get("value")
            v = json.loads(v) if isinstance(v, str) and v.startswith("{") else v
            detail = f"{v.get('type')} {v.get('url', '')}" if isinstance(v, dict) else v
            print(f"  · {e['name']}: {detail}")
        elif t == "RUN_ERROR":
            print("  ! RUN_ERROR", e.get("message"))
    return events


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("title")
    parser.add_argument("--api", default="http://localhost:8001")
    parser.add_argument("--pick", type=int, default=0)
    parser.add_argument(
        "--approve", action="store_true", help="tự duyệt kịch bản (review_script) để dựng video"
    )
    parser.add_argument("--review", type=Path, help="file bài review (.txt/.md) cho tab review")
    parser.add_argument(
        "--print-token", action="store_true", help="chỉ in user_id và JWT thử (để dán vào web)"
    )
    args = parser.parse_args()
    settings = get_settings()
    user_id = str(uuid.uuid4())
    with psycopg.connect(settings.database_url, autocommit=True) as conn:
        conn.execute(
            "insert into auth.users (id, email) values (%s, %s)", [user_id, f"{user_id}@dev.local"]
        )
    claims = {
        "sub": user_id,
        "aud": "authenticated",
        "role": "authenticated",
        "exp": int(time.time()) + 3600,
        "iss": settings.supabase_issuer if settings.supabase_url else None,
    }
    token = jwt.encode(
        {k: v for k, v in claims.items() if v is not None},
        settings.supabase_jwt_secret,
        algorithm="HS256",
    )
    if args.print_token:
        print(json.dumps({"user_id": user_id, "email": f"{user_id}@dev.local", "token": token}))
        return
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=args.api) as client:
        state: dict[str, Any] = {"book": {"title": args.title}}
        source = "book"
        if args.review:
            source = "user_review"
            state["options"] = {"source": source}
            state["user_review"] = split_fields(args.review.read_text(encoding="utf-8"))
        project = client.post(
            "/projects", json={"book_title": args.title, "source": source}, headers=headers
        ).json()
        print("project:", project["id"], project["status"], project.get("source"))
        base = {
            "threadId": project["thread_id"],
            "runId": str(uuid.uuid4()),
            "state": state,
            "messages": [{"id": "m1", "role": "user", "content": args.title}],
            "tools": [],
            "context": [],
            "forwardedProps": {},
        }
        events = run(client, headers, base)
        while (outcome := events[-1].get("outcome")) and outcome["type"] == "interrupt":
            interrupt = outcome["interrupts"][0]
            payload = interrupt.get("payload") or interrupt
            print("interrupt:", json.dumps(payload, ensure_ascii=False)[:600])
            raw = payload.get("metadata", {}).get("langgraph", {}).get("raw", payload)
            kind = raw.get("type")
            if kind == "identify_confirm":
                answer: dict[str, Any] = {"index": args.pick}
            elif kind == "review_script" and args.approve:
                answer = {"approved": True}
            elif kind == "choose_image_mode" and args.approve:
                answer = {"mode": "auto"}
            elif kind == "review_characters" and args.approve:
                answer = {"selections": {slug: 0 for slug in raw.get("characters", {})}}
            else:
                break
            resume = [{"interruptId": interrupt["id"], "status": "resolved", "payload": answer}]
            events = run(
                client,
                headers,
                {**base, "runId": str(uuid.uuid4()), "messages": [], "resume": resume},
            )
        final = client.get(f"/projects/{project['id']}", headers=headers).json()
        print("status:", final["status"])


if __name__ == "__main__":
    main()
