"""Thử resume không qua HTTP: chạy tới interrupt, thoát process, chạy lại với cùng thread_id.

python resume_cli.py start <thread_id>
python resume_cli.py resume <thread_id> "Nhà giả kim"
"""

import os
import sys

from dotenv import load_dotenv
from graph import build_graph
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command

load_dotenv()
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/book_review"
)


def main() -> None:
    mode, thread_id = sys.argv[1], sys.argv[2]
    config = {"configurable": {"thread_id": thread_id}}
    with PostgresSaver.from_conn_string(DATABASE_URL) as saver:
        saver.setup()
        graph = build_graph(saver)
        if mode == "start":
            result = graph.invoke({"messages": []}, config)
            print("interrupt:", result.get("__interrupt__"))
        else:
            result = graph.invoke(Command(resume=sys.argv[3]), config)
            print("book_title:", result["book_title"])
            print("last message:", result["messages"][-1].content)
        print("next:", graph.get_state(config).next)


if __name__ == "__main__":
    main()
