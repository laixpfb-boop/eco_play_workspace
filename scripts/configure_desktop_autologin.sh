#!/usr/bin/env bash
set -euo pipefail

AUTOLOGIN_USER="${AUTOLOGIN_USER:-ecoplay}"
AUTOLOGIN_SESSION="${AUTOLOGIN_SESSION:-rpd-labwc}"
LIGHTDM_CONF="/etc/lightdm/lightdm.conf"

if [ ! -f "$LIGHTDM_CONF" ]; then
  echo "LightDM config not found: $LIGHTDM_CONF" >&2
  exit 1
fi

sudo cp "$LIGHTDM_CONF" "$LIGHTDM_CONF.bak.$(date +%Y%m%d%H%M%S)"

sudo python3 - "$LIGHTDM_CONF" "$AUTOLOGIN_USER" "$AUTOLOGIN_SESSION" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
autologin_user = sys.argv[2]
autologin_session = sys.argv[3]

lines = path.read_text(encoding='utf-8').splitlines()
output = []
in_seat = False
seat_seen = False
seen = {
    'autologin-user': False,
    'autologin-user-timeout': False,
    'autologin-session': False,
    'user-session': False,
}

values = {
    'autologin-user': autologin_user,
    'autologin-user-timeout': '0',
    'autologin-session': autologin_session,
    'user-session': autologin_session,
}


def append_missing(target):
    for key, value in values.items():
        if not seen[key]:
            target.append(f'{key}={value}')
            seen[key] = True


for line in lines:
    stripped = line.strip()
    if stripped.startswith('[') and stripped.endswith(']'):
        if in_seat:
            append_missing(output)
        in_seat = stripped == '[Seat:*]'
        seat_seen = seat_seen or in_seat
        output.append(line)
        continue

    if in_seat:
        uncommented = stripped.lstrip('#').strip()
        key = uncommented.split('=', 1)[0].strip() if '=' in uncommented else ''
        if key in values:
            output.append(f'{key}={values[key]}')
            seen[key] = True
            continue

    output.append(line)

if in_seat:
    append_missing(output)

if not seat_seen:
    output.extend([
        '',
        '[Seat:*]',
    ])
    append_missing(output)

path.write_text('\n'.join(output) + '\n', encoding='utf-8')
PY

sudo systemctl restart lightdm.service || true

echo "Desktop autologin configured for user '$AUTOLOGIN_USER' with session '$AUTOLOGIN_SESSION'."
echo "A reboot is recommended to verify the boot path."
