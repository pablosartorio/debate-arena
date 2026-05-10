# Arquitectura

## Flujo general

```
Browser
  │  WebSocket /ws
  ▼
FastAPI main.py
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

## Nodos del grafo

```
scout_node
    │
    ▼
router_node ──────────────────────────────────────┐
    │                                              │
    ▼  (si quedan turnos)                         │
plan_node                                          │
    │                                              │
    ▼                                              │
speak_node                                         │
    │                                              │
    ▼  (si quedan turnos)                         │
moderate_node                                      │
    │                 │                           │
    ▼ (sin problema)  ▼ (intervención necesaria)  │
router_node      intervene_node                   │
    └─────────────────┘                           │
    │                                             │
    ▼  (turnos agotados o stop flag)              │
summary_node ◄────────────────────────────────────┘
    │
    ▼
END
```

### Responsabilidades de cada nodo

| Nodo | Función |
|---|---|
| `scout_node` | Analiza el tema, genera contexto, habilita tools |
| `router_node` | Decide a quién le toca hablar (alternancia) |
| `plan_node` | El agente planifica su estrategia antes de hablar |
| `speak_node` | El agente genera su discurso (streaming de tokens) |
| `moderate_node` | Evalúa el turno: 8 métricas de calidad |
| `intervene_node` | El moderador interviene si detecta problemas |
| `summary_node` | Genera resumen final del debate |

## Estado del debate (DebateState)

El estado es un `TypedDict` que fluye a través de todos los nodos. Incluye:

- `topic`: tema del debate
- `turns`: lista acumulativa de turnos anteriores
- `current_turn_number`: contador actual
- `current_speaker_id`: quién habla ahora
- `scout_result`: análisis del tema (si scouting habilitado)
- `interventions`: lista de intervenciones del moderador
- `stop_flag`: señal de cancelación por el usuario
- `error`: si hubo un error en el grafo

## Bridge WebSocket ↔ LangGraph

`ws_bridge.py` es el componente más delicado del sistema. Conecta el protocolo WebSocket (sync/async con el browser) con el grafo LangGraph (async interno).

```
WebSocket ──► DebateSession.start()
                   │
                   ├── asyncio.create_task(_run_graph())
                   └── asyncio.create_task(_drain())
                              │
                         Queue.get() → ws.send_json()
```

El patrón `_run_graph()` + `_drain()` con `asyncio.Queue` permite:
- El grafo emite eventos sin bloquear (solo hace `queue.put_nowait()`)
- El drain los envía al browser sin acoplarse al ritmo del grafo
- Si el WebSocket se corta, `_drain()` termina con un sentinel `None`

Ver [docs/adr/002-ws-queue.md](adr/002-ws-queue.md) para la decisión de diseño.

## Base de datos

SQLite con WAL mode (Write-Ahead Logging) para soportar lecturas concurrentes mientras se escribe.

### Tablas

| Tabla | Contenido |
|---|---|
| `debates` | Metadatos del debate (topic, agents, status, winner) |
| `turns` | Cada turno: texto, latencia, plan |
| `evaluations` | 8 métricas por turno (factual_fidelity, hallucination_risk, ...) |
| `interventions` | Intervenciones del moderador |
| `tool_calls` | Llamadas a tools: nombre, args, resultado, latencia |
| `events` | Audit trail completo de eventos WebSocket |

El acceso se hace via `DebateRepository` (interfaz abstracta en `db/repository.py`), implementado por `SQLiteRepository`. Esto permite cambiar la DB en el futuro sin tocar el resto del código.

## Agentes

Todos heredan de `BaseAgent` (`agents/base_agent.py`), que maneja:
- Streaming de tokens via Ollama HTTP API
- Límite de palabras por turno
- System prompt + historial de mensajes

Cada agente tiene su `system_prompt` en `agents/personas.py` que define su postura ideológica y estilo.

## Tools

Los agentes pueden usar tools externas si `enable_tools=True`:
- `WebSearchTool`: búsqueda en DuckDuckGo (no requiere API key)
- Las tools se registran en `tools/registry.py`
- Cada tool implementa `BaseTool.run()` (async)

## Roadmap

### Etapa 1 (actual): Funcionalidad base
- [x] LangGraph con 7 nodos
- [x] Streaming de tokens
- [x] Persistencia SQLite
- [x] Frontend pixel-art
- [x] WebSearch tool

### Etapa 2: Mejoras de calidad
- [ ] Scoring más sofisticado (LLM-as-judge)
- [ ] Historial en el frontend
- [ ] Export del debate completo
- [ ] Tests unitarios de nodos

### Etapa 3: Features avanzados
- [ ] Más personas/agentes
- [ ] Temas con contexto externo (RAG)
- [ ] Modo tournament (varios debates)
- [ ] Observabilidad (LangSmith / tracing)
