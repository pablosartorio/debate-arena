"""
WebSearchTool: busca el tema en DuckDuckGo y devuelve los top snippets.

Sin API key, gratis, rate-limit informal.

Degradación elegante: si la red falla o el modulo no esta disponible,
devuelve ToolOutput(success=False) y el caller decide qué hacer
(tipicamente seguir sin contexto extra).

La libreria duckduckgo_search expone un cliente sincronico (DDGS); lo
envolvemos en run_in_executor para no bloquear el event loop.
"""

from __future__ import annotations

import asyncio
import logging
import time

import config
from tools.base import BaseTool, ToolInput, ToolOutput

logger = logging.getLogger(__name__)


def _search_sync(query: str, max_results: int = 3) -> list[dict]:
    """Sync helper que corre en threadpool."""
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        raise RuntimeError("duckduckgo_search no esta instalado")

    with DDGS() as ddgs:
        return list(ddgs.text(
            query,
            region="wt-wt",
            safesearch="off",
            max_results=max_results,
        ))


def _format_snippets(items: list[dict], max_chars: int = 1200) -> tuple[str, list[str]]:
    """Devuelve (texto_concatenado, lista_de_urls)."""
    if not items:
        return "", []

    parts = []
    sources = []
    for it in items:
        title = (it.get("title") or "").strip()
        body = (it.get("body") or "").strip()
        url = (it.get("href") or it.get("url") or "").strip()
        if not (title or body):
            continue
        snippet = f"- {title}\n  {body}"
        parts.append(snippet)
        if url:
            sources.append(url)

    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars].rsplit("\n", 1)[0] + "\n  [...truncado]"

    return text, sources


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Busca en DuckDuckGo y devuelve top snippets (titulo + body)."
    requires_network = True

    def __init__(self, max_results: int = 3):
        self.max_results = max_results

    async def run(self, input: ToolInput) -> ToolOutput:
        started = time.perf_counter()
        query = (input.query or "").strip()
        if not query:
            return ToolOutput.fail("query vacia", latency_ms=0)

        loop = asyncio.get_running_loop()
        try:
            items = await asyncio.wait_for(
                loop.run_in_executor(None, _search_sync, query, self.max_results),
                timeout=config.TOOL_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.warning("web_search timeout for %r", query)
            return ToolOutput.fail("timeout", latency_ms=latency_ms)
        except Exception as e:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.exception("web_search failed")
            return ToolOutput.fail(str(e), latency_ms=latency_ms)

        latency_ms = int((time.perf_counter() - started) * 1000)
        text, sources = _format_snippets(items)

        if not text:
            return ToolOutput(
                success=False,
                error="sin resultados",
                latency_ms=latency_ms,
                source="ddg",
            )

        return ToolOutput(
            success=True,
            result=text,
            source=" | ".join(sources[:3]) or "ddg",
            latency_ms=latency_ms,
        )
