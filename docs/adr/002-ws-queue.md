# ADR 002: asyncio.Queue como bridge WebSocket ↔ LangGraph

**Fecha**: 2025  
**Estado**: Aceptado

## Contexto

El grafo LangGraph genera eventos de forma continua (tokens, turn_start, scores, etc.) mientras el WebSocket espera recibirlos y enviarlos al browser. El problema es que estos dos mundos operan a ritmos distintos:

- El grafo puede generar eventos más rápido de lo que el WebSocket puede enviarlos
- Si el WebSocket se desconecta, el grafo no debería crashear
- El usuario puede mandar una señal `stop` en cualquier momento
- Se necesita un mecanismo de cancellation limpio

## Decisión

Usar `asyncio.Queue` como buffer entre el grafo y el WebSocket, con dos tasks concurrentes:

```python
asyncio.create_task(_run_graph())   # produce eventos → queue.put_nowait()
asyncio.create_task(_drain())       # consume eventos → ws.send_json()
```

El sentinel `None` en la queue señaliza el fin del stream.

## Por qué este patrón

**Desacople**: el grafo no sabe nada del WebSocket. Solo hace `queue.put_nowait(event)`. Si el WS se cae, el grafo sigue funcionando hasta que la queue se llena o se recibe la señal de stop.

**Backpressure**: si la queue se llena (el browser no consume), `put_nowait()` tira `QueueFull` en vez de bloquear el grafo indefinidamente.

**Cancellation limpia**: cuando el usuario manda `stop`, se setea `stop_flag` en el estado y el grafo termina su nodo actual. El drain espera el sentinel `None` para cerrarse.

**Drain timeout**: `_drain()` tiene un timeout para no quedarse esperando si el grafo se cuelga.

## Alternativas consideradas

**Llamadas directas** (`await ws.send_json()` dentro de cada nodo):
- Acopla el grafo al WebSocket
- Si el WS falla, el nodo crasha
- Más difícil de testear los nodos aislados

**Callbacks/hooks de LangGraph**:
- LangGraph tiene soporte nativo de streaming, pero menos control sobre el orden y tipo de eventos custom

## Consecuencias

- La lógica de ws_bridge.py es más compleja que una llamada directa
- Es más robusto ante disconnects inesperados
- Los nodos son testeables sin WebSocket (solo verificar que pushearon a la queue)
- El patrón sentinel (`None` = fin) es una convención que hay que respetar
