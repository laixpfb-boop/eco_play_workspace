import os
import sys
from datetime import datetime

from dotenv import load_dotenv

import comfort_notifications
import db
import lark_commands
import sensor


BASE_DIR = os.path.dirname(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))


def _read_primary_sensor_line():
    building = db.get_building_by_id(sensor.REAL_SENSOR_BUILDING_ID)
    settings = db.get_building_settings(sensor.REAL_SENSOR_BUILDING_ID) or {}
    temperature, humidity, status = sensor.read_sensor_snapshot(
        sensor.REAL_SENSOR_BUILDING_ID,
        default_temperature=settings.get('default_temperature'),
        default_humidity=settings.get('default_humidity'),
        default_co2=settings.get('default_co2'),
    )
    co2 = status.get('co2', settings.get('default_co2'))
    building_name = building['name'] if building else sensor.REAL_SENSOR_BUILDING_NAME
    parts = [
        f'{building_name}: {temperature:.1f} C',
        f'{humidity:.1f}% RH',
    ]
    if co2 is not None:
        parts.append(f'{float(co2):.0f} ppm CO2')
    parts.append(f'mode {status.get("mode", "unknown")}')
    return ', '.join(parts)


def build_daily_summary_message(days=1):
    rows = db.get_comfort_event_summary(days=days)
    summary = lark_commands._format_summary(rows, days)
    sensor_line = _read_primary_sensor_line()
    generated_at = comfort_notifications.format_hong_kong_time()
    return (
        f'EcoPlay daily summary\n'
        f'Time: {generated_at}\n\n'
        f'{summary}\n\n'
        f'Current sensor: {sensor_line}'
    )


def send_daily_summary(days=1):
    message = build_daily_summary_message(days=days)
    result = comfort_notifications.send_lark_text(message)
    return message, result


def main():
    days = int(os.getenv('ECOPLAY_DAILY_SUMMARY_DAYS', '1') or '1')
    days = max(1, min(days, 365))
    dry_run = '--dry-run' in sys.argv
    message = build_daily_summary_message(days=days)
    print(message)
    if dry_run:
        return 0

    result = comfort_notifications.send_lark_text(message)
    print(f'Lark status: {result["status"]}')
    if not result.get('ok'):
        print(result.get('error', ''), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
