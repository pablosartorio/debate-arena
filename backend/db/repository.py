"""
ABC del repositorio de persistencia. La implementacion concreta vive en
sqlite_repository.py. Tener la abstraccion permite swap a Postgres en el
futuro sin tocar el grafo ni los endpoints.

Todos los metodos son idempotentes en lo posible: una falla de DB no debe
romper un debate en curso, asi que los callers envuelven en try/except.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DebateRepository(ABC):
    @abstractmethod
    async def create_debate(
        self,
        debate_id: str,
        topic: str,
        agent1_id: str,
        agent2_id: str,
        model: str,
        max_turns: int,
        max_words: int,
    ) -> None: ...

    @abstractmethod
    async def update_debate_status(
        self,
        debate_id: str,
        status: str,
        winner_id: str | None = None,
        summary: dict | None = None,
    ) -> None: ...

    @abstractmethod
    async def save_turn(
        self,
        turn_id: str,
        debate_id: str,
        turn_number: int,
        agent_id: str,
        response_text: str,
        word_count: int,
        latency_ms: int,
        plan: dict | None = None,
    ) -> None: ...

    @abstractmethod
    async def save_evaluation(
        self,
        evaluation_id: str,
        turn_id: str,
        debate_id: str,
        score: dict,
    ) -> None: ...

    @abstractmethod
    async def save_intervention(
        self,
        intervention_id: str,
        debate_id: str,
        turn_number: int,
        reason: str,
        message: str,
        severity: str,
    ) -> None: ...

    @abstractmethod
    async def save_tool_call(
        self,
        tool_call_id: str,
        debate_id: str,
        turn_id: str | None,
        tool_name: str,
        args: dict,
        result: str | None,
        latency_ms: int,
        success: bool,
    ) -> None: ...

    @abstractmethod
    async def save_event(
        self,
        event_id: str,
        debate_id: str,
        event_type: str,
        payload: dict,
        turn_number: int | None = None,
        agent_id: str | None = None,
    ) -> None: ...

    # ---------- queries ----------

    @abstractmethod
    async def list_debates(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_debate(self, debate_id: str) -> dict[str, Any] | None: ...

    @abstractmethod
    async def get_debate_turns(self, debate_id: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_debate_evaluations(self, debate_id: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_debate_interventions(self, debate_id: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_debate_tool_calls(self, debate_id: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    async def get_debate_full(self, debate_id: str) -> dict[str, Any] | None: ...
