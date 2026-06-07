"""Registro global de herramientas disponibles."""

from __future__ import annotations

from tools.base import BaseTool
from tools.web_search import WebSearchTool

TOOL_REGISTRY: dict[str, BaseTool] = {
    "web_search": WebSearchTool(max_results=3),
}


def get_tool(name: str) -> BaseTool | None:
    return TOOL_REGISTRY.get(name)


def list_tools() -> list[dict]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "requires_network": t.requires_network,
        }
        for t in TOOL_REGISTRY.values()
    ]
