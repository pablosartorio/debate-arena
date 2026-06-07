"""
ModeratorAgent: evalúa cada turno en 8 dimensiones y decide si necesita
intervenir. La intervención efectiva (turno hablado del moderador) la maneja
INTERVENE_NODE en Etapa 7 — aca solo armamos los scores y la "intencion".

Salida JSON con TurnScore + intervention_needed/severity/reason.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

import config
import httpx
from pydantic import BaseModel, field_validator

from agents.structured_response import parse_structured_response

logger = logging.getLogger(__name__)


# Pesos de la formula del plan (suman 1.0):
SCORE_WEIGHTS = {
    "factual_fidelity": 0.20,
    "hallucination_risk": 0.20,        # invertido (1 - hr)
    "consign_compliance": 0.15,
    "rebuttal_quality": 0.15,
    "clarity": 0.12,
    "role_adherence": 0.10,
    "repetition_penalty": 0.05,        # invertido (1 - rp)
    "tool_usage_quality": 0.03,
}


def _clamp(v: float) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.5


def compute_total(score: dict) -> float:
    """Aplica los pesos y la inversion para hallucination/repetition. Clampa cada dim."""
    ff = _clamp(score.get("factual_fidelity", 0.5))
    hr = _clamp(score.get("hallucination_risk", 0.5))
    cc = _clamp(score.get("consign_compliance", 0.5))
    rq = _clamp(score.get("rebuttal_quality", 0.5))
    cl = _clamp(score.get("clarity", 0.5))
    ra = _clamp(score.get("role_adherence", 0.5))
    rp = _clamp(score.get("repetition_penalty", 0.0))
    tu = _clamp(score.get("tool_usage_quality", 0.5))

    total = (
        SCORE_WEIGHTS["factual_fidelity"] * ff
        + SCORE_WEIGHTS["hallucination_risk"] * (1.0 - hr)
        + SCORE_WEIGHTS["consign_compliance"] * cc
        + SCORE_WEIGHTS["rebuttal_quality"] * rq
        + SCORE_WEIGHTS["clarity"] * cl
        + SCORE_WEIGHTS["role_adherence"] * ra
        + SCORE_WEIGHTS["repetition_penalty"] * (1.0 - rp)
        + SCORE_WEIGHTS["tool_usage_quality"] * tu
    )
    return round(total, 4)


class ModeratorEvaluation(BaseModel):
    """Salida estructurada del moderador para un turno."""

    factual_fidelity: float = 0.5
    hallucination_risk: float = 0.5
    repetition_penalty: float = 0.0
    consign_compliance: float = 0.5
    rebuttal_quality: float = 0.5
    clarity: float = 0.5
    role_adherence: float = 0.5
    tool_usage_quality: float = 0.5

    intervention_needed: bool = False
    intervention_reason: str = ""    # 'hallucination'|'repetition'|'off_topic'|'role_break'|''
    intervention_severity: str = ""  # 'warning'|'correction'|'redirect'|''
    notes: str = ""

    @field_validator(
        "factual_fidelity", "hallucination_risk", "repetition_penalty",
        "consign_compliance", "rebuttal_quality", "clarity",
        "role_adherence", "tool_usage_quality",
        mode="before",
    )
    @classmethod
    def _clamp_scores(cls, v):
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.5

    @classmethod
    def neutral(cls) -> ModeratorEvaluation:
        """Score neutro cuando el moderador falla — no penaliza ni premia."""
        return cls()

    def to_score_dict(self) -> dict:
        d = self.model_dump()
        d["total"] = compute_total(d)
        return d


_SYSTEM_PROMPT = (
    "Sos un moderador imparcial de debates. Evaluás cada turno en 8 dimensiones "
    "(0.0 = pesimo, 1.0 = excelente). La mayoría de los turnos deberian puntuar "
    "entre 0.5 y 0.85. Reserva 0.9+ para turnos excepcionales. No tomas partido."
)


def _user_prompt(
    topic: str,
    agent_id: str,
    turn_text: str,
    previous_opponent_text: str | None,
    own_history_summary: str | None,
    evaluation_criteria: list[str] | None,
) -> str:
    parts = [f"Tema: {topic}", f"Turno a evaluar (de {agent_id}):\n\"{turn_text.strip()}\""]

    if previous_opponent_text:
        parts.append(f'Oponente dijo antes:\n"{previous_opponent_text.strip()}"')

    if own_history_summary:
        parts.append(f"Turnos previos del mismo agente (para detectar repetición):\n{own_history_summary}")

    if evaluation_criteria:
        criteria_str = "\n".join(f"- {c}" for c in evaluation_criteria)
        parts.append(f"Criterios específicos del tema a evaluar:\n{criteria_str}")

    parts.append(
        "Devolvé SOLO un JSON con estas claves (cada score 0.0-1.0):\n"
        "{\n"
        '  "factual_fidelity": 0.7,\n'
        '  "hallucination_risk": 0.2,\n'
        '  "repetition_penalty": 0.1,\n'
        '  "consign_compliance": 0.8,\n'
        '  "rebuttal_quality": 0.6,\n'
        '  "clarity": 0.7,\n'
        '  "role_adherence": 0.8,\n'
        '  "tool_usage_quality": 0.5,\n'
        '  "intervention_needed": false,\n'
        '  "notes": "comentario breve"\n'
        "}\n"
        "La mayoria de los turnos puntua entre 0.5 y 0.85. Sin markdown, solo el JSON."
    )
    return "\n\n".join(parts)


class ModeratorAgent:
    def __init__(self, model: str | None = None):
        self.model = model or config.MODERATION_MODEL

    async def evaluate(
        self,
        topic: str,
        agent_id: str,
        turn_text: str,
        previous_opponent_text: str | None = None,
        own_history_summary: str | None = None,
        evaluation_criteria: list[str] | None = None,
    ) -> ModeratorEvaluation:
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(
                topic, agent_id, turn_text, previous_opponent_text,
                own_history_summary, evaluation_criteria,
            )},
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
            logger.exception("moderator LLM call failed")
            return ModeratorEvaluation.neutral()

        return parse_structured_response(
            raw,
            model_cls=ModeratorEvaluation,
            default_factory=ModeratorEvaluation.neutral,
            context=f"moderate:{agent_id}",
        )

    async def speak_intervention(
        self,
        topic: str,
        agent_id: str,
        turn_text: str,
        reason: str,
        severity: str,
        max_words: int = 40,
    ) -> AsyncIterator[str]:
        """
        Genera un mensaje breve y streameado de intervencion para encauzar el debate.
        Sin format=json: salida en lenguaje natural. Cap blando de palabras.
        """
        system = (
            "Sos el moderador imparcial de un debate. NO tomas partido ideologico. "
            "Tu intervencion es muy breve (1-2 oraciones), directa, en español "
            "rioplatense, sin agresividad. Encauzás sin asumir el rol de un debatiente."
        )
        user = (
            f"Tema: {topic}\n"
            f"Acabo de leer este turno de {agent_id}:\n"
            f'"{turn_text.strip()}"\n\n'
            f"Detecte un problema — razon: {reason}, severidad: {severity}.\n"
            "Intervene ahora con 1-2 oraciones que: (a) señalen el problema sin "
            "atacar a la persona, (b) reorienten al debatiente. Hablale directamente "
            f"al agente {agent_id}. Sin listas, solo texto corrido."
        )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        word_count = 0
        buffer = ""

        try:
            async with httpx.AsyncClient(timeout=config.LLM_TIMEOUT_SECONDS) as client:
                async with client.stream(
                    "POST",
                    f"{config.OLLAMA_HOST}/api/chat",
                    json={"model": self.model, "messages": messages, "stream": True},
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        token = chunk.get("message", {}).get("content", "")
                        if not token:
                            if chunk.get("done"):
                                return
                            continue

                        buffer += token
                        words = buffer.split()
                        new_words = len(words) - word_count

                        if word_count + new_words >= max_words:
                            remaining = max_words - word_count
                            if remaining > 0:
                                partial = " ".join(words[:remaining])
                                emitted_so_far = " ".join(words[:word_count])
                                yield partial[len(emitted_so_far):].lstrip()
                            return

                        word_count += new_words
                        yield token

                        if chunk.get("done"):
                            return
        except Exception:
            logger.exception("moderator speak_intervention failed")
            return
