#!/usr/bin/env bash

set -euo pipefail

APP_ROOT="/opt/eco_play_workspace"
WEB_ROOT="/var/www/eco_play_workspace/frontend-dist"
SERVICE_NAME="ecoplay-backend"
NGINX_CONF_SOURCE="$APP_ROOT/deploy/nginx-lico-fun.conf"
NGINX_CONF_TARGET="/etc/nginx/conf.d/ecoplay.conf"
SERVICE_SOURCE="$APP_ROOT/deploy/ecoplay-backend.service"
SERVICE_TARGET="/etc/systemd/system/${SERVICE_NAME}.service"

echo "==> EcoPlay deployment for lico.fun"

if [ ! -d "$APP_ROOT" ]; then
  echo "Project not found at $APP_ROOT"
  echo "Copy or clone the repo there first."
  exit 1
fi

cd "$APP_ROOT"

echo "==> Creating Python virtual environment"
python3 -m venv venv
source venv/bin/activate

echo "==> Installing backend dependencies"
pip install --upgrade pip
pip install -r backend/requirements.txt

echo "==> Ensuring backend .env exists"
if [ ! -f backend/.env ] && [ -f backend/.env.example ]; then
  cp backend/.env.example backend/.env
  echo "Created backend/.env from backend/.env.example"
  echo "Edit backend/.env if you want to enable OpenAI smart chat."
fi

echo "==> Installing frontend dependencies"
cd "$APP_ROOT/frontend/EcoPlay Campus Energy App"
npm install

echo "==> Building frontend"
npm run build

echo "==> Copying frontend build to $WEB_ROOT"
mkdir -p "$WEB_ROOT"
cp -R dist/* "$WEB_ROOT/"

echo "==> Installing systemd backend service"
cp "$SERVICE_SOURCE" "$SERVICE_TARGET"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"
systemctl --no-pager --full status "$SERVICE_NAME" || true

echo "==> Installing Nginx config"
cp "$NGINX_CONF_SOURCE" "$NGINX_CONF_TARGET"
nginx -t
systemctl reload nginx

echo
echo "Deployment finished."
echo
echo "Next recommended step for HTTPS:"
echo "  certbot --nginx -d lico.fun -d www.lico.fun"
echo
echo "Public QR URL:"
echo "  https://lico.fun/user?building=Sustainability%20Office&room=Sustainability%20Office"
echo
echo "Operator URL:"
echo "  https://lico.fun/settings"
