"""ImplementaciÃ³n SQLite del DebateRepository, sobre aiosqlite."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from db.connection import Database
from db.repository import DebateRepository

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict[str, Any]:
    if row is None:
        return None  # type: ignore
    return {k: row[k] for k in row.keys()}


class SQLiteDebateRepository(DebateRepository):
    def __init__(self, db: Database):
        self.db = db

    @property
    def _conn(self):
        return self.db.connection

    # ---------- writes ----------

    async def create_debate(
        self,
        debate_id: str,
        topic: str,
        agent1_id: str,
        agent2_id: str,
        model: str,
        max_turns: int,
        max_words: int,
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO debates
                (id, topic, agent1_id, agent2_id, model, max_turns, max_words,
                 started_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'running')
            """,
            (debate_id, topic, agent1_id, agent2_id, model, max_turns, max_words, _now_iso()),
        )
        await self._conn.commit()

    async def update_debate_status(
        self,
        debate_id: str,
        status: str,
        winner_id: str | None = None,
        summary: dict | None = None,
    ) -> None:
        ended_at = _now_iso() if status in ("completed", "stopped", "error") else None
        summary_json = json.dumps(summary, ensure_ascii=False) if summary is not None else None

        await self._conn.execute(
            """
            UPDATE debates
               SET status     = ?,
                   ended_at   = COALESCE(?, ended_at),
                   winner_id  = COALESCE(?, winner_id),
                   summary    = COALESCE(?, summary)
             WHERE id = ?
            """,
            (status, ended_at, winner_id, summary_json, debate_id),
        )
        await self._conn.commit()

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
    ) -> None:
        plan_json = json.dumps(plan, ensure_ascii=False) if plan else None
        await self._conn.execute(
            """
            INSERT INTO turns
                (id, debate_id, turn_number, agent_id, response_text,
                 word_count, latency_ms, plan_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(debate_id, turn_number) DO UPDATE SET
                response_text = excluded.response_text,
                word_count    = excluded.word_count,
                latency_ms    = excluded.latency_ms,
                plan_json     = excluded.plan_json
            """,
            (
                turn_id, debate_id, turn_number, agent_id,
                response_text, word_count, latency_ms, plan_json, _now_iso(),
            ),
        )
        await self._conn.commit()

    async def save_evaluation(
        self,
        evaluation_id: str,
        turn_id: str,
        debate_id: str,
        score: dict,
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO evaluations
                (id, turn_id, debate_id,
                 factual_fidelity, hallucination_risk, repetition_penalty,
                 consign_compliance, rebuttal_quality, clarity,
                 role_adherence, tool_usage_quality, total, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evaluation_id, turn_id, debate_id,
                float(score.get("factual_fidelity", 0.0)),
                float(score.get("hallucination_risk", 0.0)),
                float(score.get("repetition_penalty", 0.0)),
                float(score.get("consign_compliance", 0.0)),
                float(score.get("rebuttal_quality", 0.0)),
                float(score.get("clarity", 0.0)),
                float(score.get("role_adherence", 0.0)),
                float(score.get("tool_usage_quality", 0.5)),
                float(score.get("total", 0.0)),
                _now_iso(),
            ),
        )
        await self._conn.commit()

    async def save_intervention(
        self,
        intervention_id: str,
        debate_id: str,
        turn_number: int,
        reason: str,
        message: str,
        severity: str,
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO interventions
                (id, debate_id, turn_number, reason, message, severity, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (intervention_id, debate_id, turn_number, reason, message, severity, _now_iso()),
        )
        await self._conn.commit()

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
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO tool_calls
                (id, turn_id, debate_id, tool_name, args_json, result,
                 latency_ms, success, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                tool_call_id, turn_id, debate_id, tool_name,
                json.dumps(args, ensure_ascii=False), result,
                latency_ms, 1 if success else 0, _now_iso(),
            ),
        )
        await self._conn.commit()

    async def save_event(
        self,
        event_id: str,
        debate_id: str,
        event_type: str,
        payload: dict,
        turn_number: int | None = None,
        agent_id: str | None = None,
    ) -> None:
        await self._conn.execute(
            """
            INSERT INTO events
                (id, debate_id, event_type, turn_number, agent_id,
                 payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id, debate_id, event_type, turn_number, agent_id,
                json.dumps(payload, ensure_ascii=False), _now_iso(),
            ),
        )
        await self._conn.commit()

    # ---------- queries ----------

    async def list_debates(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        cursor = await self._conn.execute(
            """
            SELECT id, topic, agent1_id, agent2_id, model, max_turns, max_words,
                   started_at, ended_at, status, winner_id
              FROM debates
             ORDER BY started_at DESC
             LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [_row_to_dict(r) for r in rows]

    async def get_debate(self, debate_id: str) -> dict[str, Any] | None:
        cursor = await self._conn.execute(
            "SELECT * FROM debates WHERE id = ?",
            (debate_id,),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            return None
        result = _row_to_dict(row)
        if result.get("summary"):
            try:
                result["summary"] = json.loads(result["summary"])
            except (json.JSONDecodeError, TypeError):
                pass
        return result

    async def get_debate_turns(self, debate_id: str) -> list[dict[str, Any]]:
        cursor = await self._conn.execute(
            """
            SELECT id, turn_number, agent_id, response_text, word_count,
                   latency_ms, plan_json, created_at
              FROM turns
             WHERE debate_id = ?
             ORDER BY turn_number ASC
            """,
            (debate_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        result = []
        for r in rows:
            d = _row_to_dict(r)
            if d.get("plan_json"):
                try:
                    d["plan"] = json.loads(d.pop("plan_json"))
                except (json.JSONDecodeError, TypeError):
                    d["plan"] = None
                    d.pop("plan_json", None)
            else:
                d["plan"] = None
                d.pop("plan_json", None)
            result.append(d)
        return result

    async def get_debate_evaluations(self, debate_id: str) -> list[dict[str, Any]]:
        cursor = await self._conn.execute(
            """
            SELECT *
              FROM evaluations
             WHERE debate_id = ?
             ORDER BY created_at ASC
            """,
            (debate_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [_row_to_dict(r) for r in rows]

    async def get_debate_interventions(self, debate_id: str) -> list[dict[str, Any]]:
        cursor = await self._conn.execute(
            """
            SELECT *
              FROM interventions
             WHERE debate_id = ?
             ORDER BY turn_number ASC, created_at ASC
            """,
            (debate_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        return [_row_to_dict(r) for r in rows]

    async def get_debate_tool_calls(self, debate_id: str) -> list[dict[str, Any]]:
        cursor = await self._conn.execute(
            """
            SELECT id, turn_id, tool_name, args_json, result, latency_ms, success, created_at
              FROM tool_calls
             WHERE debate_id = ?
             ORDER BY created_at ASC
            """,
            (debate_id,),
        )
        rows = await cursor.fetchall()
        await cursor.close()
        result = []
        for r in rows:
            d = _row_to_dict(r)
            try:
                d["args"] = json.loads(d.pop("args_json") or "{}")
            except (json.JSONDecodeError, TypeError):
                d["args"] = {}
                d.pop("args_json", None)
            d["success"] = bool(d.get("success"))
            result.append(d)
        return result

    async def get_debate_full(self, debate_id: str) -> dict[str, Any] | None:
        """Combina debate + turns + evaluations + interventions + tool_calls."""
        debate = await self.get_debate(debate_id)
        if debate is None:
            return None

        turns = await self.get_debate_turns(debate_id)
        evaluations = await self.get_debate_evaluations(debate_id)
        interventions = await self.get_debate_interventions(debate_id)
        tool_calls = await self.get_debate_tool_calls(debate_id)

        # indexar evaluations por turn_id para attach al turn correspondiente
        evals_by_turn = {e["turn_id"]: e for e in evaluations}
        for t in turns:
            t["evaluation"] = evals_by_turn.get(t["id"])

        return {
            **debate,
            "turns": turns,
            "interventions": interventions,
            "tool_calls": tool_calls,
        }
