import os
from pathlib import Path

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# Modelos chicos por default (CPU-friendly). Eventualmente se reemplazaran
# por llamadas a APIs externas (Anthropic/OpenAI), pero por ahora priorizamos
# fluidez del flujo agentic sobre calidad del discurso.
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "llama3.2:1b")
MODERATION_MODEL = os.getenv("MODERATION_MODEL", DEFAULT_MODEL)
PLANNING_MODEL = os.getenv("PLANNING_MODEL", DEFAULT_MODEL)
SCOUT_MODEL = os.getenv("SCOUT_MODEL", DEFAULT_MODEL)
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", DEFAULT_MODEL)

DEFAULT_MAX_TURNS = 6
DEFAULT_MAX_WORDS = 80
DEFAULT_TOPIC = "el futuro de la inteligencia artificial y quién debería controlarla"
DEFAULT_AGENT1_ID = "valentina"
DEFAULT_AGENT2_ID = "bruno"

DATA_DIR = Path(os.getenv("DATA_DIR", str(Path(__file__).parent / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = str(DATA_DIR / "debates.db")

SCOUTING_TIMEOUT_SECONDS = 60.0
LLM_TIMEOUT_SECONDS = 120.0
TOOL_TIMEOUT_SECONDS = 8.0

ENABLE_SCOUTING_DEFAULT = True
ENABLE_MODERATION_DEFAULT = True
ENABLE_TOOLS_DEFAULT = True
RESEARCH_MODE_DEFAULT = False

MODERATION_THRESHOLDS = {
    "hallucination_risk": 0.75,
    "repetition_penalty": 0.80,
    "consign_compliance": 0.30,
    "role_adherence": 0.40,
}

WS_QUEUE_MAX_SIZE = 1000
WS_DRAIN_TIMEOUT_SECONDS = 60.0
