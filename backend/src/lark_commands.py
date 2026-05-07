import json
import os
import re

import chat_service
import comfort_notifications
import db


COMMAND_PREFIXES = ('ecoplay', '/ecoplay', '@ecoplay')
BARE_COMMAND_PREFIXES = ('summary', 'stats', 'history', 'histroy', 'log', 'help')
CHAT_PREFIXES = ('chat', 'ask', 'question')
HISTORY_KEYWORDS = ('history', 'histroy', 'log')
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


def _has_bot_mention(text):
    return bool(re.search(r'<at[^>]*>.*?</at>', text, flags=re.IGNORECASE))


def _is_ecoplay_command(text):
    lower = text.lower().strip()
    return lower.startswith(COMMAND_PREFIXES) or lower.startswith(BARE_COMMAND_PREFIXES)


def _parse_days(text):
    lower = text.lower()
    if any(keyword in lower for keyword in ('today', 'toda', 'tdy')):
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


def _default_lark_building_id():
    raw_value = (
        os.getenv('ECOPLAY_LARK_CHAT_BUILDING_ID')
        or os.getenv('ECOPLAY_REAL_SENSOR_BUILDING_ID')
        or '13'
    )
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return 13


def _strip_prefix(text, prefix):
    if text.lower() == prefix:
        return ''
    return text[len(prefix):].strip()


def _extract_llm_prompt(original_text, command_text):
    lower = command_text.lower().strip()
    if not lower:
        return ''

    for prefix in CHAT_PREFIXES:
        if lower == prefix or lower.startswith(f'{prefix} '):
            return _strip_prefix(command_text, prefix)

    for prefix in COMMAND_PREFIXES:
        if lower == prefix:
            return ''
        if lower.startswith(f'{prefix} '):
            remaining = _strip_prefix(command_text, prefix)
            remaining_lower = remaining.lower()
            for chat_prefix in CHAT_PREFIXES:
                if remaining_lower == chat_prefix or remaining_lower.startswith(f'{chat_prefix} '):
                    return _strip_prefix(remaining, chat_prefix)
            return remaining

    if _has_bot_mention(original_text):
        return command_text

    return ''


def _build_llm_reply(prompt):
    building_id = _find_building_id(prompt) or _default_lark_building_id()
    session_id = db.create_chat_session(building_id=building_id, room_label='Lark')
    result = chat_service.process_chat(
        session_id,
        prompt,
        building_id=building_id,
        room_label='Lark',
    )
    return result['reply']


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
    if not _is_ecoplay_command(command_text) and not _has_bot_mention(text):
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
    if any(keyword in lower for keyword in HISTORY_KEYWORDS):
        limit = _parse_limit(command_text)
        events = db.get_comfort_events(limit=limit, building_id=building_id)
        return _format_history(events, limit)

    if 'summary' in lower or 'stats' in lower:
        rows = db.get_comfort_event_summary(days=days, building_id=building_id)
        return _format_summary(rows, days)

    llm_prompt = _extract_llm_prompt(text, command_text)
    if llm_prompt:
        return _build_llm_reply(llm_prompt)

    return (
        'I heard EcoPlay, but I did not recognize the command. '
        'Try: ecoplay summary 7 days, ecoplay history today, or ecoplay chat what is the current CO2?'
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
