FROM ollama/ollama:latest

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --break-system-packages --no-cache-dir huggingface-hub

ENV OLLAMA_HOST=0.0.0.0:11434 \
    OLLAMA_MODELS=/workspace/models \
    HF_HOME=/workspace/hf-cache \
    MODEL_REPO=DavidAU/Qwen3.6-40B-Claude-4.6-Opus-Deckard-Heretic-Uncensored-Thinking-NEO-CODE-Di-IMatrix-MAX-GGUF \
    MODEL_PATTERN=*Q4_K_M*.gguf \
    MODEL_TAG=deckard-40b

COPY Modelfile.tpl /opt/Modelfile.tpl
COPY entrypoint.sh /opt/entrypoint.sh
RUN chmod +x /opt/entrypoint.sh

EXPOSE 11434
ENTRYPOINT ["/opt/entrypoint.sh"]
