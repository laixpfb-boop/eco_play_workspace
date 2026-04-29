#!/usr/bin/env bash
set -u

WORKSPACE="/home/ecoplay/eco_play_workspace"
LOG_DIR="$WORKSPACE/logs"
STATUS_FILE="$LOG_DIR/last_start_status.txt"
LOCK_FILE="/tmp/ecoplay-start.lock"

BACKEND_PORT="5001"
FRONTEND_PORT="5173"
LLM_PORT="8080"
OPENCLAW_CONTAINER="1Panel-openclaw-fBFy"
LLAMA_SERVER="/home/ecoplay/llama.cpp/build/bin/llama-server"
LLAMA_MODEL="/home/ecoplay/llama.cpp/Llama-3.2-1B-Instruct-Q4_0.gguf"
CLOUDFLARED="/home/ecoplay/.local/bin/cloudflared"

mkdir -p "$LOG_DIR"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "EcoPlay startup is already running. Check $STATUS_FILE"
  exit 0
fi

exec > >(tee -a "$STATUS_FILE") 2>&1

echo
echo "========== EcoPlay startup $(date -Is) =========="

run_bg() {
  local name="$1"
  local workdir="$2"
  local logfile="$3"
  shift 3
  mkdir -p "$(dirname "$logfile")"
  (
    cd "$workdir" || exit 1
    exec "$@"
  ) > "$logfile" 2>&1 < /dev/null &
  echo "$name started with pid $!"
}

has_process() {
  pgrep -u "$(id -u)" -f "$1" >/dev/null 2>&1
}

port_listening() {
  ss -ltn 2>/dev/null | grep -q ":$1 "
}

wait_for_port() {
  local port="$1"
  local label="$2"
  local tries="${3:-20}"
  for _ in $(seq 1 "$tries"); do
    if port_listening "$port"; then
      echo "$label is listening on port $port"
      return 0
    fi
    sleep 1
  done
  echo "WARNING: $label did not listen on port $port within ${tries}s"
  return 1
}

start_openclaw() {
  echo "--- OpenClaw ---"
  if ! command -v docker >/dev/null 2>&1; then
    echo "WARNING: docker is not installed; cannot start OpenClaw."
    return 0
  fi
  if ! sudo -n timeout 20 docker inspect "$OPENCLAW_CONTAINER" >/dev/null 2>&1; then
    echo "WARNING: OpenClaw container $OPENCLAW_CONTAINER was not found."
    return 0
  fi
  sudo -n timeout 20 docker update --restart unless-stopped "$OPENCLAW_CONTAINER" >/dev/null 2>&1 || true
  if sudo -n timeout 20 docker inspect -f '{{.State.Running}}' "$OPENCLAW_CONTAINER" 2>/dev/null | grep -q true; then
    echo "OpenClaw container is already running."
  else
    sudo -n timeout 30 docker start "$OPENCLAW_CONTAINER" || echo "WARNING: OpenClaw container start timed out or failed."
    echo "OpenClaw container start requested."
  fi
}

start_backend() {
  echo "--- Backend ---"
  if has_process "python3 backend/src/app.py"; then
    echo "Backend process is already running."
  else
    run_bg "backend" "$WORKSPACE" "$LOG_DIR/backend.log" \
      bash -lc "source venv/bin/activate && exec python3 backend/src/app.py"
  fi
  wait_for_port "$BACKEND_PORT" "Backend" 20 || true
}

start_frontend() {
  echo "--- Frontend ---"
  local frontend_dir="$WORKSPACE/frontend/EcoPlay Campus Energy App"
  if has_process "vite --host 0.0.0.0 --port $FRONTEND_PORT"; then
    echo "Frontend process is already running."
  else
    run_bg "frontend" "$frontend_dir" "$LOG_DIR/frontend.log" \
      npm run dev -- --host 0.0.0.0 --port "$FRONTEND_PORT"
  fi
  wait_for_port "$FRONTEND_PORT" "Frontend" 20 || true
}

start_llm() {
  echo "--- LLM ---"
  if [ ! -x "$LLAMA_SERVER" ] || [ ! -f "$LLAMA_MODEL" ]; then
    echo "WARNING: llama-server or model not found; skipping LLM."
    return 0
  fi
  if has_process "llama-server.*Llama-3.2-1B-Instruct-Q4_0.gguf"; then
    echo "LLM server is already running."
  else
    run_bg "llm" "/home/ecoplay/llama.cpp" "$LOG_DIR/llama-server.log" \
      "$LLAMA_SERVER" --host 0.0.0.0 --port "$LLM_PORT" \
      -m "$LLAMA_MODEL" -c 2048 --threads 4
  fi
  wait_for_port "$LLM_PORT" "LLM server" 60 || true
}

start_lark_tunnel() {
  echo "--- Lark callback tunnel ---"
  if has_process "cloudflared.*127.0.0.1:$BACKEND_PORT"; then
    echo "Cloudflare tunnel is already running."
    grep -Eo 'https://[^ ]+\.trycloudflare\.com' "$LOG_DIR/cloudflared.log" 2>/dev/null | tail -1 || true
    return 0
  fi
  if [ ! -x "$CLOUDFLARED" ]; then
    echo "cloudflared is not installed; skipping callback tunnel."
    return 0
  fi
  if [ -f "/home/ecoplay/.cloudflared/config.yml" ] || [ -f "/home/ecoplay/.cloudflared/config.yaml" ]; then
    run_bg "cloudflared named tunnel" "/home/ecoplay" "$LOG_DIR/cloudflared.log" \
      "$CLOUDFLARED" tunnel run
  else
    run_bg "cloudflared quick tunnel" "/home/ecoplay" "$LOG_DIR/cloudflared.log" \
      "$CLOUDFLARED" tunnel --url "http://127.0.0.1:$BACKEND_PORT"
    sleep 8
    local public_url
    public_url="$(grep -Eo 'https://[^ ]+\.trycloudflare\.com' "$LOG_DIR/cloudflared.log" 2>/dev/null | tail -1 || true)"
    if [ -n "$public_url" ]; then
      echo "Temporary Lark callback URL: $public_url/api/lark/events"
    fi
  fi
}

show_status() {
  echo "--- Status ---"
  ss -ltnp 2>/dev/null | grep -E ":(5001|5173|8080|18789|20241) " || true
  local lan_ip
  lan_ip="$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^192\.168\.|^10\.|^172\.(1[6-9]|2[0-9]|3[0-1])\.' | grep -vE '^172\.1[78]\.' | head -1 || true)"
  local tailscale_ip
  tailscale_ip="$(command -v tailscale >/dev/null 2>&1 && tailscale ip -4 2>/dev/null | head -1 || true)"
  if [ -n "$lan_ip" ]; then
    echo "Frontend LAN: http://$lan_ip:$FRONTEND_PORT/"
    echo "Backend LAN:  http://$lan_ip:$BACKEND_PORT/"
    echo "LLM LAN:      http://$lan_ip:$LLM_PORT/"
  fi
  if [ -n "$tailscale_ip" ]; then
    echo "Frontend Tailscale: http://$tailscale_ip:$FRONTEND_PORT/"
    echo "Backend Tailscale:  http://$tailscale_ip:$BACKEND_PORT/"
    echo "LLM Tailscale:      http://$tailscale_ip:$LLM_PORT/"
  fi
  echo "Logs:     $LOG_DIR"
}

start_openclaw
start_backend
start_frontend
start_llm
start_lark_tunnel
show_status

echo "========== EcoPlay startup finished $(date -Is) =========="

if [ "${1:-}" = "--desktop" ]; then
  echo
  read -r -p "Press Enter to close this window..."
fi
