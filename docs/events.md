# Contrato de eventos WebSocket

> Este documento describe **exactamente** los mensajes que viajan por `/ws`, tal
> como los emite el backend hoy. Cada evento sale del grafo vía una
> `asyncio.Queue` y `DebateSession._drain()` lo reenvía al browser con
> `ws.send_json(...)`. Ver [architecture.md](architecture.md) y
> [adr/002-ws-queue.md](adr/002-ws-queue.md).

## Conexión

El cliente abre `ws://<host>/ws` (en local: `ws://localhost:8080/ws`). Una sola
sesión activa por socket: un nuevo `start` cancela la anterior.

---

## Cliente → Servidor

### `start`
Inicia un debate nuevo. Los campos opcionales caen a los defaults de `config.py`.

```json
{
  "type": "start",
  "topic": "¿Debe regularse la inteligencia artificial?",
  "max_turns": 6,
  "max_words": 80,
  "agent1_id": "valentina",
  "agent2_id": "bruno",
  "model": "llama3.2:1b",
  "enable_scouting": true,
  "enable_moderation": true,
  "enable_tools": true,
  "research_mode": false
}
```

Si `agent1_id` o `agent2_id` no existen en `PERSONAS`, el servidor responde con
un `error` (`"Personaje no encontrado."`) y no arranca.

### `stop`
Cancela el debate en curso (cancelación dura del task del grafo).

```json
{ "type": "stop" }
```

---

## Servidor → Cliente

Hay **19 tipos** de eventos. El frontend ignora los que no conoce (contrato
aditivo, ver más abajo).

### `node_active`
El grafo entró a un nodo. El panel de grafo lo usa para resaltar el nodo activo
en vivo. `node` ∈ `scout | router | plan | speak | moderate | intervene | summarize | finalize`.

```json
{ "type": "node_active", "node": "speak" }
```

### `scouting_start`
Arrancó el análisis del tema (si `enable_scouting=true`).

```json
{ "type": "scouting_start", "topic": "..." }
```

### `scouting_completed`
El scout terminó. Las listas pueden venir vacías (degradación elegante si el LLM
falla o el modelo chico no llena todos los campos).

```json
{
  "type": "scouting_completed",
  "key_concepts": ["...", "...", "..."],
  "guiding_questions": ["...", "..."],
  "misinformation_risks": ["...", "..."],
  "evaluation_criteria": ["...", "..."],
  "context_summary": "1-2 oraciones de contexto neutro",
  "latency_ms": 1234
}
```

### `tool_call_start`
Una tool empezó a ejecutarse (hoy solo `web_search`, durante el scouting).

```json
{ "type": "tool_call_start", "tool": "web_search", "phase": "scout", "query": "..." }
```

### `tool_call_end`
La tool terminó.

```json
{
  "type": "tool_call_end",
  "tool": "web_search",
  "phase": "scout",
  "success": true,
  "latency_ms": 980,
  "source": "https://... | https://...",
  "error": ""
}
```

### `turn_counter`
El router decidió el próximo turno/orador.

```json
{ "type": "turn_counter", "current": 2, "max": 6, "next_agent": "bruno" }
```

### `agent_planning`
El agente está planificando (fase privada, el plan **no** se emite).
Dos fases: `start` y `end` (esta última con `latency_ms`).

```json
{ "type": "agent_planning", "agent": "valentina", "phase": "start", "turn": 3 }
```

### `turn_start`
Empieza un turno hablado. `agent` puede ser una persona o `"moderator"`
(cuando interviene, reusa la misma pipeline visual).

```json
{ "type": "turn_start", "agent": "valentina" }
```

### `token`
Token del discurso, en streaming.

```json
{ "type": "token", "agent": "valentina", "content": "La " }
```

### `turn_end`
Terminó el turno hablado (sin texto ni score; eso va por otros eventos).

```json
{ "type": "turn_end", "agent": "valentina" }
```

### `moderator_evaluating`
El moderador empezó a evaluar el último turno (puede tardar decenas de segundos
con modelos chicos). UX: badge "evaluando…".

```json
{ "type": "moderator_evaluating", "agent": "valentina", "turn": 3, "phase": "start" }
```

### `moderator_evaluation`
Resultado de la evaluación del turno (8 dimensiones + `total`). Ver el detalle
de las dimensiones en [architecture.md](architecture.md#scoring).

```json
{
  "type": "moderator_evaluation",
  "agent": "valentina",
  "turn": 3,
  "score": {
    "factual_fidelity": 0.7,
    "hallucination_risk": 0.2,
    "repetition_penalty": 0.1,
    "consign_compliance": 0.8,
    "rebuttal_quality": 0.6,
    "clarity": 0.7,
    "role_adherence": 0.8,
    "tool_usage_quality": 0.5,
    "total": 0.66
  },
  "latency_ms": 5400
}
```

### `score_update`
Scoreboard acumulado por agente, tras sumar el último turno.

```json
{ "type": "score_update", "scores": { "valentina": 1.98, "bruno": 1.32 } }
```

### `moderator_intervention_pending`
El moderador decidió intervenir (combinando el flag del LLM con los thresholds
deterministas de `config.MODERATION_THRESHOLDS`). Viene un turno hablado.

```json
{
  "type": "moderator_intervention_pending",
  "agent": "valentina",
  "turn": 3,
  "reason": "hallucination",
  "severity": "correction"
}
```

`reason` ∈ `hallucination | repetition | off_topic | role_break | moderation`.
`severity` ∈ `warning | correction | redirect`.

### `moderator_intervention`
La intervención hablada del moderador. Dos fases:

```json
{ "type": "moderator_intervention", "phase": "start", "severity": "correction",
  "reason": "hallucination", "agent": "valentina", "turn": 3 }
```
```json
{ "type": "moderator_intervention", "phase": "end", "severity": "correction",
  "reason": "hallucination", "agent": "valentina", "turn": 3,
  "message": "texto final de la intervención", "latency_ms": 3100 }
```

Entre `start` y `end` llegan `turn_start`/`token`/`turn_end` con `agent: "moderator"`.

### `summary_start`
Arrancó la generación del resumen final.

```json
{ "type": "summary_start" }
```

### `debate_summary`
Resumen final del debate. El ganador se decide **deterministicamente** por
`cumulative_scores` (con un margen para empate); el LLM solo aporta la narrativa.

```json
{
  "type": "debate_summary",
  "topic": "...",
  "winner_id": "valentina",
  "verdict": "Ventaja para valentina (1.98 vs 1.32).",
  "cumulative_scores": { "valentina": 1.98, "bruno": 1.32 },
  "turn_count": 6,
  "narrative": {
    "overall": "2-3 oraciones generales",
    "per_agent": {
      "valentina": { "highlights": ["..."], "weaknesses": ["..."] },
      "bruno":     { "highlights": ["..."], "weaknesses": ["..."] }
    },
    "key_moments": ["...", "..."]
  },
  "latency_ms": 7200
}
```

`winner_id` puede ser `null` (empate técnico).

### `conversation_end`
El debate terminó (todos los turnos, o stop). Cierra el ciclo de la UI.

```json
{ "type": "conversation_end" }
```

### `error`
Ocurrió un error (validación de personas, o excepción del grafo).

```json
{ "type": "error", "message": "descripción del error" }
```

---

## Orden típico de eventos

```
node_active(scout) → scouting_start → [tool_call_start → tool_call_end] → scouting_completed
└─ por turno ─────────────────────────────────────────────────────────────────┐
   node_active(router) → turn_counter
   node_active(plan)   → agent_planning(start) → agent_planning(end)
   node_active(speak)  → turn_start → token* → turn_end
   node_active(moderate) → moderator_evaluating → moderator_evaluation → score_update
   [ moderator_intervention_pending
     node_active(intervene) → moderator_intervention(start)
       → turn_start(moderator) → token* → turn_end(moderator)
       → moderator_intervention(end) ]
└──────────────────────────────────────────────────────────────────────────────┘
node_active(summarize) → summary_start → debate_summary
node_active(finalize)  → conversation_end
```

---

## Principio de diseño: contratos aditivos

Los eventos solo **agregan** campos nuevos; nunca renombran ni eliminan los
existentes. El frontend ignora los campos (y tipos) que no conoce. Esto permite
evolucionar el protocolo sin romper clientes viejos.
