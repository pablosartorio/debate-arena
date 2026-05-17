"""
PLAN_NODE: corre antes de cada SPEAK_NODE.

Cada agente arma su plan interno (estrategia + key_claims + rebuttal_target)
mediante una llamada LLM con format=json. El plan se guarda en
state["current_plan"] y lo lee SPEAK_NODE para inyectarlo como contexto
privado.

DegradaciÃ³n elegante:
  - Si planning falla o timeoutea, current_plan = None y el SPEAK corre sin plan.
  - Eventos WS: agent_planning {phase: "start"|"end"}. El plan en si NO se emite.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from langchain_core.runnables import RunnableConfig

import config as app_config
from agents.debater_agent import AgentPlanModel, plan_for_turn
from agents.personas import PERSONAS
from graph.state import DebateState

logger = logging.getLogger(__name__)


# Timeout especifico para planning (mas corto que SCOUTING porque corre por turno)
_PLAN_TIMEOUT = 45.0


def _last_texts(state: DebateState, agent_id: str) -> tuple[str | None, str | None]:
    """Devuelve (ultimo_turno_oponente, ultimo_turno_propio)."""
    turns = state.get("turns") or []
    last_opponent = None
    last_own = None
    # iteramos al reves para encontrar los mas recientes
    for t in reversed(turns):
        text = (t.get("response_text") or "").strip()
        if not text:
            continue
        if t.get("agent_id") == agent_id and last_own is None:
            last_own = text
        elif t.get("agent_id") != agent_id and last_opponent is None:
            last_opponent = text
        if last_opponent and last_own:
            break
    return last_opponent, last_own


async def plan_node(state: DebateState, config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable", {}) if config else {}
    ws_queue: asyncio.Queue | None = configurable.get("ws_queue")
    if ws_queue is not None:
        await ws_queue.put({"type": "node_active", "node": "plan"})
    stop_event: asyncio.Event | None = configurable.get("stop_event")

    if stop_event and stop_event.is_set():
        return {"current_plan": None}

    agent_id = state.get("current_agent_id")
    persona = PERSONAS.get(agent_id) if agent_id else None
    if not persona:
        return {"current_plan": None}

    turn_number = state.get("current_turn", 0) + 1
    is_first_turn = turn_number == 1
    last_opponent, last_own = _last_texts(state, agent_id)

    if ws_queue is not None:
        await ws_queue.put(
            {"type": "agent_planning", "agent": agent_id, "phase": "start", "turn": turn_number}
        )

    started = time.perf_counter()
    try:
        plan = await asyncio.wait_for(
            plan_for_turn(
                persona=persona,
                topic=state.get("topic", ""),
                last_opponent_text=last_opponent,
                own_previous_text=last_own,
                is_first_turn=is_first_turn,
                model=state.get("model"),
            ),
            timeout=_PLAN_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("plan timed out for agent=%s turn=%s", agent_id, turn_number)
        plan = AgentPlanModel.empty()
    except Exception:
        logger.exception("plan failed for agent=%s turn=%s", agent_id, turn_number)
        plan = AgentPlanModel.empty()

    latency_ms = int((time.perf_counter() - started) * 1000)
    plan_dict = plan.model_dump()

    if ws_queue is not None:
        await ws_queue.put(
            {
                "type": "agent_planning",
                "agent": agent_id,
                "phase": "end",
                "turn": turn_number,
                "latency_ms": latency_ms,
            }
        )

    return {
        "current_plan": plan_dict,
        "debate_status": "speaking",
    }
