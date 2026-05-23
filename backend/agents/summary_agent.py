"""
SummaryAgent: produce el resumen narrativo del debate al final.

El "ganador" se determina deterministicamente por cumulative_scores — el LLM
solo aporta la narrativa (highlights, weaknesses, momentos clave). Asi
evitamos que un LLM chico se contradiga con los scores ya calculados.

Salida JSON validada con Pydantic. Si falla, devolvemos un summary vacio
y el debate termina igual con los scores como unica señal.
"""

from __future__ import annotations

import logging

import httpx
from pydantic import BaseModel, Field

import config
from agents.structured_response import parse_structured_response

logger = logging.getLogger(__name__)


class AgentAssessment(BaseModel):
    highlights: list[str] = Field(default_factory=list)   # 1-2 puntos fuertes
    weaknesses: list[str] = Field(default_factory=list)   # 1-2 puntos debiles


class DebateSummaryModel(BaseModel):
    overall: str = ""                                      # 2-3 oraciones generales
    per_agent: dict[str, AgentAssessment] = Field(default_factory=dict)
    key_moments: list[str] = Field(default_factory=list)   # 2-3 momentos del debate

    @classmethod
    def empty(cls) -> "DebateSummaryModel":
        return cls()


def _format_turns_for_summary(turns: list[dict]) -> str:
    """Compacta los turnos para el prompt: agente: \"texto\" por linea."""
    if not turns:
        return "(sin turnos registrados)"
    lines = []
    for t in turns:
        agent = t.get("agent_id", "?")
        text = (t.get("response_text") or "").strip()
        if text:
            lines.append(f"{agent}: \"{text}\"")
    return "\n".join(lines) if lines else "(sin turnos registrados)"


_SYSTEM_PROMPT = (
    "Sos un analista imparcial de debates. Tu tarea es producir un resumen "
    "estructurado del intercambio, sin tomar partido ideologico. "
    "Sos breve y especifico, en español rioplatense."
)


def _user_prompt(
    topic: str,
    turns: list[dict],
    cumulative_scores: dict[str, float],
    agent_ids: list[str],
) -> str:
    transcript = _format_turns_for_summary(turns)
    scores_line = ", ".join(f"{aid}={cumulative_scores.get(aid, 0.0):.2f}" for aid in agent_ids)

    return (
        f"Tema del debate: {topic}\n"
        f"Scores acumulados (suma del moderador, mayor es mejor): {scores_line}\n\n"
        f"Transcripcion del debate:\n{transcript}\n\n"
        "Devolvé SOLO un JSON con esta forma (sin markdown):\n"
        "{\n"
        '  "overall": "2-3 oraciones que describan el debate sin elegir ganador",\n'
        '  "per_agent": {\n'
        f'    "{agent_ids[0] if agent_ids else "agentX"}": {{ "highlights": ["..."], "weaknesses": ["..."] }},\n'
        f'    "{agent_ids[1] if len(agent_ids) > 1 else "agentY"}": {{ "highlights": ["..."], "weaknesses": ["..."] }}\n'
        "  },\n"
        '  "key_moments": ["...", "..."]\n'
        "}\n"
        "Cada lista 1-2 elementos cortos. Sé conciso."
    )


class SummaryAgent:
    def __init__(self, model: str | None = None):
        self.model = model or config.SUMMARY_MODEL

    async def summarize(
        self,
        topic: str,
        turns: list[dict],
        cumulative_scores: dict[str, float],
        agent_ids: list[str],
    ) -> DebateSummaryModel:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(topic, turns, cumulative_scores, agent_ids)},
        ]

        try:
            async with httpx.AsyncClient(timeout=config.LLM_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    f"{config.OLLAMA_HOST}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": False,
                        "format": "json",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                raw = data.get("message", {}).get("content", "")
        except Exception:
            logger.exception("summary LLM call failed")
            return DebateSummaryModel.empty()

        return parse_structured_response(
            raw,
            model_cls=DebateSummaryModel,
            default_factory=DebateSummaryModel.empty,
            context="summary",
        )


def determine_winner(
    cumulative_scores: dict[str, float],
    agent_ids: list[str],
    margin: float = 0.05,
) -> tuple[str | None, str]:
    """
    Decide el ganador en base a scores acumulados.
    Si la diferencia es menor a `margin`, declaramos empate.
    Returns (winner_id_or_None, verdict_text).
    """
    if not agent_ids:
        return None, "Sin participantes."

    scored = [(aid, float(cumulative_scores.get(aid, 0.0))) for aid in agent_ids]
    scored.sort(key=lambda x: x[1], reverse=True)

    if len(scored) == 1:
        return scored[0][0], f"Solo participo {scored[0][0]}."

    top, second = scored[0], scored[1]
    diff = top[1] - second[1]

    if diff < margin:
        return None, f"Empate técnico ({top[0]}={top[1]:.2f} vs {second[0]}={second[1]:.2f})."

    return top[0], f"Ventaja para {top[0]} ({top[1]:.2f} vs {second[1]:.2f})."
