# Arquitectura

## Flujo general

```
Browser
  │  WebSocket /ws
  ▼
FastAPI main.py ── REST /api/*
  │
  ▼
DebateSession (ws_bridge.py)
  ├── asyncio.Queue (canal de eventos)
  ├── Task: _run_graph()   ← ejecuta el grafo LangGraph
  └── Task: _drain()       ← envía eventos al WebSocket
         │
         ▼
LangGraph StateGraph (graph/graph.py)
```

## Nodos del grafo (8 nodos)

```
scout
  │
  ▼
router ───────────────────────────────────────────┐
  │  (route_from_router)                           │
  ▼  speak  → plan                                 │ end
plan                                               │
  │                                                │
  ▼                                                │
speak                                              │
  │  (route_after_speak)                           │
  ▼  moderate                       end ───────────┤
moderate                                           │
  │  (route_after_moderate)                        │
  ├── intervene ── router                          │
  ├── router (siguiente turno)                     │
  └── end ───────────────────────────────────────►│
                                                   ▼
                                              summarize
                                                   │
                                                   ▼
                                               finalize
                                                   │
                                                   ▼
                                                  END
```

> **Nota de diseño (fix de fairness):** el cierre por "turnos agotados" se decide
> en `route_after_moderate`, **después** de moderar. Así el último turno también
> se evalúa y los `cumulative_scores` quedan parejos. (Antes el cierre estaba en
> `route_after_speak` y salteaba la moderación del último turno, sesgando al ganador.)

### Responsabilidades de cada nodo

| Nodo | Función |
|---|---|
| `scout` | Analiza el tema 1 sola vez; genera contexto + criterios; corre `web_search` si hay tools |
| `router` | Decide a quién le toca hablar (alternancia por `current_turn % len(turn_order)`) |
| `plan` | El agente planifica su estrategia antes de hablar (JSON privado, no visible) |
| `speak` | El agente genera su discurso (streaming de tokens) |
| `moderate` | Evalúa el turno en 8 dimensiones y decide si hay que intervenir |
| `intervene` | El moderador habla cuando se detecta un problema (turno hablado) |
| `summarize` | Determina el ganador por score y pide la narrativa final al LLM |
| `finalize` | Cierra el debate y emite `conversation_end` |

## Estado del debate (`DebateState`)

El estado es un `TypedDict` (`graph/state.py`) que fluye por todos los nodos.
Los campos acumulativos usan reducers (`turns`, `moderator_evaluations`,
`interventions` se concatenan con `_append`). Campos clave:

- `topic`, `max_turns`, `max_words`, `model`: parámetros del debate
- `turns`: lista acumulativa de turnos (`Turn`)
- `current_turn`: contador de turnos completados
- `current_agent_id`: quién habla ahora
- `turn_order`: orden de alternancia (`[agent1_id, agent2_id]`)
- `scout_result`: análisis del tema (si scouting habilitado)
- `cumulative_scores`: score acumulado por agente
- `pending_intervention` / `interventions`: intervenciones del moderador
- `stop_requested`: señal de cancelación
- `error`: si hubo un error en el grafo
- `summary`: payload del resumen final

## Bridge WebSocket ↔ LangGraph

`ws_bridge.py` es el componente más delicado. Conecta el WebSocket (browser) con
el grafo LangGraph (async interno) vía una `asyncio.Queue`.

```
WebSocket ──► DebateSession.start()
                   │
                   ├── asyncio.create_task(_run_graph())   # ainvoke(graph)
                   └── asyncio.create_task(_drain())        # Queue.get() → ws.send_json()
```

El patrón `_run_graph()` + `_drain()` con `asyncio.Queue` permite:
- Los nodos emiten eventos con `queue.put(...)` sin acoplarse al WebSocket
- El drain los envía al browser a su propio ritmo
- Al terminar (o ante una excepción), `_run_graph()` empuja un **sentinel**
  (`{"__sentinel__": "end"}`) para que `_drain()` corte aunque no haya llegado
  `conversation_end`

El `stop` del cliente llama a `DebateSession.cancel()`, que cancela los tasks y
persiste el status `stopped`. Ver [adr/002-ws-queue.md](adr/002-ws-queue.md).

## Scoring

Cada turno se evalúa en 8 dimensiones (`0.0`–`1.0`). El `total` es un promedio
ponderado (`SCORE_WEIGHTS` en `agents/moderator_agent.py`), invirtiendo las
dimensiones "de penalización":

| Dimensión | Peso | Nota |
|---|---|---|
| `factual_fidelity` | 0.20 | |
| `hallucination_risk` | 0.20 | invertida (`1 - hr`) |
| `consign_compliance` | 0.15 | |
| `rebuttal_quality` | 0.15 | |
| `clarity` | 0.12 | |
| `role_adherence` | 0.10 | |
| `repetition_penalty` | 0.05 | invertida (`1 - rp`) |
| `tool_usage_quality` | 0.03 | |

El **ganador** se determina deterministicamente sumando los `total` por agente
(`determine_winner`), con un margen para declarar empate técnico. El LLM del
`summary_node` solo aporta la narrativa, no elige ganador.

**Intervención:** además del flag del LLM, hay thresholds deterministas en
`config.MODERATION_THRESHOLDS` (p. ej. `hallucination_risk > 0.75`) que disparan
una intervención aunque el LLM no la pida.

## Base de datos

SQLite con WAL mode (`PRAGMA journal_mode = WAL`) para lecturas concurrentes
mientras se escribe. Una sola conexión `aiosqlite` persistente serializa las
queries en su thread interno.

### Tablas

| Tabla | Contenido |
|---|---|
| `debates` | Metadatos del debate (topic, agents, status, winner, summary) |
| `turns` | Cada turno: texto, latencia, word_count, plan |
| `evaluations` | 8 métricas + total por turno |
| `interventions` | Intervenciones del moderador |
| `tool_calls` | Llamadas a tools: nombre, args, resultado, latencia |
| `events` | Audit trail de eventos del scout |

El acceso pasa por `DebateRepository` (ABC en `db/repository.py`), implementado
por `SQLiteDebateRepository` (`db/sqlite_repository.py`). Esto permite cambiar la
DB en el futuro sin tocar el grafo ni los endpoints.

## Agentes

Los debatientes hablan vía `BaseAgent` (`agents/base_agent.py`), que maneja:
- Streaming de tokens contra la API HTTP de Ollama (`/api/chat`)
- Límite de palabras por turno (cap blando)
- System prompt (de la persona) + contexto invisible (scout/plan/intervención) + historial

El modelo efectivo es el elegido en la UI (`state["model"]`), con fallback al de
la persona. Los agentes especializados (`ScoutAgent`, `ModeratorAgent`,
`SummaryAgent`, y `plan_for_turn`) usan salida JSON validada con Pydantic vía
`agents/structured_response.py`. Cada persona define su `system_prompt` en
`agents/personas.py`.

## Tools

Si `enable_tools=true`, el scout puede usar tools externas:
- `WebSearchTool`: búsqueda en DuckDuckGo (sin API key), corrida en threadpool
  para no bloquear el event loop.
- Se registran en `tools/registry.py`; cada tool implementa `BaseTool.run()` (async)
  y **nunca** lanza: ante un fallo devuelve `ToolOutput(success=False, ...)`.

## Endpoints REST

| Método | Ruta | Qué devuelve |
|---|---|---|
| `GET` | `/api/config` | Defaults (topic, turnos, palabras, agentes) |
| `GET` | `/api/personas` | Lista de personas disponibles |
| `GET` | `/api/models` | Modelos disponibles en Ollama |
| `GET` | `/api/debates` | Lista paginada de debates |
| `GET` | `/api/debates/{id}` | Metadatos de un debate |
| `GET` | `/api/debates/{id}/turns` | Turnos de un debate |
| `GET` | `/api/debates/{id}/full` | Debate completo (turns + evals + intervenciones + tools) |
| `GET` | `/api/debates/{id}/export` | Descarga JSON del debate |
| `GET` | `/api/graph/diagram` | Mermaid del grafo (themed) |

## Roadmap

Ver [../notas/planes.md](../notas/planes.md) para el plan de etapas (memoria
cross-debate, RAG, humano en el loop, streaming nativo de LangGraph,
observabilidad con LangSmith, modo torneo).
