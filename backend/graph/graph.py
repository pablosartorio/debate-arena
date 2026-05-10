"""ConstrucciÃ³n del grafo LangGraph para el debate.

Etapa 1 â grafo minimo: ROUTER -> SPEAK -> (router | end). Sin scout, plan, moderate.
Las etapas siguientes agregaran nodos sin reescribir esta estructura base.
"""

import asyncio
from typing import Any

from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig

from graph.state import DebateState
from graph.nodes.intervene_node import intervene_node
from graph.nodes.moderate_node import moderate_node
from graph.nodes.plan_node import plan_node
from graph.nodes.router_node import router_node
from graph.nodes.scout_node import scout_node
from graph.nodes.speak_node import speak_node
from graph.nodes.summary_node import summary_node
from graph.edges import route_from_router, route_after_speak, route_after_moderate


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

    # plan -> speak -> moderate -> (router|summary)
    builder.add_edge("plan", "speak")

    builder.add_conditional_edges(
        "speak",
        route_after_speak,
        {"router": "moderate", "end": "summarize"},
    )

    # moderate decide si interviene o pasa al siguiente turno
    builder.add_conditional_edges(
        "moderate",
        route_after_moderate,
        {"intervene": "intervene", "router": "router"},
    )

    # intervene â siempre vuelve al router para el siguiente turno
    builder.add_edge("intervene", "router")

    # summary corre 1 sola vez al final, antes de cerrar el WS.
    builder.add_edge("summarize", "finalize")

    builder.add_edge("finalize", END)

    return builder.compile()
