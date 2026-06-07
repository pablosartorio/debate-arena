from typing import Annotated, Literal, TypedDict


class TurnScore(TypedDict, total=False):
    factual_fidelity: float
    hallucination_risk: float
    repetition_penalty: float
    consign_compliance: float
    rebuttal_quality: float
    clarity: float
    role_adherence: float
    tool_usage_quality: float
    total: float


class AgentPlan(TypedDict, total=False):
    agent_id: str
    strategy: str
    key_claims: list[str]
    rebuttal_target: str | None


class ToolCallRecord(TypedDict, total=False):
    tool_name: str
    args: dict
    result: str
    success: bool
    latency_ms: int


class Turn(TypedDict, total=False):
    turn_id: str
    turn_number: int
    agent_id: str
    plan: AgentPlan | None
    tool_calls: list[ToolCallRecord]
    response_text: str
    score: TurnScore | None
    word_count: int
    latency_ms: int


class ModeratorIntervention(TypedDict, total=False):
    turn_number: int
    affected_agent: str
    reason: str
    message: str
    severity: Literal["warning", "correction", "redirect"]


class ScoutResult(TypedDict, total=False):
    key_concepts: list[str]
    guiding_questions: list[str]
    misinformation_risks: list[str]
    enabled_tools: list[str]
    evaluation_criteria: list[str]
    sources_consulted: list[str]
    context_summary: str


DebateStatus = Literal[
    "preparing",
    "scouting",
    "planning",
    "speaking",
    "evaluating",
    "intervening",
    "routing",
    "summarizing",
    "ended",
    "error",
]


def _replace(_old, new):
    return new


def _append(old, new):
    if old is None:
        return list(new) if new else []
    return list(old) + list(new)


class DebateState(TypedDict, total=False):
    debate_id: str
    topic: str
    max_turns: int
    max_words: int
    agent1_id: str
    agent2_id: str
    model: str

    enable_scouting: bool
    enable_moderation: bool
    enable_tools: bool
    research_mode: bool

    scout_result: ScoutResult | None
    scouting_done: bool

    current_turn: int
    current_agent_id: str
    turn_order: list[str]
    turns: Annotated[list[Turn], _append]

    moderator_evaluations: Annotated[list[TurnScore], _append]
    interventions: Annotated[list[ModeratorIntervention], _append]
    pending_intervention: ModeratorIntervention | None

    cumulative_scores: dict[str, float]

    debate_status: DebateStatus
    stop_requested: bool

    current_plan: AgentPlan | None

    summary: dict | None
    error: str | None


def initial_state(
    debate_id: str,
    topic: str,
    max_turns: int,
    max_words: int,
    agent1_id: str,
    agent2_id: str,
    model: str,
    enable_scouting: bool,
    enable_moderation: bool,
    enable_tools: bool,
    research_mode: bool,
) -> DebateState:
    return {
        "debate_id": debate_id,
        "topic": topic,
        "max_turns": max_turns,
        "max_words": max_words,
        "agent1_id": agent1_id,
        "agent2_id": agent2_id,
        "model": model,
        "enable_scouting": enable_scouting,
        "enable_moderation": enable_moderation,
        "enable_tools": enable_tools,
        "research_mode": research_mode,
        "scout_result": None,
        "scouting_done": False,
        "current_turn": 0,
        "current_agent_id": agent1_id,
        "turn_order": [agent1_id, agent2_id],
        "turns": [],
        "moderator_evaluations": [],
        "interventions": [],
        "pending_intervention": None,
        "cumulative_scores": {agent1_id: 0.0, agent2_id: 0.0},
        "debate_status": "preparing",
        "stop_requested": False,
        "current_plan": None,
        "summary": None,
        "error": None,
    }
