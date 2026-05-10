# Guía: devcontainer

## ¿Qué es un devcontainer?

Un devcontainer (Development Container) es una forma de tener tu entorno de desarrollo dentro de un container Docker. En vez de instalar Python, extensiones de VS Code, linters, etc. en tu máquina, todo corre adentro de un container que se define en el código.

Ventajas:
- El entorno es idéntico para todos (no hay "en mi máquina funciona")
- Si rompés el entorno, lo tirás y lo volvés a crear en minutos
- Las extensiones de VS Code se instalan automáticamente
- CI/CD puede usar el mismo entorno

## ¿Cómo funciona en este proyecto?

El archivo `.devcontainer/devcontainer.json` le dice a VS Code:
- Qué container usar (el servicio `backend` del `docker-compose.yml`)
- Dónde está el workspace dentro del container (`/app`)
- Qué extensiones instalar automáticamente
- Qué hacer al crear el container (`postCreateCommand`)

## Setup inicial

**Requisitos:**
1. [VS Code](https://code.visualstudio.com/)
2. [Docker Desktop](https://www.docker.com/products/docker-desktop/) (o Docker Engine en Linux)
3. Extensión [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) en VS Code

**Pasos:**
1. Abrir la carpeta del proyecto en VS Code
2. VS Code va a detectar el `.devcontainer/` y mostrar una notificación → "Reopen in Container"
3. O: `Ctrl+Shift+P` → "Dev Containers: Reopen in Container"
4. VS Code construye el container, instala extensiones, y reabre el editor dentro del container

## Ollama y el devcontainer

**Ollama NO corre dentro del devcontainer.** Corre en el host (tu máquina), fuera del container.

El devcontainer se conecta a Ollama via `http://host.docker.internal:11434`. Esta es una dirección especial de Docker que apunta al host desde dentro del container.

```
[VS Code en devcontainer] → http://host.docker.internal:11434 → [Ollama en tu máquina]
```

**En Linux**, `host.docker.internal` no existe por defecto. Por eso en el `docker-compose.yml` agregamos:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

Esto crea el alias manualmente.

**En Mac y Windows** funciona automáticamente, Docker Desktop lo configura solo.

## ¿Por qué Ollama afuera?

- Ollama consume muchos recursos (descarga modelos de varios GB)
- Si usás GPU, los drivers son complicados de pasar al container
- Ollama ya corre bien en el host via `docker compose up ollama`
- El devcontainer solo necesita acceso HTTP a Ollama, no tiene que controlarlo

## Workflow con devcontainer

```bash
# Terminal fuera de VS Code: levantar Ollama
docker compose up ollama

# VS Code: "Reopen in Container"
# → el backend corre dentro del container
# → Ollama corre en el host
# → se conectan via host.docker.internal
```

## Troubleshooting

**"No se puede conectar a Ollama":**
```bash
# Verificar que Ollama está corriendo en el host
curl http://localhost:11434/api/tags

# Desde dentro del container
curl http://host.docker.internal:11434/api/tags
```

**"El container no arranca":**
- Verificar que Docker está corriendo
- `docker compose down` y volver a intentar

**"Las extensiones no se instalaron":**
- `Ctrl+Shift+P` → "Dev Containers: Rebuild Container"
