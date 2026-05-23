"""
SCOUT_NODE: corre 1 sola vez antes del turno 1.

Degradación elegante: si scouting_done ya esta True, o enable_scouting es False,
o el scout falla/timeoutea, el grafo continua sin contexto extra y el debate
funciona como en Etapa 1.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig

import config as app_config
from agents.scout_agent import ScoutAgent, ScoutResultModel
from graph.state import DebateState
from tools.base import ToolInput
from tools.registry import get_tool

logger = logging.getLogger(__name__)


async def _try_web_search(
    topic: str,
    ws_queue: asyncio.Queue | None,
    repo,
    debate_id: str | None,
) -> tuple[str | None, list[str]]:
    """
    Llama web_search; si falla, devuelve (None, []). Persistente en tool_calls
    cuando hay repo. Emite tool_call_start/end por WS.
    """
    tool = get_tool("web_search")
    if tool is None:
        return None, []

    if ws_queue is not None:
        await ws_queue.put(
            {"type": "tool_call_start", "tool": tool.name, "phase": "scout", "query": topic}
        )

    output = await tool.run(ToolInput(query=topic))

    if ws_queue is not None:
        await ws_queue.put(
            {
                "type": "tool_call_end",
                "tool": tool.name,
                "phase": "scout",
                "success": output.success,
                "latency_ms": output.latency_ms,
                "source": output.source,
                "error": output.error,
            }
        )

    if repo is not None and debate_id:
        try:
            await repo.save_tool_call(
                tool_call_id=str(uuid.uuid4()),
                debate_id=debate_id,
                turn_id=None,    # tool-call de scouting no esta atado a un turn
                tool_name=tool.name,
                args={"query": topic},
                result=output.result if output.success else None,
                latency_ms=output.latency_ms,
                success=output.success,
            )
        except Exception:
            logger.exception("failed to persist tool_call")

    if not output.success:
        return None, []

    sources = [s.strip() for s in (output.source or "").split("|") if s.strip()]
    return output.result, sources


async def scout_node(state: DebateState, config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable", {}) if config else {}
    ws_queue: asyncio.Queue | None = configurable.get("ws_queue")
    if ws_queue is not None:
        await ws_queue.put({"type": "node_active", "node": "scout"})
    repo = configurable.get("repo")
    debate_id = configurable.get("debate_id") or state.get("debate_id")

    # idempotencia: si ya corrio, no repetir
    if state.get("scouting_done"):
        return {}

    # opt-out
    if not state.get("enable_scouting"):
        return {"scouting_done": True, "scout_result": None}

    topic = state.get("topic", "")
    if ws_queue is not None:
        await ws_queue.put({"type": "scouting_start", "topic": topic})

    started = time.perf_counter()

    # Si tools estan habilitadas, intentamos web_search ANTES del LLM.
    # Si falla, el scout corre sin evidencia — degradacion elegante.
    web_evidence: str | None = None
    sources: list[str] = []
    if state.get("enable_tools"):
        try:
            web_evidence, sources = await _try_web_search(
                topic=topic,
                ws_queue=ws_queue,
                repo=repo,
                debate_id=debate_id,
            )
        except Exception:
            logger.exception("web_search wrapper failed")

    scout = ScoutAgent(model=state.get("model"))

    try:
        result = await asyncio.wait_for(
            scout.analyze(topic, web_evidence=web_evidence, sources=sources),
            timeout=app_config.SCOUTING_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("scout timed out after %.1fs", app_config.SCOUTING_TIMEOUT_SECONDS)
        result = ScoutResultModel.empty()
    except Exception:
        logger.exception("scout failed")
        result = ScoutResultModel.empty()

    latency_ms = int((time.perf_counter() - started) * 1000)
    payload = result.model_dump()

    if ws_queue is not None:
        await ws_queue.put(
            {
                "type": "scouting_completed",
                "key_concepts": payload["key_concepts"],
                "guiding_questions": payload["guiding_questions"],
                "misinformation_risks": payload["misinformation_risks"],
                "evaluation_criteria": payload["evaluation_criteria"],
                "context_summary": payload["context_summary"],
                "latency_ms": latency_ms,
            }
        )

    if repo is not None and debate_id:
        try:
            await repo.save_event(
                event_id=str(uuid.uuid4()),
                debate_id=debate_id,
                event_type="scouting_completed",
                payload={**payload, "latency_ms": latency_ms},
            )
        except Exception:
            logger.exception("failed to persist scout result")

    return {
        "scout_result": payload,
        "scouting_done": True,
        "debate_status": "routing",
    }
