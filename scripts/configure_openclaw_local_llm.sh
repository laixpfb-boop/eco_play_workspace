#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${OPENCLAW_CONTAINER:-1Panel-openclaw-fBFy}"
MODEL_ID="${OPENCLAW_LOCAL_MODEL_ID:-Llama-3.2-1B-Instruct-Q4_0.gguf}"
MODEL_NAME="${OPENCLAW_LOCAL_MODEL_NAME:-EcoPlay Local Llama 3.2 1B}"
BASE_URL="${OPENCLAW_LOCAL_BASE_URL:-http://172.17.0.1:8080/v1}"
CONTEXT_WINDOW="${OPENCLAW_LOCAL_CONTEXT_WINDOW:-4096}"
MAX_TOKENS="${OPENCLAW_LOCAL_MAX_TOKENS:-512}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required to configure the OpenClaw container." >&2
  exit 1
fi

if ! sudo -n docker inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "OpenClaw container not found: $CONTAINER" >&2
  exit 1
fi

TAILSCALE_IP="$(command -v tailscale >/dev/null 2>&1 && tailscale ip -4 2>/dev/null | head -1 || true)"
TAILSCALE_ORIGIN=""
if [ -n "$TAILSCALE_IP" ]; then
  TAILSCALE_ORIGIN=", \"http://$TAILSCALE_IP:18789\""
fi

if ! sudo -n docker exec "$CONTAINER" sh -lc 'test -n "${VLLM_API_KEY:-}"'; then
  echo "WARNING: VLLM_API_KEY is not set in the OpenClaw container; model auth may be unavailable." >&2
fi

sudo -n docker exec -i "$CONTAINER" sh -lc "openclaw config patch --stdin" <<PATCH
{
  "gateway": {
    "mode": "local",
    "controlUi": {
      "allowedOrigins": [
        "http://localhost:18789",
        "http://127.0.0.1:18789"$TAILSCALE_ORIGIN
      ]
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "vllm/$MODEL_ID"
      }
    }
  },
  "models": {
    "providers": {
      "vllm": {
        "baseUrl": "$BASE_URL",
        "apiKey": "\${VLLM_API_KEY}",
        "api": "openai-completions",
        "request": {
          "allowPrivateNetwork": true
        },
        "timeoutSeconds": 120,
        "models": [
          {
            "id": "$MODEL_ID",
            "name": "$MODEL_NAME",
            "reasoning": false,
            "input": ["text"],
            "cost": {
              "input": 0,
              "output": 0,
              "cacheRead": 0,
              "cacheWrite": 0
            },
            "contextWindow": $CONTEXT_WINDOW,
            "maxTokens": $MAX_TOKENS
          }
        ]
      }
    }
  }
}
PATCH

sudo -n docker exec "$CONTAINER" sh -lc "openclaw config validate"
sudo -n docker restart "$CONTAINER" >/dev/null
echo "OpenClaw local LLM configured for vllm/$MODEL_ID."
