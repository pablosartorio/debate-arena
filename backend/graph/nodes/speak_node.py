"""SPEAK_NODE: el agente actual habla, streameando tokens al WebSocket."""

import asyncio
import logging
import time
import uuid
from typing import Any

from langchain_core.runnables import RunnableConfig

from agents.base_agent import BaseAgent
from agents.debater_agent import render_plan_for_speak
from agents.personas import PERSONAS
from graph.state import DebateState, Turn

logger = logging.getLogger(__name__)


def _trim_to_sentence(text: str) -> str:
    last = max(text.rfind("."), text.rfind("!"), text.rfind("?"))
    if last > len(text) // 3:
        return text[: last + 1]
    return text.rstrip() + "."


def _last_intervention_for(state: DebateState, agent_id: str) -> str | None:
    """
    Si el moderador intervino dirigiendose a este agente desde su ultimo turno,
    devuelve un system message con la nota. Una vez que el agente "respondio"
    a la intervencion (es decir, hablo despues), no se le repite.
    """
    interventions = state.get("interventions") or []
    if not interventions:
        return None

    turns = state.get("turns") or []
    last_own_turn_number = 0
    for t in reversed(turns):
        if t.get("agent_id") == agent_id:
            last_own_turn_number = t.get("turn_number") or 0
            break

    relevant = [
        i for i in interventions
        if i.get("affected_agent") == agent_id
        and (i.get("turn_number") or 0) > last_own_turn_number
    ]
    if not relevant:
        return None

    last = relevant[-1]
    msg = (last.get("message") or "").strip()
    if not msg:
        return None

    severity = last.get("severity", "warning")
    return (
        f"Nota privada: el moderador acaba de señalarte algo "
        f"(severidad: {severity}). Dijo:\n\"{msg}\"\n"
        "Tomá nota para tu proximo turno y ajustá tu argumento. "
        "No cites al moderador textualmente."
    )


def _scout_context(state: DebateState) -> str | None:
    """
    Construye un mensaje de sistema con el contexto del scout. Se inyecta
    como instruccion invisible para los debatientes (no aparece en el WS).
    Retorna None si no hay scout result.
    """
    sr = state.get("scout_result")
    if not sr:
        return None

    parts = []
    summary = sr.get("context_summary") or ""
    if summary.strip():
        parts.append(f"Contexto neutro del tema: {summary.strip()}")

    concepts = sr.get("key_concepts") or []
    if concepts:
        parts.append("Conceptos centrales que deberias tener presentes: " + "; ".join(concepts))

    risks = sr.get("misinformation_risks") or []
    if risks:
        parts.append(
            "Riesgos de desinformacion a EVITAR (no afirmar como hechos): "
            + "; ".join(risks)
        )

    if not parts:
        return None

    parts.append(
        "Estas notas son contextuales y privadas: no las menciones explicitamente "
        "en tu turno, ni cites que un scout te las dio. Son para calibrar tu argumento."
    )
    return "\n\n".join(parts)


def _history_for(state: DebateState, agent_id: str) -> list[dict]:
    """
    Construye historial desde la perspectiva del agente: sus turnos = assistant,
    los del otro = user. Si no hay turnos previos, abre con la consigna.
    """
    turns = state.get("turns") or []
    topic = state.get("topic", "")

    if not turns:
        return [{"role": "user", "content": f"El tema del debate es: {topic}. Presentá tu postura inicial."}]

    messages: list[dict] = []
    for t in turns:
        speaker = t.get("agent_id")
        text = t.get("response_text") or ""
        if not text:
            continue
        role = "assistant" if speaker == agent_id else "user"
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] += "\n" + text
        else:
            messages.append({"role": role, "content": text})

    if not messages:
        return [{"role": "user", "content": f"El tema del debate es: {topic}. Presentá tu postura inicial."}]

    if messages[-1]["role"] == "assistant":
        messages.append({"role": "user", "content": "Continuá tu argumento."})

    return messages


async def speak_node(state: DebateState, config: RunnableConfig) -> dict[str, Any]:
    configurable = config.get("configurable", {}) if config else {}
    ws_queue: asyncio.Queue | None = configurable.get("ws_queue")
    if ws_queue is not None:
        await ws_queue.put({"type": "node_active", "node": "speak"})
    stop_event: asyncio.Event | None = configurable.get("stop_event")
    repo = configurable.get("repo")
    debate_id = configurable.get("debate_id") or state.get("debate_id")

    agent_id = state.get("current_agent_id")
    persona = PERSONAS.get(agent_id) if agent_id else None
    if not persona:
        return {"error": f"persona no encontrada: {agent_id}", "stop_requested": True}

    if stop_event and stop_event.is_set():
        return {"stop_requested": True}

    max_words = state.get("max_words", 80)
    agent = BaseAgent(persona, max_words)

    history = _history_for(state, agent_id)
    scout_part = _scout_context(state)
    plan_dict = state.get("current_plan")
    plan_part = render_plan_for_speak(plan_dict) if plan_dict else None
    intervention_part = _last_intervention_for(state, agent_id)

    # Mergear contextos invisibles. Si todos son None, no se inyecta nada.
    extra_chunks = [c for c in (scout_part, plan_part, intervention_part) if c]
    extra_context = "\n\n".join(extra_chunks) if extra_chunks else None

    turn_number = state.get("current_turn", 0) + 1

    if ws_queue is not None:
        await ws_queue.put({"type": "turn_start", "agent": agent_id})

    full_response = ""
    word_count = 0
    stopped_mid_turn = False
    started = time.perf_counter()

    try:
        async for token in agent.generate(history, extra_system_context=extra_context):
            if stop_event and stop_event.is_set():
                stopped_mid_turn = True
                break
            full_response += token
            if ws_queue is not None:
                await ws_queue.put({"type": "token", "agent": agent_id, "content": token})
        word_count = len(full_response.split())
    except Exception as e:
        if ws_queue is not None:
            await ws_queue.put({"type": "error", "message": str(e)})
        return {"error": str(e), "stop_requested": True}

    latency_ms = int((time.perf_counter() - started) * 1000)

    if ws_queue is not None:
        await ws_queue.put({"type": "turn_end", "agent": agent_id})

    update: dict[str, Any] = {
        "current_turn": turn_number,
        "debate_status": "routing",
        # limpiar el plan: el siguiente turno generara uno nuevo
        "current_plan": None,
    }

    if full_response.strip():
        trimmed = _trim_to_sentence(full_response)
        turn_id = str(uuid.uuid4())
        new_turn: Turn = {
            "turn_id": turn_id,
            "turn_number": turn_number,
            "agent_id": agent_id,
            "plan": plan_dict,
            "tool_calls": [],
            "response_text": trimmed,
            "score": None,
            "word_count": word_count,
            "latency_ms": latency_ms,
        }
        update["turns"] = [new_turn]

        if repo is not None and debate_id:
            try:
                await repo.save_turn(
                    turn_id=turn_id,
                    debate_id=debate_id,
                    turn_number=turn_number,
                    agent_id=agent_id,
                    response_text=trimmed,
                    word_count=word_count,
                    latency_ms=latency_ms,
                    plan=plan_dict,
                )
            except Exception:
                logger.exception("failed to persist turn %s", turn_number)

    if stopped_mid_turn:
        update["stop_requested"] = True

    return update
