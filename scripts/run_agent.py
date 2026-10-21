"""Gọi thật endpoint AG-UI `/agent` như web: tạo project, chạy graph, in event tiến độ.

    export DATABASE_URL=... SUPABASE_JWT_SECRET=dev-secret-...
    uv run uvicorn book_review_api.main:app --port 8001
    uv run python scripts/run_agent.py "Nhà giả kim" [--api http://localhost:8001] [--pick 0]

Script tự thêm một người dùng thử vào `auth.users` của DB local rồi ký JWT HS256 bằng
`SUPABASE_JWT_SECRET` (chỉ dùng với Postgres local, không dùng với Supabase thật).
Nếu graph dừng ở `identify_confirm` thì chọn ứng viên `--pick` và chạy tiếp (resume).
"""

import argparse
import json
import time
import uuid
from typing import Any

import httpx
import jwt
import psycopg

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
        project = client.post("/projects", json={"book_title": args.title}, headers=headers).json()
        print("project:", project["id"], project["status"])
        base = {
            "threadId": project["thread_id"],
            "runId": str(uuid.uuid4()),
            "state": {"book": {"title": args.title}},
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
            if payload.get("type") != "identify_confirm":
                break
            resume = [
                {
                    "interruptId": interrupt["id"],
                    "status": "resolved",
                    "payload": {"index": args.pick},
                }
            ]
            events = run(
                client,
                headers,
                {**base, "runId": str(uuid.uuid4()), "messages": [], "resume": resume},
            )
        final = client.get(f"/projects/{project['id']}", headers=headers).json()
        print("status:", final["status"])


if __name__ == "__main__":
    main()
