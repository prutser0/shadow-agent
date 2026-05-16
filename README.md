# shadow-agent

Stateless LLM endpoint for delegation from hermes-agents (Lies, Zina) when their primary model refuses legitimate business automation tasks.

## Stack

- **Model**: DavidAU/Qwen3.6-40B-Claude-4.6-Opus-Deckard-Heretic-Uncensored-Thinking-NEO-CODE (Q4_K_M GGUF, ~24GB)
- **Runtime**: Ollama on RunPod Serverless (custom Docker image)
- **GPU**: RTX A6000 48GB (Secure Cloud)
- **API**: OpenAI-compatible at `/v1/chat/completions`

## How it works

1. GitHub Actions builds a thin Docker image (~2GB) with Ollama + entrypoint
2. On first RunPod worker start: entrypoint downloads model from HF into mounted Network Volume (~3min one-time)
3. Subsequent cold starts: model loads from cache (~30s)
4. Hermes-agents call `/v1/chat/completions` via tool `delegate_to_shadow(prompt)`

## RunPod setup

After GHA push completes (image at `ghcr.io/<owner>/shadow-agent:latest`):

1. RunPod → Serverless → New Endpoint
2. Container Image: `ghcr.io/<owner>/shadow-agent:latest`
3. Container Disk: 20 GB (image + tmp)
4. Network Volume: 50 GB mounted at `/workspace` (persists model across cold starts)
5. GPU: 1x RTX A6000 (48GB) — Secure Cloud
6. Workers Min: 0 (scale-to-zero)
7. Workers Max: 2 (cap concurrency)
8. Idle Timeout: 300s (kill workers after 5min idle)
9. Expose HTTP: port 11434
10. Save → get endpoint URL `https://api.runpod.ai/v2/<endpoint-id>/run` and `/runsync`

## Cost (estimated)

- Idle: $0 (scale-to-zero)
- Active: ~$0.0008/sec on A6000 Secure
- 100 calls/dag @ 30s avg: ~$72/mo
- 500 calls/dag @ 30s avg: ~$360/mo

## Caveats

- Model is uncensored — only expose to trusted callers (tailnet ACL + API key auth)
- Thinking mode CoT can be verbose — `num_predict` capped in Modelfile
- First call after long idle: ~30-60s cold start

## Files

- `Dockerfile` — Ollama + tooling
- `Modelfile.tpl` — Ollama model config template (path filled at runtime)
- `entrypoint.sh` — Boot logic: download model if missing, import, serve
- `.github/workflows/build.yml` — Build + push to ghcr.io on main push
