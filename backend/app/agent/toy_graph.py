"""Grafo de juguete de 3 nodos (T-300): demuestra invocacion real de LangGraph
con el checkpointer PostgreSQL (plan.md §1, §11). NO es el grafo real del
agente (T-303); solo emite un evento `step` por nodo para probar la
mecanica de durabilidad de punta a punta.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import TypedDict

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncEngine

from app.agent.durability import reserve_and_emit_event

NODES: tuple[str, ...] = ("node_a", "node_b", "node_c")


class ToyState(TypedDict):
    run_id: str
    steps_done: list[str]


def _make_node(
    engine: AsyncEngine, run_id: uuid.UUID, node_name: str
) -> Callable[[ToyState], Awaitable[ToyState]]:
    async def _node(state: ToyState) -> ToyState:
        step_number = len(state["steps_done"]) + 1
        display_message = (
            f"Ejecutando paso de demostracion {step_number}/{len(NODES)} ({node_name})."
        )
        await reserve_and_emit_event(
            engine,
            run_id,
            "step",
            {
                "step_number": step_number,
                "node": node_name,
                "display_message": display_message,
                "detail": None,
            },
        )
        return {"steps_done": [*state["steps_done"], node_name]}

    return _node


def build_toy_graph(engine: AsyncEngine, run_id: uuid.UUID, checkpointer: AsyncPostgresSaver):
    """Compila el grafo con `interrupt_after=NODES`: cada `ainvoke` avanza
    exactamente un nodo y persiste su checkpoint antes de retornar, lo que
    permite matar el proceso entre nodos sin perder el progreso ya
    confirmado (thread_id=run_id, plan.md §11)."""

    graph = StateGraph(ToyState)
    for name in NODES:
        graph.add_node(name, _make_node(engine, run_id, name))
    graph.set_entry_point(NODES[0])
    for current, following in zip(NODES, NODES[1:], strict=False):
        graph.add_edge(current, following)
    graph.add_edge(NODES[-1], END)
    return graph.compile(checkpointer=checkpointer, interrupt_after=list(NODES))
