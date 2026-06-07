"""Construcción del grafo LangGraph para el debate.

Etapa 1 — grafo minimo: ROUTER -> SPEAK -> (router | end). Sin scout, plan, moderate.
Las etapas siguientes agregaran nodos sin reescribir esta estructura base.
"""

import asyncio
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from graph.edges import route_after_moderate, route_after_speak, route_from_router
from graph.nodes.intervene_node import intervene_node
from graph.nodes.moderate_node import moderate_node
from graph.nodes.plan_node import plan_node
from graph.nodes.router_node import router_node
from graph.nodes.scout_node import scout_node
from graph.nodes.speak_node import speak_node
from graph.nodes.summary_node import summary_node
from graph.state import DebateState


async def _end_node(state: DebateState, config: RunnableConfig) -> dict[str, Any]:
    """Emite conversation_end al cerrar el debate."""
    configurable = config.get("configurable", {}) if config else {}
    ws_queue: asyncio.Queue | None = configurable.get("ws_queue")
    if ws_queue is not None:
        await ws_queue.put({"type": "node_active", "node": "finalize"})
        await ws_queue.put({"type": "conversation_end"})

    return {"debate_status": "ended"}


def build_graph():
    builder = StateGraph(DebateState)

    builder.add_node("scout", scout_node)
    builder.add_node("router", router_node)
    builder.add_node("plan", plan_node)
    builder.add_node("speak", speak_node)
    builder.add_node("moderate", moderate_node)
    builder.add_node("intervene", intervene_node)
    builder.add_node("summarize", summary_node)
    builder.add_node("finalize", _end_node)

    # scout corre 1 sola vez (idempotente: si scouting_done=True, no-op)
    builder.add_edge(START, "scout")
    builder.add_edge("scout", "router")

    # Al cerrar el debate (max turns o stop) pasamos por summary antes de finalize.
    builder.add_conditional_edges(
        "router",
        route_from_router,
        {"speak": "plan", "end": "summarize"},
    )

    # plan -> speak -> moderate -> (intervene | router | summary)
    builder.add_edge("plan", "speak")

    # speak siempre pasa por moderate (incluido el ultimo turno); el cierre por
    # turnos agotados lo decide route_after_moderate.
    builder.add_conditional_edges(
        "speak",
        route_after_speak,
        {"moderate": "moderate", "end": "summarize"},
    )

    # moderate decide si interviene, pasa al siguiente turno, o cierra el debate
    builder.add_conditional_edges(
        "moderate",
        route_after_moderate,
        {"intervene": "intervene", "router": "router", "end": "summarize"},
    )

    # intervene — siempre vuelve al router para el siguiente turno
    builder.add_edge("intervene", "router")

    # summary corre 1 sola vez al final, antes de cerrar el WS.
    builder.add_edge("summarize", "finalize")

    builder.add_edge("finalize", END)

    return builder.compile()
