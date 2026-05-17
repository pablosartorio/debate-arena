#!/usr/bin/env bash
# Descarga los modelos necesarios en el contenedor Ollama.
# Ejecutar una sola vez después del primer `docker compose up`.
#
# Uso: ./init_models.sh [modelo]
#      ./init_models.sh              → descarga llama3.2 (default)
#      ./init_models.sh mistral      → descarga mistral

set -e

MODEL="${1:-llama3.2}"

echo "Descargando modelo: $MODEL ..."
docker compose exec ollama ollama pull "$MODEL"
echo "Listo. Podés abrir http://localhost:8080"
