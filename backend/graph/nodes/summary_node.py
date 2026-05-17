"""
SUMMARY_NODE: corre 1 sola vez al cierre del debate, antes de FINALIZE.

Tareas:
  1. Determinar ganador por cumulative_scores (deterministic).
  2. Pedir narrativa al LLM (highlights/weaknesses/key_moments).
  3. Persistir en debates.summary y debates.winner_id.
  4. Emitir `debate_summary` event con todo el payload.

DegradaciÃ³n elegante: si el LLM falla, el winner sigue siendo determinable
y emitimos un summary minimo.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from agents.summary_agent import SummaryAgent, DebateSummaryModel, determine_winner
from graph.state import DebateState

logger = logging.getLogger(__name__)


_SUMMARY_TIMEOUT = 90.0


async def summary_node(state: DebateState, config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable", {}) if config else {}
    ws_queue: asyncio.Queue | None = configurable.get("ws_queue")
    if ws_queue is not None:
        await ws_queue.put({"type": "node_active", "node": "summarize"})
    repo = configurable.get("repo")
    debate_id = configurable.get("debate_id") or state.get("debate_id")

    turns = state.get("turns") or []
    cumulative = state.get("cumulative_scores") or {}
    agent_ids = state.get("turn_order") or [
        state.get("agent1_id"), state.get("agent2_id"),
    ]
    agent_ids = [a for a in agent_ids if a]
    topic = state.get("topic", "")

    winner_id, verdict = determine_winner(cumulative, agent_ids)

    if ws_queue is not None:
        await ws_queue.put({"type": "summary_start"})

    started = time.perf_counter()
    summarizer = SummaryAgent(model=state.get("model"))

    try:
        summary_model = await asyncio.wait_for(
            summarizer.summarize(
                topic=topic,
                turns=turns,
                cumulative_scores=cumulative,
                agent_ids=agent_ids,
            ),
            timeout=_SUMMARY_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("summary timed out")
        summary_model = DebateSummaryModel.empty()
    except Exception:
        logger.exception("summary failed")
        summary_model = DebateSummaryModel.empty()

    latency_ms = int((time.perf_counter() - started) * 1000)
    summary_payload = summary_model.model_dump()

    full_summary = {
        "topic": topic,
        "winner_id": winner_id,
        "verdict": verdict,
        "cumulative_scores": {k: round(v, 4) for k, v in cumulative.items()},
        "turn_count": len(turns),
        "narrative": summary_payload,
        "latency_ms": latency_ms,
    }

    if ws_queue is not None:
        await ws_queue.put({"type": "debate_summary", **full_summary})

    if repo is not None and debate_id:
        try:
            await repo.update_debate_status(
                debate_id=debate_id,
                status="completed",
                winner_id=winner_id,
                summary=full_summary,
            )
        except Exception:
            logger.exception("failed to persist debate summary")

    return {
        "summary": full_summary,
        "debate_status": "summarizing",
    }
