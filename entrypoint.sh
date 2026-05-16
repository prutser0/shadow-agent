#!/bin/bash
# handler.py spawns ollama + downloads model in background thread.
# RunPod heartbeat starts immediately — no init timeout race.
set -e
exec python3 /opt/handler.py
