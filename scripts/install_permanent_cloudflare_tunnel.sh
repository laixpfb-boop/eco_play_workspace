#!/usr/bin/env bash
set -euo pipefail

TOKEN="${1:-}"
if [ -z "$TOKEN" ]; then
  cat <<'USAGE'
Usage:
  ./install_permanent_cloudflare_tunnel.sh <cloudflare-tunnel-token>

Create a named Cloudflare Tunnel in Cloudflare Zero Trust first.
Set its public hostname to forward to:
  http://127.0.0.1:5001

Then pass the tunnel token here. The callback URL for Lark will be:
  https://<your-public-hostname>/api/lark/events
USAGE
  exit 2
fi

HOME_DIR="/home/ecoplay"
CLOUDFLARED="$HOME_DIR/.local/bin/cloudflared"
SYSTEMD_DIR="$HOME_DIR/.config/systemd/user"
SERVICE_FILE="$SYSTEMD_DIR/ecoplay-cloudflared.service"

mkdir -p "$HOME_DIR/.local/bin" "$SYSTEMD_DIR" "$HOME_DIR/eco_play_workspace/logs"

if [ ! -x "$CLOUDFLARED" ]; then
  wget -q -O "$CLOUDFLARED" https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64
  chmod +x "$CLOUDFLARED"
fi

cat > "$SERVICE_FILE" <<SERVICE
[Unit]
Description=EcoPlay permanent Cloudflare Tunnel
After=network-online.target

[Service]
Type=simple
ExecStart=$CLOUDFLARED tunnel --no-autoupdate run --token $TOKEN
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
SERVICE

systemctl --user daemon-reload
systemctl --user enable ecoplay-cloudflared.service
systemctl --user restart ecoplay-cloudflared.service

pkill -f "cloudflared tunnel --url http://127.0.0.1:5001" 2>/dev/null || true

echo "Permanent Cloudflare tunnel service installed and started."
echo "Check it with:"
echo "  systemctl --user status ecoplay-cloudflared.service"
