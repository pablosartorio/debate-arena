# Guía: .env y .env.example

## ¿Por qué dos archivos?

`.env` es el archivo real con tus configuraciones locales. Nunca se sube a git (está en el `.gitignore`) porque puede contener API keys, passwords, configuraciones de prod, etc.

`.env.example` es una plantilla sin valores secretos que sí se sube a git. Sirve para que cualquiera que clone el repo sepa qué variables configurar.

## Flujo de uso

```bash
# Al clonar el repo por primera vez:
cp .env.example .env

# Luego editar .env con tus valores reales
```

## Variables de este proyecto

```bash
OLLAMA_HOST=http://localhost:11434
DATA_DIR=./backend/data
```

Estos valores cambian según el contexto:

| Contexto | OLLAMA_HOST |
|---|---|
| Local sin Docker | `http://localhost:11434` |
| Dentro de docker compose | `http://ollama:11434` (nombre del servicio) |
| Dentro de devcontainer | `http://host.docker.internal:11434` |

El `docker-compose.yml` ya setea `OLLAMA_HOST=http://ollama:11434` directamente como variable de entorno del container, así que en el flujo normal de Docker no necesitás tocar el `.env`.

## ¿Cómo lo lee la app?

En `backend/config.py`:

```python
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
```

`os.getenv("VAR", "default")` lee la variable de entorno si existe, o usa el valor por defecto. FastAPI con uvicorn respeta las variables del sistema, y Docker Compose las inyecta desde el `environment:` del compose file.

## Regla de oro

**Nunca commitear un `.env` real**. Si accidentalmente lo commitiaste, rotar las credenciales inmediatamente (las credenciales en git history se consideran comprometidas incluso si después las borrás).
