"""
INTERVENE_NODE: el moderador habla cuando detecta un problema.

Se ejecuta solo si state["pending_intervention"] esta set, lo cual ocurre
cuando moderate_node combino el flag del LLM con los thresholds del config.

Flujo:
  1. Emite turn_start con agent="moderator" (reusa la pipeline visual)
  2. Streamea tokens via ModeratorAgent.speak_intervention()
  3. Persiste la intervencion completa en `interventions`
  4. Limpia pending_intervention para que el siguiente turno corra normal

DegradaciÃ³n elegante: si el speak_intervention falla/timeoutea, persistimos
el mensaje original (notes del LLM) y el debate continua.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig

from agents.moderator_agent import ModeratorAgent
from graph.state import DebateState

logger = logging.getLogger(__name__)


_INTERVENE_TIMEOUT = 60.0


async def intervene_node(state: DebateState, config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable", {}) if config else {}
    ws_queue: asyncio.Queue | None = configurable.get("ws_queue")
    stop_event: asyncio.Event | None = configurable.get("stop_event")
    repo = configurable.get("repo")
    debate_id = configurable.get("debate_id") or state.get("debate_id")

    pending = state.get("pending_intervention")
    if not pending:
        return {}

    if stop_event and stop_event.is_set():
        return {"pending_intervention": None}

    affected_agent = pending.get("affected_agent") or ""
    turn_number = pending.get("turn_number") or state.get("current_turn", 0)
    reason = pending.get("reason") or "moderation"
    severity = pending.get("severity") or "warning"
    fallback_message = pending.get("message") or ""

    # ultimo turno del agente afectado para darle contexto al moderador
    turns = state.get("turns") or []
    last_turn_text = ""
    for t in reversed(turns):
        if t.get("agent_id") == affected_agent:
            last_turn_text = (t.get("response_text") or "").strip()
            break

    if ws_queue is not None:
        await ws_queue.put(
            {
                "type": "moderator_intervention",
                "phase": "start",
                "severity": severity,
                "reason": reason,
                "agent": affected_agent,
                "turn": turn_number,
            }
        )
        # reusamos la pipeline visual de turn_start/token/turn_end
        await ws_queue.put({"type": "turn_start", "agent": "moderator"})

    moderator = ModeratorAgent(model=state.get("model"))
    started = time.perf_counter()
    full_message = ""
    stopped_mid = False

    async def _run_stream():
        nonlocal full_message, stopped_mid
        async for token in moderator.speak_intervention(
            topic=state.get("topic", ""),
            agent_id=affected_agent,
            turn_text=last_turn_text,
            reason=reason,
            severity=severity,
        ):
            if stop_event and stop_event.is_set():
                stopped_mid = True
                return
            full_message += token
            if ws_queue is not None:
                await ws_queue.put({"type": "token", "agent": "moderator", "content": token})

    try:
        await asyncio.wait_for(_run_stream(), timeout=_INTERVENE_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("intervention stream timed out for turn %s", turn_number)
    except Exception:
        logger.exception("intervention failed for turn %s", turn_number)

    latency_ms = int((time.perf_counter() - started) * 1000)
    final_text = (full_message or fallback_message or "El moderador detecto un problema en el ultimo turno.").strip()

    if ws_queue is not None:
        await ws_queue.put({"type": "turn_end", "agent": "moderator"})
        await ws_queue.put(
            {
                "type": "moderator_intervention",
                "phase": "end",
                "severity": severity,
                "reason": reason,
                "agent": affected_agent,
                "turn": turn_number,
                "message": final_text,
                "latency_ms": latency_ms,
            }
        )

    if repo is not None and debate_id:
        try:
            await repo.save_intervention(
                intervention_id=str(uuid.uuid4()),
                debate_id=debate_id,
                turn_number=turn_number,
                reason=reason,
                message=final_text,
                severity=severity,
            )
        except Exception:
            logger.exception("failed to persist intervention for turn %s", turn_number)

    update: dict[str, Any] = {
        "interventions": [
            {
                "turn_number": turn_number,
                "affected_agent": affected_agent,
                "reason": reason,
                "severity": severity,
                "message": final_text,
            }
        ],
        "pending_intervention": None,
        "debate_status": "routing",
    }

    if stopped_mid:
        update["stop_requested"] = True

    return update
