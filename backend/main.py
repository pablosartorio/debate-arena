import logging
from contextlib import asynccontextmanager
from pathlib import Path

import json

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from agents.personas import PERSONAS
import config
from db.connection import init_db, close_db
from db.sqlite_repository import SQLiteDebateRepository
from ws_bridge import DebateSession

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = await init_db()
    app.state.repo = SQLiteDebateRepository(db)
    try:
        yield
    finally:
        await close_db()


app = FastAPI(lifespan=lifespan)

# En Docker: frontend se monta en /app/frontend (parent del archivo).
# En desarrollo local: frontend es hermano de backend/.
_HERE = Path(__file__).parent
FRONTEND_DIR = _HERE / "frontend"
if not FRONTEND_DIR.exists():
    FRONTEND_DIR = _HERE.parent / "frontend"


_persona_ids = list(PERSONAS.keys())


def _default_agent(idx: int) -> str:
    preferred = config.DEFAULT_AGENT1_ID if idx == 0 else config.DEFAULT_AGENT2_ID
    if preferred in PERSONAS:
        return preferred
    return _persona_ids[idx] if len(_persona_ids) > idx else ""


@app.get("/api/config")
def get_config():
    return {
        "topic": config.DEFAULT_TOPIC,
        "max_turns": config.DEFAULT_MAX_TURNS,
        "max_words": config.DEFAULT_MAX_WORDS,
        "agent1_id": _default_agent(0),
        "agent2_id": _default_agent(1),
    }


@app.get("/api/personas")
def get_personas():
    return [
        {
            "id": p.id,
            "display_name": p.display_name,
            "emoji": p.emoji,
            "color": p.color,
            "model": p.model,
            "role_label": p.role_label,
            "short_stance": p.short_stance,
        }
        for p in PERSONAS.values()
    ]


@app.get("/api/models")
async def get_models():
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{config.OLLAMA_HOST}/api/tags")
            data = r.json()
            return {"models": [m["name"] for m in data.get("models", [])]}
    except Exception:
        return {"models": []}


# ---------- historial ----------


@app.get("/api/debates")
async def list_debates(limit: int = 50, offset: int = 0):
    repo: SQLiteDebateRepository = app.state.repo
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    debates = await repo.list_debates(limit=limit, offset=offset)
    return {"debates": debates, "limit": limit, "offset": offset}


@app.get("/api/debates/{debate_id}")
async def get_debate(debate_id: str):
    repo: SQLiteDebateRepository = app.state.repo
    debate = await repo.get_debate(debate_id)
    if debate is None:
        raise HTTPException(status_code=404, detail="debate no encontrado")
    return debate


@app.get("/api/debates/{debate_id}/turns")
async def get_debate_turns(debate_id: str):
    repo: SQLiteDebateRepository = app.state.repo
    debate = await repo.get_debate(debate_id)
    if debate is None:
        raise HTTPException(status_code=404, detail="debate no encontrado")
    turns = await repo.get_debate_turns(debate_id)
    return {"debate_id": debate_id, "turns": turns}


@app.get("/api/debates/{debate_id}/full")
async def get_debate_full(debate_id: str):
    repo: SQLiteDebateRepository = app.state.repo
    full = await repo.get_debate_full(debate_id)
    if full is None:
        raise HTTPException(status_code=404, detail="debate no encontrado")
    return full


@app.get("/api/debates/{debate_id}/export")
async def export_debate(debate_id: str):
    repo: SQLiteDebateRepository = app.state.repo
    full = await repo.get_debate_full(debate_id)
    if full is None:
        raise HTTPException(status_code=404, detail="debate no encontrado")
    payload = json.dumps(full, ensure_ascii=False, indent=2)
    short_id = debate_id.split("-")[0]
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="debate-{short_id}.json"'},
    )


# ---------- Diagrama del grafo ----------


@app.get("/api/graph/diagram")
def get_graph_diagram():
    import re
    from graph.graph import build_graph
    compiled = build_graph()
    raw = compiled.get_graph().draw_mermaid()

    # Replace the %%{init}%% block to inject dark theme + better spacing
    themed = re.sub(
        r"%%\{init:.*?\}%%",
        "%%{init: {'theme':'dark','flowchart':{'curve':'linear','padding':20,'nodeSpacing':50,'rankSpacing':60}}}%%",
        raw,
    )
    # Override LangGraph's default light classDefs with pixel-art dark palette
    themed = re.sub(r"classDef default[^\n]*",
                    "classDef default fill:#1a0e05,stroke:#c8923a,color:#f0d090,stroke-width:2px", themed)
    themed = re.sub(r"classDef first[^\n]*",
                    "classDef first fill:#0a0616,stroke:#8060b8,stroke-dasharray:5 3,color:#c0a0f0,stroke-width:2px", themed)
    themed = re.sub(r"classDef last[^\n]*",
                    "classDef last fill:#180e2e,stroke:#8060b8,color:#c0a0f0,stroke-width:2px", themed)

    return {"mermaid": themed}


# ---------- WebSocket ----------


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    repo: SQLiteDebateRepository = app.state.repo
    session = DebateSession(websocket, repo)

    try:
        while True:
            msg = await websocket.receive_json()
            msg_type = msg.get("type")

            if msg_type == "start":
                payload = {k: v for k, v in msg.items() if k != "type"}
                await session.start(payload)

            elif msg_type == "stop":
                await session.cancel()

    except WebSocketDisconnect:
        await session.cancel()


# servir el frontend estatico - debe ir al final para no solapar las rutas /api y /ws
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
