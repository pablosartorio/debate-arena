"""ROUTER_NODE: decide cual es el proximo agente y emite turn_counter."""

import asyncio
from typing import Any

from langchain_core.runnables import RunnableConfig

from graph.state import DebateState


async def router_node(state: DebateState, config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable", {}) if config else {}
    ws_queue: asyncio.Queue | None = configurable.get("ws_queue")
    if ws_queue is not None:
        await ws_queue.put({"type": "node_active", "node": "router"})

    turn_order = state.get("turn_order") or [state.get("agent1_id"), state.get("agent2_id")]
    current_turn = state.get("current_turn", 0)
    next_agent_id = turn_order[current_turn % len(turn_order)]

    if ws_queue is not None:
        await ws_queue.put(
            {
                "type": "turn_counter",
                "current": current_turn,
                "max": state.get("max_turns", 0),
                "next_agent": next_agent_id,
            }
        )

    return {
        "current_agent_id": next_agent_id,
        "debate_status": "speaking",
    }
