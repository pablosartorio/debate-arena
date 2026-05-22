# Contrato de eventos WebSocket

## Conexión

El cliente se conecta a `ws://localhost:8080/ws`.

## Cliente → Servidor

### `start`
Inicia un debate nuevo.

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
  "enable_tools": false,
  "research_mode": false
}
```

### `stop`
Señal para cancelar el debate en curso.

```json
{
  "type": "stop"
}
```

---

## Servidor → Cliente

### `debate_started`
El debate fue creado en la base de datos.

```json
{
  "type": "debate_started",
  "debate_id": "uuid-...",
  "topic": "...",
  "agents": ["valentina", "bruno"]
}
```

### `scouting_start`
Comenzó el análisis del tema (si `enable_scouting=true`).

```json
{ "type": "scouting_start" }
```

### `scouting_token`
Token de streaming del scout (análisis del tema).

```json
{ "type": "scouting_token", "token": "La " }
```

### `scouting_done`
El scout terminó su análisis.

```json
{
  "type": "scouting_done",
  "concepts": ["IA", "regulación", "riesgos"],
  "context": "texto del análisis..."
}
```

### `turn_start`
Comienza un turno de debate.

```json
{
  "type": "turn_start",
  "turn_number": 1,
  "agent_id": "valentina",
  "agent_name": "Valentina"
}
```

### `agent_planning`
El agente está planificando su estrategia (si `enable_moderation=true`).

```json
{
  "type": "agent_planning",
  "agent_id": "valentina",
  "strategy": "atacar el punto débil del argumento anterior",
  "key_claims": ["claim1", "claim2"]
}
```

### `token`
Token del discurso del agente (streaming en tiempo real).

```json
{
  "type": "token",
  "agent_id": "valentina",
  "token": "La "
}
```

### `turn_end`
Terminó un turno. Incluye el texto completo y métricas.

```json
{
  "type": "turn_end",
  "turn_number": 1,
  "agent_id": "valentina",
  "text": "La inteligencia artificial debe...",
  "word_count": 75,
  "latency_ms": 3200,
  "score": {
    "factual_fidelity": 0.8,
    "hallucination_risk": 0.2,
    "repetition_penalty": 0.1,
    "consign_compliance": 0.9,
    "rebuttal_quality": 0.7,
    "clarity": 0.85,
    "role_adherence": 0.95,
    "tool_usage_quality": 0.0,
    "total": 0.78
  }
}
```

### `moderator_evaluation`
El moderador evaluó el turno.

```json
{
  "type": "moderator_evaluation",
  "turn_number": 1,
  "scores": { ... },
  "needs_intervention": false
}
```

### `moderator_intervention`
El moderador interviene (si detectó un problema).

```json
{
  "type": "moderator_intervention",
  "turn_number": 2,
  "reason": "hallucination_detected",
  "message": "Por favor, el dato citado no es correcto...",
  "severity": "warning"
}
```

### `conversation_end`
El debate terminó (todos los turnos completados o stop recibido).

```json
{
  "type": "conversation_end",
  "debate_id": "uuid-...",
  "summary": "texto del resumen...",
  "winner": "valentina",
  "total_turns": 6
}
```

### `error`
Ocurrió un error durante el debate.

```json
{
  "type": "error",
  "message": "descripción del error",
  "debate_id": "uuid-..."
}
```

---

## Principio de diseño: contratos aditivos

Los eventos solo agregan campos nuevos, nunca renombran ni eliminan existentes. El frontend debe ignorar campos que no conoce. Esto permite evolucionar el protocolo sin romper clientes viejos.
