-- Schema completo del debate-arena. Se aplica idempotente al inicio.
-- Las tablas para etapas posteriores (evaluations, interventions, tool_calls)
-- se crean ya pero quedan vacias hasta que esos nodos las llenen.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS debates (
    id          TEXT PRIMARY KEY,
    topic       TEXT NOT NULL,
    agent1_id   TEXT NOT NULL,
    agent2_id   TEXT NOT NULL,
    model       TEXT NOT NULL,
    max_turns   INTEGER NOT NULL,
    max_words   INTEGER NOT NULL,
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    status      TEXT NOT NULL,         -- 'running'|'completed'|'stopped'|'error'
    winner_id   TEXT,
    summary     TEXT                   -- JSON blob opcional
);

CREATE INDEX IF NOT EXISTS idx_debates_started_at ON debates(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_debates_status     ON debates(status);

CREATE TABLE IF NOT EXISTS turns (
    id              TEXT PRIMARY KEY,
    debate_id       TEXT NOT NULL REFERENCES debates(id) ON DELETE CASCADE,
    turn_number     INTEGER NOT NULL,
    agent_id        TEXT NOT NULL,
    response_text   TEXT NOT NULL,
    word_count      INTEGER NOT NULL,
    latency_ms      INTEGER NOT NULL,
    plan_json       TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_turns_debate    ON turns(debate_id, turn_number);
CREATE UNIQUE INDEX IF NOT EXISTS uq_turns_debate_number ON turns(debate_id, turn_number);

CREATE TABLE IF NOT EXISTS evaluations (
    id                  TEXT PRIMARY KEY,
    turn_id             TEXT NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    debate_id           TEXT NOT NULL REFERENCES debates(id) ON DELETE CASCADE,
    factual_fidelity    REAL NOT NULL,
    hallucination_risk  REAL NOT NULL,
    repetition_penalty  REAL NOT NULL,
    consign_compliance  REAL NOT NULL,
    rebuttal_quality    REAL NOT NULL,
    clarity             REAL NOT NULL,
    role_adherence      REAL NOT NULL,
    tool_usage_quality  REAL NOT NULL,
    total               REAL NOT NULL,
    created_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_evaluations_debate ON evaluations(debate_id);
CREATE INDEX IF NOT EXISTS idx_evaluations_turn   ON evaluations(turn_id);

CREATE TABLE IF NOT EXISTS interventions (
    id          TEXT PRIMARY KEY,
    debate_id   TEXT NOT NULL REFERENCES debates(id) ON DELETE CASCADE,
    turn_number INTEGER NOT NULL,
    reason      TEXT NOT NULL,
    message     TEXT NOT NULL,
    severity    TEXT NOT NULL,         -- 'warning'|'correction'|'redirect'
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_interventions_debate ON interventions(debate_id, turn_number);

CREATE TABLE IF NOT EXISTS tool_calls (
    id          TEXT PRIMARY KEY,
    turn_id     TEXT REFERENCES turns(id) ON DELETE CASCADE,
    debate_id   TEXT NOT NULL REFERENCES debates(id) ON DELETE CASCADE,
    tool_name   TEXT NOT NULL,
    args_json   TEXT NOT NULL,
    result      TEXT,
    latency_ms  INTEGER NOT NULL,
    success     INTEGER NOT NULL,      -- 0/1
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tool_calls_debate ON tool_calls(debate_id);

CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    debate_id       TEXT NOT NULL REFERENCES debates(id) ON DELETE CASCADE,
    event_type      TEXT NOT NULL,
    turn_number     INTEGER,
    agent_id        TEXT,
    payload_json    TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_debate ON events(debate_id, created_at);
