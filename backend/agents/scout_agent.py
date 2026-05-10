"""
ScoutAgent: analiza el tema del debate UNA sola vez antes del primer turno.

Salida: ScoutResultModel con conceptos clave, preguntas guia, riesgos de
desinformacion, criterios de evaluacion para el moderador, y un resumen de
contexto que se inyecta como nota invisible en el system prompt de los
debatientes.

Etapa 4: el scout solo usa el LLM (sin web search). Etapa 9 sumara tools.
"""

from __future__ import annotations

import json
import logging

import httpx
from pydantic import BaseModel, Field

import config
from agents.structured_response import parse_structured_response

logger = logging.getLogger(__name__)


class ScoutResultModel(BaseModel):
    key_concepts: list[str] = Field(default_factory=list)
    guiding_questions: list[str] = Field(default_factory=list)
    misinformation_risks: list[str] = Field(default_factory=list)
    enabled_tools: list[str] = Field(default_factory=list)
    evaluation_criteria: list[str] = Field(default_factory=list)
    sources_consulted: list[str] = Field(default_factory=list)
    context_summary: str = ""

    @classmethod
    def empty(cls) -> "ScoutResultModel":
        return cls()


_SYSTEM_PROMPT = (
    "Sos un analista de debates. Te dan un tema y devolves un mapa estructurado "
    "del terreno argumental. Tu output va a guiar a dos debatientes y a un "
    "moderador. Sos preciso, breve y evitas tomar partido."
)


def _user_prompt(topic: str, web_evidence: str | None = None) -> str:
    parts = [f"Tema: {topic}"]

    if web_evidence:
        parts.append(
            "Evidencia reciente de busqueda web (uso interno; podes referenciar "
            "los conceptos pero no inventes URLs):\n" + web_evidence
        )

    parts.append(
        "Devolve SOLO un JSON con estas claves (sin texto extra, sin markdown):\n"
        '{\n'
        '  "key_concepts": [3 conceptos centrales, frases cortas],\n'
        '  "misinformation_risks": [2 afirmaciones exageradas comunes a evitar],\n'
        '  "context_summary": "1-2 oraciones de contexto factual neutro"\n'
        '}\n'
        "En español rioplatense. Sé breve."
    )
    return "\n\n".join(parts)


class ScoutAgent:
    def __init__(self, model: str | None = None):
        self.model = model or config.SCOUT_MODEL

    async def analyze(
        self,
        topic: str,
        web_evidence: str | None = None,
        sources: list[str] | None = None,
    ) -> ScoutResultModel:
        """
        Llama al LLM con format=json. Si falla la llamada o el parsing,
        devuelve ScoutResultModel.empty() — el debate continua sin contexto.

        web_evidence: snippets de busqueda web ya formateados, opcional.
        sources: urls de las fuentes para guardar en sources_consulted.
        """
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _user_prompt(topic, web_evidence)},
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
            logger.exception("scout LLM call failed")
            return ScoutResultModel.empty()

        result = parse_structured_response(
            raw,
            model_cls=ScoutResultModel,
            default_factory=ScoutResultModel.empty,
            context="scout",
        )

        # adjuntar fuentes consultadas (si las hubo) al ScoutResult final
        if sources:
            seen = set(result.sources_consulted)
            for s in sources:
                if s and s not in seen:
                    result.sources_consulted.append(s)
                    seen.add(s)

        # listar tools efectivamente usadas
        if web_evidence and "web_search" not in result.enabled_tools:
            result.enabled_tools.append("web_search")

        return result
