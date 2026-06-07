"""
MODERATE_NODE: corre despues de cada SPEAK_NODE.

Evaluá el ultimo turno con el ModeratorAgent (8 dimensiones + flag de intervencion),
calcula el score total ponderado, actualiza cumulative_scores y persiste.

Etapa 6: si el moderador detecta que se necesita intervencion, solo emitimos
un evento `warning` — la intervencion como tercer hablante llega en Etapa 7.

Degradación elegante: si el moderador falla/timeoutea, se usa un score neutro
(todas las dimensiones en 0.5 — total ~0.55) y el debate continua sin warning.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig

import config as app_config
from agents.moderator_agent import ModeratorAgent, ModeratorEvaluation
from graph.state import DebateState, ModeratorIntervention

logger = logging.getLogger(__name__)


_MODERATE_TIMEOUT = 90.0


def _decide_intervention(
    evaluation: ModeratorEvaluation,
    score: dict,
) -> tuple[bool, str, str]:
    """
    Combina la decision del LLM con los thresholds del config.
    Returns (needed, reason, severity). Si LLM y thresholds disienten,
    los thresholds tienen prioridad por ser deterministicos.
    """
    thresholds = app_config.MODERATION_THRESHOLDS

    # 1. thresholds duros — disparan siempre
    if score.get("hallucination_risk", 0.0) > thresholds.get("hallucination_risk", 1.1):
        return True, "hallucination", "correction"
    if score.get("repetition_penalty", 0.0) > thresholds.get("repetition_penalty", 1.1):
        return True, "repetition", "warning"
    if score.get("consign_compliance", 1.0) < thresholds.get("consign_compliance", -0.1):
        return True, "off_topic", "redirect"
    if score.get("role_adherence", 1.0) < thresholds.get("role_adherence", -0.1):
        return True, "role_break", "warning"

    # 2. fallback: lo que diga el LLM
    if evaluation.intervention_needed and evaluation.intervention_severity:
        return (
            True,
            evaluation.intervention_reason or "moderation",
            evaluation.intervention_severity,
        )

    return False, "", ""


def _own_history_summary(state: DebateState, agent_id: str, exclude_turn_id: str) -> str | None:
    """Resume los turnos previos del mismo agente (sin contar el que se evalua)."""
    turns = state.get("turns") or []
    own_texts = [
        (t.get("response_text") or "").strip()
        for t in turns
        if t.get("agent_id") == agent_id and t.get("turn_id") != exclude_turn_id
    ]
    own_texts = [t for t in own_texts if t]
    if not own_texts:
        return None
    # ultimos 2 turnos como referencia para deteccion de repeticion
    snippets = own_texts[-2:]
    return "\n".join(f'- "{s}"' for s in snippets)


def _last_opponent_text(state: DebateState, agent_id: str) -> str | None:
    turns = state.get("turns") or []
    for t in reversed(turns):
        if t.get("agent_id") != agent_id:
            return (t.get("response_text") or "").strip() or None
    return None


async def moderate_node(state: DebateState, config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable", {}) if config else {}
    ws_queue: asyncio.Queue | None = configurable.get("ws_queue")
    if ws_queue is not None:
        await ws_queue.put({"type": "node_active", "node": "moderate"})
    stop_event: asyncio.Event | None = configurable.get("stop_event")
    repo = configurable.get("repo")
    debate_id = configurable.get("debate_id") or state.get("debate_id")

    if not state.get("enable_moderation"):
        return {}

    if stop_event and stop_event.is_set():
        return {}

    turns = state.get("turns") or []
    if not turns:
        return {}

    last_turn = turns[-1]
    turn_id = last_turn.get("turn_id")
    turn_number = last_turn.get("turn_number")
    agent_id = last_turn.get("agent_id")
    turn_text = (last_turn.get("response_text") or "").strip()

    if not (turn_id and turn_text):
        return {}

    scout_result = state.get("scout_result") or {}
    evaluation_criteria = scout_result.get("evaluation_criteria") or []

    moderator = ModeratorAgent(model=state.get("model"))
    started = time.perf_counter()

    # avisar al frontend que la evaluacion arranco (UX: badge "evaluando...")
    if ws_queue is not None:
        await ws_queue.put(
            {
                "type": "moderator_evaluating",
                "agent": agent_id,
                "turn": turn_number,
                "phase": "start",
            }
        )

    try:
        evaluation = await asyncio.wait_for(
            moderator.evaluate(
                topic=state.get("topic", ""),
                agent_id=agent_id,
                turn_text=turn_text,
                previous_opponent_text=_last_opponent_text(state, agent_id),
                own_history_summary=_own_history_summary(state, agent_id, turn_id),
                evaluation_criteria=evaluation_criteria,
            ),
            timeout=_MODERATE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("moderator timed out for turn %s", turn_number)
        evaluation = ModeratorEvaluation.neutral()
    except Exception:
        logger.exception("moderator failed for turn %s", turn_number)
        evaluation = ModeratorEvaluation.neutral()

    latency_ms = int((time.perf_counter() - started) * 1000)
    score_dict = evaluation.to_score_dict()
    total = score_dict["total"]

    # actualizar cumulative_scores
    cumulative = dict(state.get("cumulative_scores") or {})
    cumulative[agent_id] = round(cumulative.get(agent_id, 0.0) + total, 4)

    if ws_queue is not None:
        await ws_queue.put(
            {
                "type": "moderator_evaluation",
                "agent": agent_id,
                "turn": turn_number,
                "score": score_dict,
                "latency_ms": latency_ms,
            }
        )
        await ws_queue.put(
            {
                "type": "score_update",
                "scores": {
                    aid: round(s, 4) for aid, s in cumulative.items()
                },
            }
        )

    if repo is not None and debate_id:
        try:
            await repo.save_evaluation(
                evaluation_id=str(uuid.uuid4()),
                turn_id=turn_id,
                debate_id=debate_id,
                score=score_dict,
            )
        except Exception:
            logger.exception("failed to persist evaluation for turn %s", turn_number)

    # decidir intervencion combinando LLM + thresholds
    needs_intervention, reason, severity = _decide_intervention(evaluation, score_dict)

    pending: ModeratorIntervention | None = None
    if needs_intervention:
        pending = {
            "turn_number": turn_number,
            "affected_agent": agent_id,
            "reason": reason,
            "severity": severity,
            "message": (evaluation.notes or "").strip(),
        }
        if ws_queue is not None:
            await ws_queue.put(
                {
                    "type": "moderator_intervention_pending",
                    "agent": agent_id,
                    "turn": turn_number,
                    "reason": reason,
                    "severity": severity,
                }
            )

    # NOTA: el reducer de `turns` es _append, asi que no podemos "actualizar" el ultimo
    # turno via return. La evaluacion va solo a la tabla `evaluations`.
    return {
        "cumulative_scores": cumulative,
        "pending_intervention": pending,
        "debate_status": "routing",
    }
