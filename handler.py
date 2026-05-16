"""RunPod serverless handler — starts immediately, sets up Ollama in background.

Pattern: handler starts BEFORE Ollama is ready so RunPod sees the worker as healthy
(heartbeat goes out). First request blocks until model is loaded (can take 5-10min
on cold worker with no network volume; near-instant if model is cached).
"""
import os
import subprocess
import threading
import time

import requests
import runpod

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL_TAG = os.environ.get("MODEL_TAG", "deckard-40b")
MODEL_REPO = os.environ.get("MODEL_REPO", "")
MODEL_PATTERN = os.environ.get("MODEL_PATTERN", "*Q4_K_M*.gguf")
MODELS_DIR = os.environ.get("OLLAMA_MODELS", "/workspace/models")
MODELFILE_TPL = "/opt/Modelfile.tpl"

# Long timeout for first cold start (model download + load can take 10+ min)
WAIT_TIMEOUT_SEC = int(os.environ.get("WAIT_TIMEOUT_SEC", "1800"))

# Tracks Ollama readiness — handler() blocks on this for first call
_ready_event = threading.Event()
_setup_error = [None]  # list so background thread can mutate


def _log(msg: str) -> None:
    print(f"[handler] {msg}", flush=True)


def _shell(cmd: str, check: bool = True, timeout: int | None = None) -> subprocess.CompletedProcess:
    _log(f"$ {cmd}")
    result = subprocess.run(cmd, shell=True, timeout=timeout,
                            capture_output=True, text=True)
    if result.stdout:
        _log(f"stdout: {result.stdout[-500:]}")
    if result.stderr:
        _log(f"stderr: {result.stderr[-500:]}")
    if check and result.returncode != 0:
        raise RuntimeError(
            f"cmd failed (exit {result.returncode}): {cmd}\n"
            f"stderr: {result.stderr[-1000:]}\n"
            f"stdout: {result.stdout[-500:]}"
        )
    return result


def _ollama_alive() -> bool:
    try:
        return requests.get(f"{OLLAMA_URL}/api/tags", timeout=2).ok
    except Exception:
        return False


def _model_loaded() -> bool:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        return r.ok and any(m["name"].startswith(MODEL_TAG) for m in r.json().get("models", []))
    except Exception:
        return False


def _setup_ollama() -> None:
    """Background thread: start ollama, download model if needed, import, prewarm."""
    try:
        os.makedirs(MODELS_DIR, exist_ok=True)

        _log("starting ollama daemon")
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Wait for daemon HTTP
        deadline = time.time() + 60
        while time.time() < deadline and not _ollama_alive():
            time.sleep(1)
        if not _ollama_alive():
            raise RuntimeError("ollama daemon failed to start")

        if not _model_loaded():
            _log(f"model {MODEL_TAG} not loaded — checking volume for GGUF")
            gguf = ""
            for root, _, files in os.walk(MODELS_DIR):
                for f in files:
                    if "Q4_K_M" in f and f.endswith(".gguf"):
                        gguf = os.path.join(root, f)
                        break
                if gguf:
                    break

            if not gguf:
                _log(f"GGUF not in volume — downloading {MODEL_REPO} (~24GB, one-time)")
                target = os.path.join(MODELS_DIR, "_gguf")
                _shell(
                    f'hf download "{MODEL_REPO}" '
                    f'--include "{MODEL_PATTERN}" --local-dir "{target}"',
                    timeout=1800,
                )
                for root, _, files in os.walk(target):
                    for f in files:
                        if "Q4_K_M" in f and f.endswith(".gguf"):
                            gguf = os.path.join(root, f)
                            break

            if not gguf:
                raise RuntimeError("no GGUF found after download")

            _log(f"importing model from {gguf}")
            with open(MODELFILE_TPL) as fp:
                tpl = fp.read().replace("__MODEL_GGUF_PATH__", gguf)
            with open("/tmp/Modelfile", "w") as fp:
                fp.write(tpl)
            _shell(f'ollama create "{MODEL_TAG}" -f /tmp/Modelfile', timeout=300)

        # Pre-warm so first user request is fast
        _log("pre-warming model")
        try:
            requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": MODEL_TAG, "prompt": "hi", "stream": False},
                timeout=120,
            )
        except Exception as e:
            _log(f"pre-warm failed (non-fatal): {e}")

        _log("ready to serve requests")
        _ready_event.set()

    except Exception as e:
        _setup_error[0] = str(e)
        _log(f"SETUP FAILED: {e}")
        _ready_event.set()  # unblock handler so it can return error


def handler(event):
    """Process a single request. Blocks if Ollama not yet ready."""
    if not _ready_event.is_set():
        _log("waiting for Ollama setup to finish...")
        if not _ready_event.wait(timeout=WAIT_TIMEOUT_SEC):
            return {"error": f"Ollama setup timed out after {WAIT_TIMEOUT_SEC}s"}
    if _setup_error[0]:
        return {"error": f"Ollama setup failed: {_setup_error[0]}"}

    inp = event.get("input", {})

    if "openai" in inp:
        payload = inp["openai"]
        payload.setdefault("model", MODEL_TAG)
    elif "messages" in inp:
        payload = {
            "model": inp.get("model", MODEL_TAG),
            "messages": inp["messages"],
            "stream": False,
            "temperature": inp.get("temperature", 0.7),
            "max_tokens": inp.get("max_tokens", 4096),
        }
    else:
        prompt = inp.get("prompt", "")
        if not prompt:
            return {"error": "missing 'prompt' or 'messages' in input"}
        messages = []
        if inp.get("system"):
            messages.append({"role": "system", "content": inp["system"]})
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
    try:
        return {
            "output": data["choices"][0]["message"]["content"],
            "raw": data,
        }
    except (KeyError, IndexError):
        return {"error": "unexpected ollama response", "raw": data}


# Start Ollama setup in background BEFORE blocking on runpod.serverless.start()
_setup_thread = threading.Thread(target=_setup_ollama, daemon=True)
_setup_thread.start()

if __name__ == "__main__":
    runpod.serverless.start({"handler": handler})
