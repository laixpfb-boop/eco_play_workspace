import json
import os
import urllib.error
import urllib.request
from dotenv import load_dotenv

try:
    from . import db
except ImportError:
    import db

load_dotenv()

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
OPENAI_MODEL = os.getenv('OPENAI_CHAT_MODEL', 'gpt-5-mini')

SERVICE_KEYWORDS = {
    'too_cold': ['cold', 'freezing', 'chilly'],
    'too_warm': ['warm', 'hot', 'heat'],
    'air_quality': ['air', 'co2', 'stuffy', 'ventilation'],
    'noise': ['noise', 'loud', 'quiet'],
    'lighting': ['light', 'dark', 'bright'],
}


def process_chat(session_id, user_message, building_id=None, room_label=''):
    session = db.get_chat_session(session_id)
    if not session:
        raise ValueError('Chat session not found')

    next_building_id = building_id if building_id is not None else session.get('building_id')
    next_room_label = room_label or session.get('room_label', '')
    db.update_chat_session(session_id, building_id=next_building_id, room_label=next_room_label)
    db.add_chat_message(session_id, 'user', user_message)

    context = build_chat_context(session_id, next_building_id, next_room_label)
    model_result = generate_chat_response(user_message, context)

    service_request_id = None
    if model_result['should_create_service_request'] and next_building_id:
        service_request_id = db.create_service_request(
            session_id,
            next_building_id,
            next_room_label,
            model_result['request_type'],
            model_result['severity'],
            model_result['service_summary'],
        )

    db.add_chat_message(session_id, 'assistant', model_result['reply'], model_result['intent'])
    return {
        'session_id': session_id,
        'reply': model_result['reply'],
        'intent': model_result['intent'],
        'service_request_created': service_request_id is not None,
        'service_request_id': service_request_id,
        'service_summary': model_result['service_summary'] if service_request_id else '',
    }


def build_chat_context(session_id, building_id, room_label):
    building = db.get_building_by_id(building_id) if building_id else None
    votes = db.ensure_votes_for_date(building_id) if building_id else None
    sensor = db.get_latest_sensor_data(building_id) if building_id else None
    if not sensor and building_id:
        settings = db.get_building_settings(building_id) or {}
        sensor = {
            'temperature': settings.get('default_temperature', 24.0),
            'humidity': settings.get('default_humidity', 50.0),
        }

    return {
        'building': building,
        'room_label': room_label,
        'votes': votes,
        'sensor': sensor,
        'weights': db.get_algorithm_weights(),
        'recent_messages': db.get_chat_messages(session_id, limit=8),
        'open_requests': db.get_open_service_requests(session_id),
    }


def generate_chat_response(user_message, context):
    if OPENAI_API_KEY:
        try:
            return generate_openai_response(user_message, context)
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, json.JSONDecodeError):
            pass
    return generate_fallback_response(user_message, context)


def generate_openai_response(user_message, context):
    messages = [
        {
            'role': 'system',
            'content': (
                'You are the EcoPlay campus comfort assistant. '
                'Use the provided building context only. '
                'Return valid JSON with keys: '
                'reply, intent, should_create_service_request, request_type, severity, service_summary. '
                'Keep reply concise and helpful. '
                'Only create a service request when the user is reporting a concrete room comfort issue.'
            ),
        },
        {
            'role': 'user',
            'content': (
                f'Context:\n{json.dumps(context, ensure_ascii=False)}\n\n'
                f'User message:\n{user_message}\n\n'
                'Respond as JSON only.'
            ),
        },
    ]
    payload = json.dumps({
        'model': OPENAI_MODEL,
        'messages': messages,
        'response_format': {'type': 'json_object'},
    }).encode('utf-8')
    request = urllib.request.Request(
        'https://api.openai.com/v1/chat/completions',
        data=payload,
        headers={
            'Authorization': f'Bearer {OPENAI_API_KEY}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.loads(response.read().decode('utf-8'))
    content = body['choices'][0]['message']['content']
    result = json.loads(content)
    return normalize_chat_result(result)


def generate_fallback_response(user_message, context):
    lower = user_message.lower()
    building = context.get('building')
    votes = context.get('votes')
    sensor = context.get('sensor')
    request_type = infer_request_type(lower)
    should_create_service_request = request_type in {'too_cold', 'too_warm', 'air_quality', 'noise', 'lighting'}
    building_name = building['name'] if building else 'this area'

    if votes and sensor and ('temperature' in lower or 'humidity' in lower or 'data' in lower):
        reply = (
            f'{building_name} currently shows {sensor["temperature"]}°C and {sensor["humidity"]}% humidity. '
            f'Today\'s comfort split is {votes["comfort"]} comfort, {votes["too_cold"]} too cold, and {votes["too_warm"]} too warm.'
        )
        intent = 'building_status'
    elif should_create_service_request:
        room_note = f' for room {context.get("room_label")}' if context.get('room_label') else ''
        reply = (
            f'I can help log that comfort issue{room_note}. '
            'If this is the correct building or room, I will prepare it for follow-up service.'
        )
        intent = 'service_request'
    else:
        reply = (
            'I can help with room comfort issues, building vote trends, and current temperature or humidity. '
            'Tell me the room and what problem you are experiencing.'
        )
        intent = 'general_help'

    return normalize_chat_result({
        'reply': reply,
        'intent': intent,
        'should_create_service_request': should_create_service_request and building is not None,
        'request_type': request_type,
        'severity': infer_severity(lower),
        'service_summary': f'User reported {request_type} issue in {building_name}.',
    })


def infer_request_type(lower_message):
    for request_type, keywords in SERVICE_KEYWORDS.items():
        if any(keyword in lower_message for keyword in keywords):
            return request_type
    return 'other'


def infer_severity(lower_message):
    if any(word in lower_message for word in ['urgent', 'immediately', 'very', 'extreme']):
        return 'high'
    if any(word in lower_message for word in ['slightly', 'a bit', 'minor']):
        return 'low'
    return 'medium'


def normalize_chat_result(result):
    return {
        'reply': str(result.get('reply', 'I can help with room comfort issues and building support.')).strip(),
        'intent': str(result.get('intent', 'general_help')).strip(),
        'should_create_service_request': bool(result.get('should_create_service_request', False)),
        'request_type': str(result.get('request_type', 'other')).strip() or 'other',
        'severity': str(result.get('severity', 'medium')).strip() or 'medium',
        'service_summary': str(result.get('service_summary', '')).strip(),
    }
