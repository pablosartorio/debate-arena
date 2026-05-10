from typing import TypedDict, Literal


DebateEventType = Literal[
    "debate_started",
    "debate_stopped",
    "debate_ended",
    "debate_error",
    "scouting_start",
    "scouting_completed",
    "scouting_error",
    "agent_planning_start",
    "agent_planning_end",
    "tool_call_start",
    "tool_call_end",
    "tool_call_error",
    "turn_start",
    "turn_token",
    "turn_end",
    "turn_counter",
    "moderator_evaluation",
    "moderator_intervention_start",
    "moderator_intervention_token",
    "moderator_intervention_end",
    "moderator_intervention",
    "score_update",
    "debate_summary",
    "warning",
]


class DebateEvent(TypedDict, total=False):
    event_id: str
    type: DebateEventType
    timestamp: str
    debate_id: str
    turn_number: int | None
    agent_id: str | None
    latency_ms: int | None
    model: str | None
    token_count: int | None
    payload: dict
