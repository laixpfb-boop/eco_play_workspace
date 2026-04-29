import json
import re

import comfort_notifications
import db


COMMAND_PREFIXES = ('ecoplay', '/ecoplay', '@ecoplay')
BARE_COMMAND_PREFIXES = ('summary', 'stats', 'history', 'log', 'help')
VOTE_LABELS = {
    'too_cold': 'Too Cold',
    'comfort': 'Comfort',
    'too_warm': 'Too Warm',
}


def extract_message_text(payload):
    if isinstance(payload.get('text'), str):
        return payload['text']

    event = payload.get('event') if isinstance(payload.get('event'), dict) else {}
    message = event.get('message') if isinstance(event.get('message'), dict) else {}
    content = message.get('content')
    if isinstance(content, str):
        try:
            content_data = json.loads(content)
        except json.JSONDecodeError:
            return content
        if isinstance(content_data.get('text'), str):
            return content_data['text']

    if isinstance(message.get('text'), str):
        return message['text']
    return ''


def _normalize_command_text(text):
    text = re.sub(r'<at[^>]*>.*?</at>', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _is_ecoplay_command(text):
    lower = text.lower().strip()
    return lower.startswith(COMMAND_PREFIXES) or lower.startswith(BARE_COMMAND_PREFIXES)


def _parse_days(text):
    lower = text.lower()
    if 'today' in lower:
        return 1
    match = re.search(r'(\d+)\s*(day|days|d)\b', lower)
    if match:
        return max(1, min(int(match.group(1)), 365))
    return 7


def _parse_limit(text):
    match = re.search(r'\blimit\s+(\d+)\b', text.lower())
    if match:
        return max(1, min(int(match.group(1)), 50))
    return 10


def _find_building_id(text):
    lower = text.lower()
    for building in db.get_all_buildings():
        if building['name'].lower() in lower:
            return building['id']
    return None


def _format_summary(rows, days):
    if not rows:
        return f'EcoPlay summary for the last {days} day(s): no recorded vote interactions yet.'

    lines = [f'EcoPlay summary for the last {days} day(s):']
    for row in rows:
        vote_label = VOTE_LABELS.get(row['vote_type'], row['vote_type'])
        lines.append(
            f'- {row["building_name"]}: {vote_label} {row["event_count"]} '
            f'({row["interaction_count"]} interaction(s)); latest '
            f'{comfort_notifications.format_hong_kong_time(row["latest_event_at"])}'
        )
    return '\n'.join(lines)


def _format_history(events, limit):
    if not events:
        return 'EcoPlay history: no recorded vote interactions yet.'

    lines = [f'EcoPlay latest {min(limit, len(events))} vote interaction(s):']
    for event in events[:limit]:
        vote_label = VOTE_LABELS.get(event['vote_type'], event['vote_type'])
        sensor_parts = []
        if event.get('sensor_temperature') is not None:
            sensor_parts.append(f'{event["sensor_temperature"]:.1f} C')
        if event.get('sensor_humidity') is not None:
            sensor_parts.append(f'{event["sensor_humidity"]:.1f}% RH')
        if event.get('sensor_co2') is not None:
            sensor_parts.append(f'{event["sensor_co2"]:.0f} ppm CO2')
        sensor_text = ', '.join(sensor_parts) if sensor_parts else 'sensor n/a'
        lines.append(
            f'- {comfort_notifications.format_hong_kong_time(event["created_at"])} | {event["building_name"]} | '
            f'{vote_label} +{event["delta_count"]} | {sensor_text}'
        )
    return '\n'.join(lines)


def build_reply_for_text(text):
    command_text = _normalize_command_text(text)
    if not _is_ecoplay_command(command_text):
        return None

    lower = command_text.lower()
    if 'help' in lower:
        return (
            'EcoPlay commands:\n'
            '- ecoplay summary today\n'
            '- ecoplay summary 7 days\n'
            '- ecoplay history today\n'
            '- ecoplay history 7 days\n'
            '- ecoplay history 7 days limit 20\n'
            '- ecoplay summary 7 days Sustainability Office'
        )

    days = _parse_days(command_text)
    building_id = _find_building_id(command_text)
    if 'history' in lower or 'log' in lower:
        limit = _parse_limit(command_text)
        events = db.get_comfort_events(limit=limit, building_id=building_id)
        return _format_history(events, limit)

    if 'summary' in lower or 'stats' in lower:
        rows = db.get_comfort_event_summary(days=days, building_id=building_id)
        return _format_summary(rows, days)

    return (
        'I heard EcoPlay, but I did not recognize the command. '
        'Try: ecoplay summary 7 days or ecoplay history today.'
    )


def handle_lark_payload(payload):
    text = extract_message_text(payload)
    reply = build_reply_for_text(text)
    if not reply:
        return {'handled': False, 'message': 'No EcoPlay command found.'}

    send_result = comfort_notifications.send_lark_text(reply)
    return {
        'handled': True,
        'reply': reply,
        'notification_status': send_result['status'],
        'notification_error': send_result.get('error', ''),
    }
