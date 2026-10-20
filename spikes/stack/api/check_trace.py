"""Kiểm tra trace LangSmith của một thread: đủ 2 node hello + ask_user chưa.

python check_trace.py <thread_id>
"""

import os
import sys

from dotenv import load_dotenv
from langsmith import Client

load_dotenv()


def main() -> None:
    thread_id = sys.argv[1]
    project = os.getenv("LANGSMITH_PROJECT", "book-review-local")
    client = Client()
    # LangSmith gom thread theo metadata thread_id (LangGraph tự gắn vào config).
    flt = f'and(eq(metadata_key, "thread_id"), eq(metadata_value, "{thread_id}"))'
    runs = list(client.list_runs(project_name=project, filter=flt))
    names = sorted({r.name for r in runs})
    print(f"{len(runs)} run trong project {project!r} cho thread {thread_id!r}: {names}")
    missing = {"hello", "ask_user"} - set(names)
    print("Thiếu node:", missing if missing else "không, đủ 2 node")


if __name__ == "__main__":
    main()
