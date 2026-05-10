# Debate Arena

Sistema de debate automático entre agentes de IA con interfaz pixel-art. Dos agentes con posturas ideológicas distintas debaten un tema en tiempo real, moderados por un tercer agente evaluador.

```
┌─────────────────────────────────────────────────┐
│          DEBATE ARENA  [pixel office]           │
│                                                 │
│   [Valentina]    [Moderador]    [Bruno]         │
│   Acelerac.      Evalúa         Humanista       │
│                                                 │
│  ← tokens streameados en tiempo real →          │
└─────────────────────────────────────────────────┘
```

## Quick start

```bash
# 1. Clonar
git clone https://github.com/pablosartorio/debate-arena.git
cd debate-arena

# 2. Copiar variables de entorno
cp .env.example .env

# 3. Levantar (requiere Docker y Ollama corriendo)
make dev

# 4. Abrir en el browser
open http://localhost:8000
```

> Ollama debe estar corriendo en el host antes de `make dev`.
> Para descargar el modelo por defecto: `./init_models.sh`

## Arquitectura

```
Browser (WebSocket)
     │
     ▼
FastAPI (ws_bridge.py)
     │   asyncio.Queue
     ▼
LangGraph StateGraph
  scout → router → plan → speak → moderate → [intervene?]
                   └──────────────────────────────┘ ×N
                          ↓ (al final)
                        summary → END
```

Los agentes se comunican con Ollama via HTTP. El estado completo del debate se persiste en SQLite después de cada turno.

Ver [docs/architecture.md](docs/architecture.md) para el detalle completo.

## Agentes y personas

| ID | Nombre | Postura | Color |
|---|---|---|---|
| `valentina` | Valentina | Aceleracionista — pro-tech sin frenos | `#7c3aed` |
| `bruno` | Bruno | Humanista — la tech al servicio del humano | `#059669` |
| `turulero` | Turulero | Estatista — rol activo del estado | `#c0392b` |
| `libertad` | Libertad | Liberal — mercado libre, estado mínimo | `#2980b9` |

## Comandos útiles

```bash
make dev        # docker compose up --build
make stop       # docker compose down
make backend    # backend local sin Docker
make lint       # ruff check backend/
make format     # ruff format backend/
make test       # pytest
make logs       # logs del backend en tiempo real
```

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | URL del servidor Ollama |
| `DATA_DIR` | `./backend/data` | Directorio para la base de datos SQLite |

## Devcontainer (VS Code)

El proyecto incluye configuración de devcontainer para desarrollo reproducible.

1. Instalar [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
2. Abrir el proyecto en VS Code
3. `Ctrl+Shift+P` → "Dev Containers: Reopen in Container"

Ollama debe seguir corriendo en el host. Ver [docs/guides/devcontainer.md](docs/guides/devcontainer.md).

## Stack

- **Backend**: Python 3.12, FastAPI, LangGraph, aiosqlite
- **LLM**: Ollama (local, CPU/GPU)
- **Frontend**: Vanilla JS + CSS pixel-art
- **DB**: SQLite con WAL mode
- **Containerización**: Docker + docker-compose

## Roadmap

Ver [docs/architecture.md#roadmap](docs/architecture.md#roadmap) para el plan de etapas.

## Licencia

MIT — ver [LICENSE](LICENSE).
