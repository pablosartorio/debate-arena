.PHONY: dev stop backend lint format test logs

# Levanta todos los servicios (Ollama + backend) con Docker Compose
dev:
	docker compose up --build

# Solo el backend, sin reconstruir imagen
up:
	docker compose up

# Detiene todos los servicios
stop:
	docker compose down

# Corre el backend localmente sin Docker (requiere Ollama corriendo en localhost)
backend:
	cd backend && uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# Chequea errores de estilo y lógica con ruff
lint:
	ruff check backend/

# Formatea el código automáticamente con ruff
format:
	ruff format backend/

# Corre los tests
test:
	pytest

# Muestra los logs del backend en tiempo real
logs:
	docker compose logs -f backend
