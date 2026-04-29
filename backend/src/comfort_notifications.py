import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv


BASE_DIR = os.path.dirname(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'))

LARK_WEBHOOK_URL = (
    os.getenv('LARK_WEBHOOK_URL', '').strip()
    or os.getenv('FEISHU_WEBHOOK_URL', '').strip()
    or os.getenv('OPENCLAW_LARK_WEBHOOK_URL', '').strip()
)
ALERT_SOURCE_NAME = os.getenv('ECOPLAY_ALERT_SOURCE_NAME', 'EcoPlay')
LARK_VERIFICATION_TOKEN = os.getenv('LARK_VERIFICATION_TOKEN', '').strip()
HONG_KONG_TZ = ZoneInfo('Asia/Hong_Kong')


def format_hong_kong_time(value=None):
    if value:
        try:
            normalized = str(value).replace('Z', '+00:00')
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=ZoneInfo('UTC'))
            return parsed.astimezone(HONG_KONG_TZ).strftime('%Y-%m-%d %H:%M:%S HKT')
        except ValueError:
            return str(value)
    return datetime.now(HONG_KONG_TZ).strftime('%Y-%m-%d %H:%M:%S HKT')


def build_lark_message(event, building):
    vote_label_by_type = {
        'too_cold': 'Too Cold',
        'comfort': 'Comfort',
        'too_warm': 'Too Warm',
    }
    vote_label = vote_label_by_type.get(event['vote_type'], event['vote_type'])
    sensor_parts = []
    if event.get('sensor_temperature') is not None:
        sensor_parts.append(f'Temp {event["sensor_temperature"]:.1f} C')
    if event.get('sensor_humidity') is not None:
        sensor_parts.append(f'Humidity {event["sensor_humidity"]:.1f}%')
    if event.get('sensor_co2') is not None:
        sensor_parts.append(f'CO2 {event["sensor_co2"]:.0f} ppm')
    sensor_line = ', '.join(sensor_parts) if sensor_parts else 'not available'
    sensor_time = format_hong_kong_time(event.get('sensor_read_time')) if event.get('sensor_read_time') else 'not available'
    return (
        f'{ALERT_SOURCE_NAME} alert: {vote_label}\n'
        f'Building: {building["name"]}\n'
        f'New interactions: {event["delta_count"]}\n'
        f'Totals now: Too Cold {event["too_cold_after"]}, '
        f'Comfort {event["comfort_after"]}, '
        f'Too Warm {event["too_warm_after"]}, Total {event["total_after"]}\n'
        f'Sensor at press: {sensor_line}\n'
        f'Sensor reading time: {sensor_time}\n'
        f'Time: {format_hong_kong_time()}'
    )


def send_lark_text(message):
    if not LARK_WEBHOOK_URL:
        return {
            'ok': False,
            'status': 'not_configured',
            'error': 'LARK_WEBHOOK_URL is not configured in backend/.env.',
        }

    payload = json.dumps({
        'msg_type': 'text',
        'content': {
            'text': message,
        },
    }).encode('utf-8')
    request = urllib.request.Request(
        LARK_WEBHOOK_URL,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            body = response.read().decode('utf-8', errors='replace')
            if 200 <= response.status < 300:
                return {'ok': True, 'status': 'sent', 'error': ''}
            return {
                'ok': False,
                'status': 'failed',
                'error': f'Lark returned HTTP {response.status}: {body[:300]}',
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        return {
            'ok': False,
            'status': 'failed',
            'error': f'Lark returned HTTP {exc.code}: {body[:300]}',
        }
    except urllib.error.URLError as exc:
        return {'ok': False, 'status': 'failed', 'error': str(exc.reason)}
    except TimeoutError:
        return {'ok': False, 'status': 'failed', 'error': 'Lark webhook request timed out.'}


def send_comfort_event_alert(event, building):
    return send_lark_text(build_lark_message(event, building))
