#!/usr/bin/env bash
set -euo pipefail

VNC_HOST="${VNC_HOST:-100.123.75.62}"
VNC_PORT="${VNC_PORT:-5900}"
VNC_USERNAME="${VNC_USERNAME:-ecoplay}"
WORKSPACE="${WORKSPACE:-/home/ecoplay/eco_play_workspace}"
SECRET_DIR="$WORKSPACE/secrets"
PASSWORD_FILE="$SECRET_DIR/vnc_credentials.txt"

if ! command -v wayvnc >/dev/null 2>&1; then
  echo "wayvnc is not installed. Install it before running this script." >&2
  exit 1
fi

password="${VNC_PASSWORD:-}"
if [ -z "$password" ]; then
  password="$(python3 -c 'import secrets, string; chars = string.ascii_letters + string.digits; print("".join(secrets.choice(chars) for _ in range(16)))')"
fi

mkdir -p "$SECRET_DIR"
chmod 700 "$SECRET_DIR"

{
  echo "VNC host: $VNC_HOST"
  echo "VNC port: $VNC_PORT"
  echo "VNC username: $VNC_USERNAME"
  echo "VNC password: $password"
  echo "Created: $(date -Is)"
} > "$PASSWORD_FILE"
chmod 600 "$PASSWORD_FILE"

if [ -f /etc/wayvnc/config ]; then
  sudo cp /etc/wayvnc/config "/etc/wayvnc/config.bak.$(date +%Y%m%d%H%M%S)"
fi

sudo tee /etc/wayvnc/config >/dev/null <<CONFIG
use_relative_paths=true
address=::
port=$VNC_PORT
enable_auth=true
enable_pam=false
username=$VNC_USERNAME
password=$password
private_key_file=tls_key.pem
certificate_file=tls_cert.pem
rsa_private_key_file=rsa_key.pem
CONFIG

sudo chown root:vnc /etc/wayvnc/config
sudo chmod 640 /etc/wayvnc/config
sudo systemctl daemon-reload
sudo systemctl enable wayvnc.service >/dev/null
sudo systemctl restart wayvnc.service

echo "VNC service configured and restarted."
echo "Connect to $VNC_HOST:$VNC_PORT with username $VNC_USERNAME."
echo "Credentials stored at $PASSWORD_FILE."
