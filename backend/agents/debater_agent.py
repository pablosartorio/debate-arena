"""
DebaterAgent: planificacion interna + delegacion al BaseAgent para hablar.

La planificacion (plan_for_turn) corre antes de cada turno: el agente decide
una estrategia, sus 2-3 key_claims, y a quÃ© apuntar como contraargumento.
Salida JSON estricta validada con Pydantic.

El plan se inyecta como nota privada en el system prompt del SPEAK y
NUNCA se emite al frontend (es razonamiento interno).
"""

from __future__ import annotations

import json
import logging

import httpx
from pydantic import BaseModel, Field

import config
from agents.personas import Persona
from agents.structured_response import parse_structured_response

logger = logging.getLogger(__name__)


class AgentPlanModel(BaseModel):
    strategy: str = ""
    key_claims: list[str] = Field(default_factory=list)
    rebuttal_target: str | None = None

    @classmethod
    def empty(cls) -> "AgentPlanModel":
        return cls()


def _system_prompt(persona: Persona) -> str:
    return (
        f"Sos {persona.display_name}. Estas planificando tu proximo turno en un "
        "debate. Esta es tu fase privada de razonamiento â el output NO se le "
        "muestra al usuario, solo te ayuda a estructurar tu respuesta. "
        "Sos breve, especifico y honesto sobre tu plan."
    )


def _user_prompt(
    topic: str,
    last_opponent_text: str | None,
    own_previous_text: str | None,
    is_first_turn: bool,
) -> str:
    parts = [f"Tema: {topic}\n"]

    if is_first_turn:
        parts.append("Es tu turno de apertura. Todavia no hablo nadie.")
    else:
        if last_opponent_text:
            parts.append(f"Ultimo turno del oponente:\n\"{last_opponent_text.strip()}\"\n")
        if own_previous_text:
            parts.append(f"Tu ultimo turno fue:\n\"{own_previous_text.strip()}\"\n")

    parts.append(
        "Devolve SOLO un JSON con estas claves (sin markdown):\n"
        '{\n'
        '  "strategy": "1 oracion corta sobre tu enfoque para este turno",\n'
        '  "key_claims": [2-3 afirmaciones concretas que vas a defender, cada una en frase corta],\n'
        '  "rebuttal_target": "1 frase: que punto especifico del oponente vas a contraargumentar (o null si es turno de apertura)"\n'
        '}\n'
        "En espaÃ±ol rioplatense. Se conciso."
    )
    return "\n".join(parts)


async def plan_for_turn(
    persona: Persona,
    topic: str,
    last_opponent_text: str | None,
    own_previous_text: str | None,
    is_first_turn: bool,
    model: str | None = None,
) -> AgentPlanModel:
    """
    Llama al LLM con format=json para que el agente arme su plan interno.
    Si falla, devuelve plan vacio (el speak corre sin plan â degradacion elegante).
    """
    model_name = model or config.PLANNING_MODEL or persona.model

    messages = [
        {"role": "system", "content": _system_prompt(persona)},
        {"role": "user", "content": _user_prompt(topic, last_opponent_text, own_previous_text, is_first_turn)},
    ]

    try:
        async with httpx.AsyncClient(timeout=config.LLM_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{config.OLLAMA_HOST}/api/chat",
                json={
                    "model": model_name,
                    "messages": messages,
                    "stream": False,
                    "format": "json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data.get("message", {}).get("content", "")
    except Exception:
        logger.exception("plan LLM call failed for %s", persona.id)
        return AgentPlanModel.empty()

    return parse_structured_response(
        raw,
        model_cls=AgentPlanModel,
        default_factory=AgentPlanModel.empty,
        context=f"plan:{persona.id}",
    )


def render_plan_for_speak(plan: AgentPlanModel | dict) -> str | None:
    """
    Convierte el plan a un mensaje de sistema invisible para el SPEAK.
    Returns None si el plan esta vacio.
    """
    if isinstance(plan, AgentPlanModel):
        d = plan.model_dump()
    else:
        d = plan or {}

    strategy = (d.get("strategy") or "").strip()
    claims = d.get("key_claims") or []
    rebuttal = (d.get("rebuttal_target") or "") if d.get("rebuttal_target") else ""

    if not (strategy or claims or rebuttal):
        return None

    parts = ["Plan privado para tu proximo turno (NO menciones que tenes un plan):"]
    if strategy:
        parts.append(f"- Estrategia: {strategy}")
    if claims:
        parts.append("- Afirmaciones a defender: " + "; ".join(claims))
    if rebuttal:
        parts.append(f"- Contraargumento al oponente: {rebuttal}")

    return "\n".join(parts)
