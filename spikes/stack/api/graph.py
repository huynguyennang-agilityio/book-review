"""Graph hello 2 node: hello -> ask_user (interrupt), checkpoint trên Postgres."""

import os
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt


class State(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    book_title: str


def _greeting() -> str:
    # Có GOOGLE_API_KEY thì gọi Gemini để trace có 1 lần gọi LLM thật; không có thì trả câu cố định.
    if not os.getenv("GOOGLE_API_KEY"):
        return "Xin chào! Mình là trợ lý review sách."
    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"))
    reply = llm.invoke("Chào người dùng bằng một câu tiếng Việt ngắn, bạn là trợ lý review sách.")
    return str(reply.content)


def hello(state: State) -> State:
    return {"messages": [AIMessage(content=_greeting())]}


def ask_user(state: State) -> State:
    answer = interrupt({"message": "Bạn muốn review cuốn sách nào?"})
    title = str(answer).strip()
    return {
        "book_title": title,
        "messages": [
            HumanMessage(content=title),
            AIMessage(content=f"Đã nhận: «{title}». Hẹn gặp lại ở ngày 3!"),
        ],
    }


def build_graph(checkpointer):  # type: ignore[no-untyped-def]
    builder = StateGraph(State)
    builder.add_node("hello", hello)
    builder.add_node("ask_user", ask_user)
    builder.add_edge(START, "hello")
    builder.add_edge("hello", "ask_user")
    builder.add_edge("ask_user", END)
    return builder.compile(checkpointer=checkpointer)
