"""
Helper para parsear respuestas JSON estructuradas de Ollama de forma robusta.

format=json en la API de Ollama garantiza JSON sintacticamente valido pero
NO garantiza que cumpla un schema. Este helper:
  1. Extrae JSON de la respuesta (incluso si viene rodeado de markdown).
  2. Lo valida con Pydantic.
  3. Si algo falla, devuelve un default seguro y loggea el error.
Nunca lanza excepciones al caller.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def _extract_json(text: str) -> str | None:
    """
    Extrae el primer objeto/array JSON del texto. Tolera markdown fences y
    texto antes/despues. Devuelve None si no encuentra nada parseable.
    """
    if not text:
        return None

    text = text.strip()

    # caso feliz: el texto ENTERO ya es JSON valido
    if text.startswith(("{", "[")):
        return text

    # extraer de markdown fence ```json ... ```
    m = _JSON_BLOCK_RE.search(text)
    if m:
        return m.group(1)

    # fallback: primer { ... } o [ ... ] balanceado
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth = 0
        for i in range(start, len(text)):
            if text[i] == opener:
                depth += 1
            elif text[i] == closer:
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]

    return None


def parse_structured_response(
    raw: str,
    model_cls: type[T],
    default_factory: Callable[[], T],
    *,
    context: str = "",
) -> T:
    """
    Parsea `raw` y lo valida contra `model_cls`. Si falla, devuelve `default_factory()`
    y loggea el motivo. `context` es un prefijo para el log (ej. "scout", "moderate").
    """
    snippet = _extract_json(raw)
    if snippet is None:
        logger.warning("[%s] no JSON found in response: %r", context or "structured", raw[:200])
        return default_factory()

    try:
        data = json.loads(snippet)
    except json.JSONDecodeError as e:
        logger.warning("[%s] JSON decode failed: %s — raw: %r", context or "structured", e, snippet[:200])
        return default_factory()

    try:
        return model_cls.model_validate(data)
    except ValidationError as e:
        logger.warning("[%s] schema validation failed: %s — data: %r", context or "structured", e, data)
        return default_factory()
