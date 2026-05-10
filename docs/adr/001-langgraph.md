# ADR 001: Uso de LangGraph para orquestación

**Fecha**: 2025  
**Estado**: Aceptado

## Contexto

El debate tiene múltiples fases secuenciales con lógica condicional:
- scouting inicial del tema
- planificación por turno
- generación de discurso
- evaluación del moderador
- intervención opcional
- resumen final

Además el flujo puede cortarse en cualquier momento (stop del usuario), y el estado del debate necesita fluir de nodo en nodo sin variables globales.

## Decisión

Usar **LangGraph** (`StateGraph`) como framework de orquestación.

## Alternativas consideradas

**Orquestación manual con bucle Python** (lo que estaba en `orchestrator.py`):
- Más simple de entender al principio
- Difícil de agregar bifurcaciones condicionales
- El estado se pasa explícitamente entre funciones
- Difícil de pausar/cancelar limpiamente

**LangChain chains/sequences**:
- Menos flexible para grafos con ciclos
- No soporta bien el estado acumulativo

## Consecuencias positivas

- Las bifurcaciones condicionales (¿intervenir o no? ¿quedan turnos?) son declarativas y legibles
- El estado (`DebateState`) fluye automáticamente entre nodos
- Fácil agregar un nodo nuevo sin tocar el resto
- LangGraph tiene soporte para streaming nativo
- Facilita tracing/observabilidad futura (LangSmith)

## Consecuencias negativas

- Dependencia externa (langgraph, langchain-core)
- Curva de aprendizaje inicial
- El debugging puede ser menos directo que un bucle simple
- Las versiones de LangGraph cambian frecuentemente

## Notas

El archivo `orchestrator.py` se mantiene temporalmente como referencia del enfoque anterior, pero no se usa en producción.
