"""
ABC para todas las herramientas que pueden usar agents/nodes.

Contrato:
  - input siempre `ToolInput` (query + context opcional)
  - output siempre `ToolOutput` con success/result/source/latency/error
  - run() nunca lanza: si falla, devuelve ToolOutput(success=False, error=...)

Las tools concretas viven en tools/*.py y se registran en tools/registry.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class ToolInput(BaseModel):
    query: str
    context: str = ""


class ToolOutput(BaseModel):
    success: bool = True
    result: str = ""
    source: str = ""           # url, "ddg", "llm", etc.
    latency_ms: int = 0
    error: str = ""

    @classmethod
    def fail(cls, message: str, latency_ms: int = 0) -> ToolOutput:
        return cls(success=False, error=message, latency_ms=latency_ms)


class BaseTool(ABC):
    name: str = "base"
    description: str = ""
    requires_network: bool = False

    @abstractmethod
    async def run(self, input: ToolInput) -> ToolOutput: ...
