# Cómo contribuir

## Setup

```bash
git clone https://github.com/pablosartorio/debate-arena.git
cd debate-arena
cp .env.example .env
make dev
```

O con devcontainer: ver [docs/guides/devcontainer.md](guides/devcontainer.md).

## Estrategia de ramas

```
main        ← siempre estable (demos, releases)
develop     ← integración de features
feature/*   ← cambios concretos
```

Flujo:
1. Crear rama desde `develop`: `git checkout -b feature/mi-feature develop`
2. Hacer commits chicos y descriptivos
3. Abrir PR hacia `develop`
4. Mergear a `main` solo para releases

## Estándares de código

**Linter y formatter**: ruff

```bash
make lint     # verifica sin modificar
make format   # formatea automáticamente
```

La configuración está en `pyproject.toml`. El CI rechaza PRs que fallen el lint.

## Cómo agregar una nueva persona/agente

1. Editar `backend/agents/personas.py`
2. Agregar una nueva instancia de `Persona`:

```python
nueva = Persona(
    id="nueva",
    name="Nombre",
    emoji="🔥",
    color="#hexcolor",
    role_label="Etiqueta corta",
    short_stance="Una frase que describe su postura",
    system_prompt="""
    Eres [nombre], [descripción de su ideología].
    Siempre defiendes [postura principal].
    Tu estilo es [adjetivos: directo, irónico, formal...].
    """
)
```

3. Agregar `nueva` a la lista `PERSONAS` al final del archivo
4. Agregar la paleta de colores pixel-art en `frontend/app.js` (sección `CHARACTER_PALETTES`)

## Cómo agregar una nueva tool

1. Crear `backend/tools/mi_tool.py` heredando de `BaseTool`:

```python
from tools.base import BaseTool, ToolInput, ToolOutput

class MiTool(BaseTool):
    name = "mi_tool"
    description = "Qué hace esta tool"

    async def run(self, input: ToolInput) -> ToolOutput:
        # implementación
        return ToolOutput(success=True, result="...", source="mi_tool")
```

2. Registrarla en `backend/tools/registry.py`
3. Habilitarla en `backend/agents/scout_agent.py` si debe ser sugerida por el scout

## Tests

```bash
make test
```

Los tests viven en `backend/tests/`. Para tests de nodos del grafo, no es necesario levantar el WebSocket — se puede invocar el nodo directamente con un `DebateState` de prueba.
