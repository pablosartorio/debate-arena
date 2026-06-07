# Guía: pyproject.toml y ruff

## ¿Qué es pyproject.toml?

Es el archivo de configuración moderno de proyectos Python. Antes cada herramienta tenía su propio archivo de configuración (`setup.cfg`, `setup.py`, `.flake8`, `pytest.ini`, etc.). `pyproject.toml` unifica todo en un solo lugar.

En este proyecto lo usamos para:
- Declarar las dependencias del backend (sección `[project]`)
- Configurar `ruff` (sección `[tool.ruff]`)
- Configurar `pytest` (sección `[tool.pytest.ini_options]`)

```toml
[project]                  ← dependencias y metadatos
[tool.ruff]                ← configuración de ruff
[tool.pytest.ini_options]  ← configuración de pytest
```

Las dependencias se instalan en la imagen Docker con [`uv`](https://github.com/astral-sh/uv) (un gestor de paquetes Python escrito en Rust, mucho más rápido que `pip`):

```dockerfile
COPY pyproject.toml .
RUN uv pip install --system --no-cache -r pyproject.toml
```

## ¿Qué es ruff?

Ruff es una herramienta de Python que hace dos cosas:
1. **Linter**: analiza el código y señala errores o malas prácticas
2. **Formatter**: reformatea el código automáticamente (como black, pero más rápido)

Está escrito en Rust, es muy rápido, y reemplaza a flake8 + black + isort en una sola herramienta.

## ¿Qué detecta ruff en este proyecto?

```toml
select = ["E", "F", "I", "UP"]
```

| Código | Qué detecta | Ejemplo |
|---|---|---|
| `E` | Errores de estilo PEP8 | líneas demasiado largas, espacios mal puestos |
| `F` | Errores lógicos | variables definidas pero nunca usadas, imports no usados |
| `I` | Orden de imports | imports desordenados (debería ir stdlib antes que third-party) |
| `UP` | Modernización | usar `list[str]` en vez de `List[str]` (Python 3.9+) |

## ¿Cómo se usa?

```bash
make lint      # solo chequea, no modifica nada
make format    # modifica automáticamente
```

O directamente:
```bash
ruff check backend/       # reporta errores
ruff check backend/ --fix  # corrige los que puede automáticamente
ruff format backend/       # formatea
```

## ¿Por qué vale la pena?

Porque los errores que detecta `F` (variables sin usar, imports sin usar) son frecuentes durante refactors y pasan desapercibidos. Y el formatter asegura que todo el código tenga el mismo estilo sin discusiones.

El CI puede rechazar automáticamente PRs que fallen el lint, evitando que entren errores descuidados.

## ¿Tengo que instalar ruff?

Para correrlo fuera de Docker: `uv pip install ruff` (o `pip install ruff` si no tenés uv).

Dentro del devcontainer ya está instalado automáticamente (la extensión VS Code de ruff lo incluye).
