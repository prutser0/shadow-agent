"""RunPod serverless handler — proxies requests to local Ollama instance."""
import os
import time
import requests
import runpod

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL_TAG = os.environ.get("MODEL_TAG", "deckard-40b")


def wait_for_ollama(timeout=120):
    """Block until Ollama is ready (model loaded)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
            if r.ok and any(m["name"].startswith(MODEL_TAG) for m in r.json().get("models", [])):
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def handler(event):
    """Handle a serverless invocation.

    Input formats accepted:
      {"prompt": "...", "system": "..."}                     — simple
      {"messages": [{"role":"...","content":"..."}], ...}    — OpenAI-style
      {"openai": {full OpenAI chat completion payload}}      — passthrough
    """
    if not wait_for_ollama():
        return {"error": "Ollama not ready within timeout"}

    inp = event.get("input", {})

    # Passthrough mode (full OpenAI payload)
    if "openai" in inp:
        payload = inp["openai"]
        payload.setdefault("model", MODEL_TAG)
        r = requests.post(f"{OLLAMA_URL}/v1/chat/completions", json=payload, timeout=600)
        return r.json()

    # Messages mode
    if "messages" in inp:
        payload = {
            "model": inp.get("model", MODEL_TAG),
            "messages": inp["messages"],
            "stream": False,
            "temperature": inp.get("temperature", 0.7),
            "max_tokens": inp.get("max_tokens", 4096),
        }
        r = requests.post(f"{OLLAMA_URL}/v1/chat/completions", json=payload, timeout=600)
        return r.json()

    # Simple prompt mode
    prompt = inp.get("prompt", "")
    system = inp.get("system")
    if not prompt:
        return {"error": "missing 'prompt' or 'messages' in input"}

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": MODEL_TAG,
        "messages": messages,
        "stream": False,
        "temperature": inp.get("temperature", 0.7),
        "max_tokens": inp.get("max_tokens", 4096),
    }
    r = requests.post(f"{OLLAMA_URL}/v1/chat/completions", json=payload, timeout=600)
    data = r.json()
    # Extract just the text for convenience
    try:
        return {
            "output": data["choices"][0]["message"]["content"],
            "raw": data,
        }
    except (KeyError, IndexError):
        return {"error": "unexpected ollama response", "raw": data}


if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
