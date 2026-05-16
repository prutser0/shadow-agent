#!/bin/bash
set -e

mkdir -p "$OLLAMA_MODELS" "$HF_HOME"

# Start ollama in background
ollama serve &
OLLAMA_PID=$!

# Wait for Ollama to be ready
until curl -sf http://localhost:11434/api/tags > /dev/null; do
    sleep 1
done

# Check if model already present in Ollama
if ! ollama list 2>/dev/null | grep -q "^${MODEL_TAG}"; then
    echo "[entrypoint] Model ${MODEL_TAG} not found, importing..."

    GGUF_PATH=$(find "$OLLAMA_MODELS" -maxdepth 3 -name "*Q4_K_M*.gguf" 2>/dev/null | head -1)

    if [ -z "$GGUF_PATH" ]; then
        echo "[entrypoint] GGUF not in volume — downloading from HF (~24GB, one-time)..."
        huggingface-cli download "$MODEL_REPO" \
            --include "$MODEL_PATTERN" \
            --local-dir "$OLLAMA_MODELS/_gguf"
        GGUF_PATH=$(find "$OLLAMA_MODELS/_gguf" -name "*Q4_K_M*.gguf" | head -1)
    fi

    if [ -z "$GGUF_PATH" ]; then
        echo "[entrypoint] ERROR: no GGUF file found after download"
        exit 1
    fi

    echo "[entrypoint] Creating Ollama model from $GGUF_PATH"
    sed "s|__MODEL_GGUF_PATH__|$GGUF_PATH|" /opt/Modelfile.tpl > /tmp/Modelfile
    ollama create "$MODEL_TAG" -f /tmp/Modelfile
    echo "[entrypoint] Model ready: $MODEL_TAG"
else
    echo "[entrypoint] Model ${MODEL_TAG} already loaded"
fi

# Pre-warm the model so first user request is fast
echo "[entrypoint] Pre-warming model..."
curl -sS -X POST http://localhost:11434/api/generate \
    -d "{\"model\":\"${MODEL_TAG}\",\"prompt\":\"hi\",\"stream\":false}" > /dev/null || true

# Start RunPod handler (foreground)
echo "[entrypoint] Starting RunPod handler"
exec python3 /opt/handler.py
