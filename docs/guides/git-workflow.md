# Guía: Git workflow y estrategia de ramas

## Estructura de ramas

```
main        ← siempre funciona, es lo que mostrás
develop     ← acumulación de features terminadas
feature/*   ← donde trabajás día a día
```

## ¿Por qué esta estructura?

**`main` siempre estable**: si alguien clona el repo, espera que funcione. Si tenés algo a medias, no debería estar en main.

**`develop` como buffer**: las features se integran acá primero. Si una feature rompe algo, lo detectás antes de pasar a main.

**`feature/*` aisladas**: cada cambio concreto vive en su propia rama. Podés trabajar en varias cosas en paralelo, pausar una, y retomar otra.

## Flujo de trabajo

```bash
# 1. Partir siempre desde develop
git checkout develop
git pull origin develop

# 2. Crear rama de feature
git checkout -b feature/moderador-scoring

# 3. Trabajar, hacer commits chicos
git add backend/agents/moderator_agent.py
git commit -m "feat: add hallucination score to moderator output"

# 4. Cuando está listo, mergear a develop
git checkout develop
git merge feature/moderador-scoring

# 5. Pushear
git push origin develop

# 6. Borrar la rama (opcional, para mantener limpio)
git branch -d feature/moderador-scoring
```

## Tags semánticos

Los tags marcan hitos del proyecto. En vez de solo tener versiones numéricas, los tags descriptivos cuentan la historia del proyecto:

```bash
git tag v0.1-graph-skeleton    # primer grafo funcionando
git tag v0.2-persistence       # SQLite integrado
git tag v0.3-moderation        # moderador funcionando
git push --tags
```

En GitHub, los tags aparecen como "Releases" y podés adjuntarles notas de release.

## Mensajes de commit

Usar el prefijo convencional:

| Prefijo | Cuándo usarlo |
|---|---|
| `feat:` | nueva funcionalidad |
| `fix:` | bug fix |
| `refactor:` | cambio que no agrega ni quita funcionalidad |
| `docs:` | solo documentación |
| `test:` | solo tests |
| `chore:` | tareas de mantenimiento (deps, config) |

Ejemplos:
```
feat: add web search tool to debater agents
fix: prevent sentinel queue leak on WebSocket disconnect
docs: add ADR for LangGraph decision
refactor: extract scoring logic to moderator_agent
```

## Commits chicos vs grandes

**Chicos**: un commit = un cambio lógico. Más fácil de revertir si algo sale mal. Más fácil de entender en el historial.

**Grandes**: tentador cuando hacés muchas cosas a la vez, pero difícil de debuggear después. Si tenés 20 archivos cambiados en un commit, es difícil saber qué cambio específico rompió algo.

## Con asistentes AI (Claude, Codex)

Los asistentes tienden a hacer cambios amplios. Conviene:
- Revisar el diff antes de commitear
- Usar branches de feature para cambios de asistentes
- No dejar que mergeen a main/develop directamente
- Commits chicos, squash si hay demasiados "fix typo" intermedios

## .gitignore

El `.gitignore` ya cubre los casos comunes del proyecto. Lo más importante que excluye:
- `backend/data/` → base de datos SQLite (runtime, no va a git)
- `.env` → variables de entorno (pueden tener secrets)
- `__pycache__/` → archivos compilados de Python
- `.venv/` → entorno virtual Python local
