#!/usr/bin/env bash
set -u

URL="http://127.0.0.1:5173/user?building=Sustainability%20Office"
BRIGHTNESS="${ECOPLAY_SCREEN_BRIGHTNESS:-0.7}"
SCALE="${ECOPLAY_FRONTEND_SCALE:-0.6}"
BRIGHTNESS_REFRESH_SECONDS="${ECOPLAY_BRIGHTNESS_REFRESH_SECONDS:-5}"

export DISPLAY="${DISPLAY:-:0}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

set_display_brightness() {
  command -v xrandr >/dev/null 2>&1 || return 0

  local output
  output="$(xrandr --query 2>/dev/null | awk '$2 == "connected" {print $1; exit}')"
  [ -n "$output" ] || return 1

  xrandr --output "$output" --brightness "$BRIGHTNESS" >/dev/null 2>&1
}

/usr/bin/chromium \
  --password-store=basic \
  --no-first-run \
  --disable-sync \
  --app="$URL" \
  --force-device-scale-factor="$SCALE" \
  --start-fullscreen \
  --window-position=0,0 \
  --window-size=1920,1080 &

chromium_pid="$!"

while kill -0 "$chromium_pid" >/dev/null 2>&1 || pgrep -u "$(id -u)" -x chromium >/dev/null 2>&1; do
  set_display_brightness || true
  sleep "$BRIGHTNESS_REFRESH_SECONDS"
done

wait "$chromium_pid" 2>/dev/null || true
