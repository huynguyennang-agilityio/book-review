"""Bọc adapter LangGraph <-> AG-UI trong một chỗ để sau này dễ thay thư viện."""

from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint
from fastapi import FastAPI
from langgraph.graph.state import CompiledStateGraph


def mount_agent(app: FastAPI, graph: CompiledStateGraph, *, name: str, path: str) -> None:
    agent = LangGraphAgent(
        name=name,
        graph=graph,
        description="Spike ngày 2",
        # Kết thúc run bằng RUN_FINISHED outcome=interrupt để client resume qua
        # RunAgentInput.resume[] (forwardedProps.command.resume đã deprecated).
        emit_interrupt_outcome=True,
    )
    add_langgraph_fastapi_endpoint(app, agent, path)
