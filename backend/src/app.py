from flask import Flask, jsonify, request, Response, session
from flask_cors import CORS
import sqlite3
import csv
import io
import json
import os
import secrets
import db
import sensor
import algorithms
import chat_service
import comfort_notifications
import lark_commands
from datetime import date, datetime, timedelta
from functools import wraps

# 初始化Flask应用
app = Flask(__name__)
CORS(app)  # 解决跨域（前端调用）
app.config['SECRET_KEY'] = os.environ.get('ECOPLAY_SECRET_KEY', 'ecoplay-dev-secret-change-me')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

# 首次运行初始化数据库
try:
    db.init_db()
except Exception as e:
    raise RuntimeError(f"数据库初始化失败: {e}") from e


OPERATOR_USERNAME = os.environ.get('ECOPLAY_OPERATOR_USERNAME', 'admin')
OPERATOR_PASSWORD = os.environ.get('ECOPLAY_OPERATOR_PASSWORD', 'admin123')
LOGIN_WINDOW = timedelta(minutes=10)
LOGIN_MAX_ATTEMPTS = 5
CHALLENGE_TTL = timedelta(minutes=5)
LOGIN_ATTEMPTS = {}
LOGIN_CHALLENGES = {}


def _cleanup_login_attempts(now):
    expired = [ip for ip, state in LOGIN_ATTEMPTS.items() if state['expires_at'] <= now]
    for ip in expired:
        LOGIN_ATTEMPTS.pop(ip, None)


def _cleanup_challenges(now):
    expired = [challenge_id for challenge_id, state in LOGIN_CHALLENGES.items() if state['expires_at'] <= now]
    for challenge_id in expired:
        LOGIN_CHALLENGES.pop(challenge_id, None)


def _get_client_ip():
    forwarded_for = request.headers.get('X-Forwarded-For', '')
    if forwarded_for:
        return forwarded_for.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def _issue_login_challenge():
    now = datetime.utcnow()
    _cleanup_challenges(now)
    left = secrets.randbelow(8) + 2
    right = secrets.randbelow(8) + 2
    challenge_id = secrets.token_urlsafe(12)
    LOGIN_CHALLENGES[challenge_id] = {
        'answer': str(left + right),
        'expires_at': now + CHALLENGE_TTL,
    }
    return {
        'challenge_id': challenge_id,
        'prompt': f'What is {left} + {right}?',
        'expires_in_seconds': int(CHALLENGE_TTL.total_seconds()),
    }


def _is_operator_authenticated():
    if session.get('operator_authenticated') is not True:
        return False
    return bool(session.get('operator_username'))


def require_operator_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not _is_operator_authenticated():
            return jsonify({'error': 'Operator authentication required'}), 401
        return view(*args, **kwargs)
    return wrapped


def calculate_percent(part, total):
    """避免 total 为 0 时触发除零错误。"""
    if total <= 0:
        return 0.0
    return round((part / total) * 100, 1)


def parse_non_negative_int(data, field_name):
    value = data.get(field_name)
    if not isinstance(value, int) or value < 0:
        raise ValueError(f'{field_name} must be a non-negative integer')
    return value


def parse_non_negative_float(data, field_name):
    value = data.get(field_name)
    if not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f'{field_name} must be a non-negative number')
    return float(value)


def parse_optional_float(data, field_name):
    value = data.get(field_name)
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        return None
    return round(float(value), 1)


def build_comfort_analysis_response():
    analysis_rows = db.get_comfort_analysis_rows()
    model_result = algorithms.analyze_comfort_correlation(analysis_rows)
    settings = db.get_settings_overview()
    reference_defaults = None
    if settings:
        reference_defaults = {
            'co2': round(sum(item['default_co2'] for item in settings) / len(settings), 1),
            'noise': round(sum(item['default_noise'] for item in settings) / len(settings), 1),
            'light': round(sum(item['default_light'] for item in settings) / len(settings), 1),
        }
    return {
        'sampleSize': model_result['sampleSize'],
        'correlations': model_result['correlations'],
        'recommendation': {
            **model_result['recommendation'],
            'reference_defaults': reference_defaults,
        },
        'buildingRecommendations': model_result['buildingRecommendations'],
    }


@app.route('/api/operator/auth/challenge', methods=['GET'])
def get_operator_login_challenge():
    return jsonify(_issue_login_challenge())


@app.route('/api/operator/auth/login', methods=['POST'])
def operator_login():
    now = datetime.utcnow()
    _cleanup_login_attempts(now)
    _cleanup_challenges(now)

    client_ip = _get_client_ip()
    login_state = LOGIN_ATTEMPTS.get(client_ip)
    if login_state and login_state['count'] >= LOGIN_MAX_ATTEMPTS and login_state['expires_at'] > now:
      retry_after = int((login_state['expires_at'] - now).total_seconds())
      return jsonify({'error': f'Too many login attempts. Try again in {retry_after} seconds.'}), 429

    data = request.get_json(silent=True) or {}
    username = data.get('username', '')
    password = data.get('password', '')
    challenge_id = data.get('challenge_id', '')
    challenge_answer = str(data.get('challenge_answer', '')).strip()

    challenge = LOGIN_CHALLENGES.get(challenge_id)
    if not challenge or challenge['expires_at'] <= now:
        return jsonify({'error': 'The anti-attack code has expired. Please refresh and try again.'}), 400

    if challenge_answer != challenge['answer']:
        LOGIN_CHALLENGES.pop(challenge_id, None)
        LOGIN_ATTEMPTS[client_ip] = {
            'count': (login_state['count'] if login_state else 0) + 1,
            'expires_at': now + LOGIN_WINDOW,
        }
        return jsonify({'error': 'Incorrect anti-attack code'}), 400

    LOGIN_CHALLENGES.pop(challenge_id, None)
    if username != OPERATOR_USERNAME or password != OPERATOR_PASSWORD:
        LOGIN_ATTEMPTS[client_ip] = {
            'count': (login_state['count'] if login_state else 0) + 1,
            'expires_at': now + LOGIN_WINDOW,
        }
        return jsonify({'error': 'Invalid username or password'}), 401

    LOGIN_ATTEMPTS.pop(client_ip, None)
    session.clear()
    session.permanent = True
    session['operator_authenticated'] = True
    session['operator_username'] = username
    session['operator_login_at'] = now.isoformat() + 'Z'
    return jsonify({'authenticated': True, 'username': username})


@app.route('/api/operator/auth/status', methods=['GET'])
def operator_auth_status():
    return jsonify({
        'authenticated': _is_operator_authenticated(),
        'username': session.get('operator_username'),
    })


@app.route('/api/operator/auth/logout', methods=['POST'])
def operator_logout():
    session.clear()
    return jsonify({'authenticated': False})

# ========== 建筑接口 ==========
@app.route('/api/buildings', methods=['GET'])
def get_buildings():
    """获取所有建筑"""
    buildings = db.get_all_buildings()
    return jsonify(buildings)

@app.route('/api/buildings/<name>', methods=['GET'])
def get_building(name):
    """按名称获取建筑"""
    building = db.get_building_by_name(name)
    if not building:
        return jsonify({'error': 'Building not found'}), 404
    return jsonify(building)

@app.route('/api/buildings', methods=['POST'])
def add_building():
    """添加建筑"""
    data = request.get_json(silent=True)
    if not data or not data.get('name'):
        return jsonify({'error': 'Name is required'}), 400
    try:
        db.add_building(data['name'], data.get('description', ''))
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Building name already exists'}), 409
    return jsonify({'message': 'Building added successfully'}), 201

@app.route('/api/buildings/<int:id>', methods=['PUT'])
def update_building(id):
    """更新建筑"""
    data = request.get_json(silent=True)
    if not data or not data.get('name'):
        return jsonify({'error': 'Name is required'}), 400
    if not db.get_building_by_id(id):
        return jsonify({'error': 'Building not found'}), 404
    try:
        db.update_building(id, data['name'], data.get('description', ''))
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Building name already exists'}), 409
    return jsonify({'message': 'Building updated successfully'})

@app.route('/api/buildings/<int:id>', methods=['DELETE'])
def delete_building(id):
    """删除建筑"""
    if not db.get_building_by_id(id):
        return jsonify({'error': 'Building not found'}), 404
    db.delete_building(id)
    return jsonify({'message': 'Building deleted successfully'})

# ========== 投票接口 ==========
@app.route('/api/votes/<building_name>', methods=['GET'])
def get_building_votes(building_name):
    """获取指定建筑的投票数据（当日）"""
    building = db.get_building_by_name(building_name)
    if not building:
        return jsonify({'error': 'Building not found'}), 404
    
    votes = db.ensure_votes_for_date(building['id'], date.today())
    
    # 计算百分比
    votes['too_cold_percent'] = calculate_percent(votes['too_cold'], votes['total'])
    votes['comfort_percent'] = calculate_percent(votes['comfort'], votes['total'])
    votes['too_warm_percent'] = calculate_percent(votes['too_warm'], votes['total'])
    
    return jsonify(votes)

@app.route('/api/votes/<int:building_id>', methods=['PUT'])
def update_building_votes(building_id):
    """更新投票数据"""
    data = request.get_json(silent=True)
    required_fields = ['too_cold', 'comfort', 'too_warm', 'total']
    if not data or not all(f in data for f in required_fields):
        return jsonify({'error': 'Missing vote data'}), 400
    building = db.get_building_by_id(building_id)
    if not building:
        return jsonify({'error': 'Building not found'}), 404

    too_cold = data['too_cold']
    comfort = data['comfort']
    too_warm = data['too_warm']
    total = data['total']
    if any(not isinstance(value, int) or value < 0 for value in [too_cold, comfort, too_warm, total]):
        return jsonify({'error': 'Vote values must be non-negative integers'}), 400
    if total != too_cold + comfort + too_warm:
        return jsonify({'error': 'Total must equal too_cold + comfort + too_warm'}), 400

    target_date = data.get('vote_date', date.today())
    sensor_snapshot = read_vote_press_sensor_snapshot(building_id)
    sensor_temperature = parse_optional_float(sensor_snapshot, 'temperature')
    sensor_humidity = parse_optional_float(sensor_snapshot, 'humidity')
    sensor_co2 = parse_optional_float(sensor_snapshot, 'co2')
    sensor_read_time = str(sensor_snapshot.get('read_time', '') or '')
    previous_votes = db.ensure_votes_for_date(building_id, target_date)
    
    db.update_votes(
        building_id,
        too_cold,
        comfort,
        too_warm,
        total,
        target_date
    )

    logged_events = []
    event_deltas = {
        'too_cold': too_cold - previous_votes.get('too_cold', 0),
        'comfort': comfort - previous_votes.get('comfort', 0),
        'too_warm': too_warm - previous_votes.get('too_warm', 0),
    }
    for vote_type, delta_count in event_deltas.items():
        if delta_count <= 0:
            continue
        event = {
            'building_id': building_id,
            'vote_type': vote_type,
            'delta_count': delta_count,
            'total_after': total,
            'too_cold_after': too_cold,
            'comfort_after': comfort,
            'too_warm_after': too_warm,
            'sensor_temperature': sensor_temperature,
            'sensor_humidity': sensor_humidity,
            'sensor_co2': sensor_co2,
            'sensor_read_time': sensor_read_time,
        }
        event_id = db.add_comfort_event(**event)
        event['id'] = event_id
        notification_result = comfort_notifications.send_comfort_event_alert(event, building)
        db.update_comfort_event_notification(
            event_id,
            notification_result['status'],
            notification_result.get('error', ''),
        )
        logged_events.append({
            **event,
            'notification_status': notification_result['status'],
            'notification_error': notification_result.get('error', ''),
        })

    return jsonify({
        'message': 'Votes updated successfully',
        'building_id': building_id,
        'comfort_events': logged_events,
    })


def read_vote_press_sensor_snapshot(building_id):
    building_settings = db.get_building_settings(building_id) or {}
    try:
        temp, humi, sensor_status = sensor.read_sensor_snapshot(
            building_id,
            default_temperature=building_settings.get('default_temperature'),
            default_humidity=building_settings.get('default_humidity'),
            default_co2=building_settings.get('default_co2'),
        )
        co2 = round(float(sensor_status.get('co2', building_settings.get('default_co2', 650.0))), 1)
        return {
            'temperature': temp,
            'humidity': humi,
            'co2': co2,
            'read_time': sensor_status.get('checked_at') or datetime.utcnow().isoformat() + 'Z',
        }
    except Exception as exc:
        print(f'Vote press sensor read failed: {exc}')
        request_sensor = request.get_json(silent=True) or {}
        sensor_snapshot = request_sensor.get('sensor') if isinstance(request_sensor.get('sensor'), dict) else {}
        return {
            'temperature': sensor_snapshot.get('temperature', building_settings.get('default_temperature')),
            'humidity': sensor_snapshot.get('humidity', building_settings.get('default_humidity')),
            'co2': sensor_snapshot.get('co2', building_settings.get('default_co2')),
            'read_time': sensor_snapshot.get('read_time') or datetime.utcnow().isoformat() + 'Z',
        }


def log_lark_event(payload, result=None, status_code=200, error=''):
    try:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        header = payload.get('header') if isinstance(payload.get('header'), dict) else {}
        event = payload.get('event') if isinstance(payload.get('event'), dict) else {}
        message = event.get('message') if isinstance(event.get('message'), dict) else {}
        entry = {
            'time': datetime.utcnow().isoformat() + 'Z',
            'path': request.path,
            'status_code': status_code,
            'payload_type': payload.get('type', ''),
            'event_type': header.get('event_type', ''),
            'has_token': bool(payload.get('token') or header.get('token')),
            'message_type': message.get('message_type', ''),
            'handled': result.get('handled') if isinstance(result, dict) else None,
            'notification_status': result.get('notification_status') if isinstance(result, dict) else '',
            'error': error,
        }
        with open(os.path.join(log_dir, 'lark_events.log'), 'a', encoding='utf-8') as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception as exc:
        print(f'Lark event logging failed: {exc}')


@app.route('/api/operator/comfort-events', methods=['GET'])
@require_operator_auth
def get_comfort_events():
    limit = request.args.get('limit', default=100, type=int)
    building_id = request.args.get('building_id', default=None, type=int)
    limit = max(1, min(limit, 500))
    return jsonify({
        'events': db.get_comfort_events(limit=limit, building_id=building_id),
    })


@app.route('/api/operator/comfort-events/summary', methods=['GET'])
@require_operator_auth
def get_comfort_event_summary():
    days = request.args.get('days', default=7, type=int)
    building_id = request.args.get('building_id', default=None, type=int)
    days = max(1, min(days, 365))
    return jsonify({
        'days': days,
        'summary': db.get_comfort_event_summary(days=days, building_id=building_id),
    })


@app.route('/', methods=['POST'])
@app.route('/lark/events', methods=['POST'])
@app.route('/api/lark/events', methods=['POST'])
def handle_lark_events():
    payload = request.get_json(silent=True) or {}
    if payload.get('type') == 'url_verification' and payload.get('challenge'):
        log_lark_event(payload)
        return jsonify({'challenge': payload['challenge']})

    expected_token = comfort_notifications.LARK_VERIFICATION_TOKEN
    header = payload.get('header') if isinstance(payload.get('header'), dict) else {}
    payload_token = str(payload.get('token', '') or header.get('token', '') or '')
    if expected_token and payload_token != expected_token:
        log_lark_event(payload, status_code=403, error='Invalid Lark verification token')
        return jsonify({'error': 'Invalid Lark verification token'}), 403

    result = lark_commands.handle_lark_payload(payload)
    log_lark_event(payload, result=result)
    return jsonify(result)

# ========== 传感器接口 ==========
@app.route('/api/sensor/<int:building_id>', methods=['GET'])
def get_sensor_data(building_id):
    """获取指定建筑的传感器数据（实时读取）"""
    if not db.get_building_by_id(building_id):
        return jsonify({'error': 'Building not found'}), 404

    building_settings = db.get_building_settings(building_id) or {}
    temp, humi, sensor_status = sensor.read_sensor_snapshot(
        building_id,
        default_temperature=building_settings.get('default_temperature'),
        default_humidity=building_settings.get('default_humidity'),
    )
    co2 = round(float(sensor_status.get('co2', building_settings.get('default_co2', 650.0))), 1)
    # 存储传感器数据到数据库
    db.add_sensor_data(building_id, temp, humi)
    return jsonify({
        'building_id': building_id,
        'temperature': temp,
        'humidity': humi,
        'co2': co2,
        'read_time': datetime.utcnow().isoformat() + 'Z',
        'sensor_status': sensor_status,
    })


@app.route('/api/rpi/health', methods=['GET'])
@require_operator_auth
def get_raspberry_pi_health():
    return jsonify(sensor.get_raspberry_pi_status())


@app.route('/api/rpi/sensors', methods=['GET'])
@require_operator_auth
def get_raspberry_pi_sensors():
    return jsonify({
        'sensors': sensor.get_all_sensor_statuses(),
    })


@app.route('/api/rpi/sensors/<sensor_id>', methods=['GET'])
@require_operator_auth
def get_raspberry_pi_sensor_detail(sensor_id):
    sensor_status = sensor.get_sensor_status()
    if sensor_id != sensor_status['interface_id']:
        return jsonify({'error': 'Sensor interface not found'}), 404

    building_settings = db.get_building_settings(sensor.REAL_SENSOR_BUILDING_ID) or {}
    temperature, humidity, status = sensor.read_sensor_snapshot(
        sensor.REAL_SENSOR_BUILDING_ID,
        default_temperature=building_settings.get('default_temperature'),
        default_humidity=building_settings.get('default_humidity'),
    )
    co2 = round(float(status.get('co2', building_settings.get('default_co2', 650.0))), 1)
    db.add_sensor_data(sensor.REAL_SENSOR_BUILDING_ID, temperature, humidity)
    return jsonify({
        'interface_id': sensor_status['interface_id'],
        'label': sensor_status['label'],
        'temperature': temperature,
        'humidity': humidity,
        'co2': co2,
        'read_time': datetime.utcnow().isoformat() + 'Z',
        'status': status,
    })

# ========== 算法扩展接口 ==========
@app.route('/api/algorithm/weighted-comfort/<building_name>', methods=['GET'])
def get_weighted_comfort(building_name):
    """获取加权舒适度评分（扩展算法）"""
    building = db.get_building_by_name(building_name)
    if not building:
        return jsonify({'error': 'Building not found'}), 404
    
    # 获取投票数据
    votes = db.ensure_votes_for_date(building['id'])
    
    # 获取最新传感器数据
    sensor_data = db.get_latest_sensor_data(building['id'])
    
    # 计算加权舒适度
    weighted_score = algorithms.calculate_weighted_comfort(votes, sensor_data, db.get_algorithm_weights())
    
    return jsonify({
        'building_name': building_name,
        'base_comfort_percent': calculate_percent(votes['comfort'], votes['total']),
        'weighted_comfort_score': weighted_score,
        'sensor_data': sensor_data
    })

# ========== 前端适配接口（原页面数据） ==========
@app.route('/api/stats', methods=['GET'])
def get_stats_data():
    """适配前端StatsPage的聚合数据接口"""
    buildings = db.get_all_buildings()
    stats_data = []
    
    for b in buildings:
        votes = db.ensure_votes_for_date(b['id'])
        if votes:
            stats_data.append({
                'name': b['name'],
                'id': b['id'],
                'tooCold': votes['too_cold'],
                'comfort': votes['comfort'],
                'tooWarm': votes['too_warm'],
                'total': votes['total'],
                'tooColdPercent': calculate_percent(votes['too_cold'], votes['total']),
                'comfortPercent': calculate_percent(votes['comfort'], votes['total']),
                'tooWarmPercent': calculate_percent(votes['too_warm'], votes['total'])
            })
    
    # 按舒适百分比排序
    stats_data.sort(key=lambda x: x['comfortPercent'], reverse=True)
    
    return jsonify({
        'currentBuilding': stats_data[0] if stats_data else {},
        'buildingRankings': stats_data
    })


@app.route('/api/settings', methods=['GET'])
@require_operator_auth
def get_settings():
    return jsonify({
        'buildings': db.get_settings_overview(),
        'algorithmWeights': db.get_algorithm_weights(),
    })


@app.route('/api/settings/buildings', methods=['POST'])
@require_operator_auth
def create_building_with_settings():
    data = request.get_json(silent=True)
    if not data or not data.get('name'):
        return jsonify({'error': 'Name is required'}), 400

    try:
        db.add_building(data['name'], data.get('description', ''))
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Building name already exists'}), 409

    building = db.get_building_by_name(data['name'])
    apply_today = bool(data.get('apply_today', True))
    try:
        default_too_cold = parse_non_negative_int(data, 'default_too_cold') if 'default_too_cold' in data else 0
        default_comfort = parse_non_negative_int(data, 'default_comfort') if 'default_comfort' in data else 0
        default_too_warm = parse_non_negative_int(data, 'default_too_warm') if 'default_too_warm' in data else 0
        default_temperature = parse_non_negative_float(data, 'default_temperature') if 'default_temperature' in data else 24.0
        default_humidity = parse_non_negative_float(data, 'default_humidity') if 'default_humidity' in data else 50.0
        default_co2 = parse_non_negative_float(data, 'default_co2') if 'default_co2' in data else 650.0
        default_noise = parse_non_negative_float(data, 'default_noise') if 'default_noise' in data else 45.0
        default_light = parse_non_negative_float(data, 'default_light') if 'default_light' in data else 450.0
        db.update_building_settings(
            building['id'],
            default_too_cold,
            default_comfort,
            default_too_warm,
            default_temperature,
            default_humidity,
            default_co2,
            default_noise,
            default_light,
            apply_today=apply_today,
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    return jsonify({'message': 'Building created successfully', 'building': db.get_building_by_id(building['id'])}), 201


@app.route('/api/settings/buildings/<int:building_id>', methods=['PUT'])
@require_operator_auth
def update_building_settings(building_id):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({'error': 'Request body is required'}), 400

    building = db.get_building_by_id(building_id)
    if not building:
        return jsonify({'error': 'Building not found'}), 404

    if 'name' in data:
        if not data.get('name'):
            return jsonify({'error': 'Name is required'}), 400
        try:
            db.update_building(building_id, data['name'], data.get('description', building.get('description', '')))
        except sqlite3.IntegrityError:
            return jsonify({'error': 'Building name already exists'}), 409
    elif 'description' in data:
        db.update_building(building_id, building['name'], data.get('description', ''))

    current_settings = db.get_building_settings(building_id) or {}
    try:
        default_too_cold = parse_non_negative_int(data, 'default_too_cold') if 'default_too_cold' in data else current_settings.get('default_too_cold', 0)
        default_comfort = parse_non_negative_int(data, 'default_comfort') if 'default_comfort' in data else current_settings.get('default_comfort', 0)
        default_too_warm = parse_non_negative_int(data, 'default_too_warm') if 'default_too_warm' in data else current_settings.get('default_too_warm', 0)
        default_temperature = parse_non_negative_float(data, 'default_temperature') if 'default_temperature' in data else current_settings.get('default_temperature', 24.0)
        default_humidity = parse_non_negative_float(data, 'default_humidity') if 'default_humidity' in data else current_settings.get('default_humidity', 50.0)
        default_co2 = parse_non_negative_float(data, 'default_co2') if 'default_co2' in data else current_settings.get('default_co2', 650.0)
        default_noise = parse_non_negative_float(data, 'default_noise') if 'default_noise' in data else current_settings.get('default_noise', 45.0)
        default_light = parse_non_negative_float(data, 'default_light') if 'default_light' in data else current_settings.get('default_light', 450.0)
        db.update_building_settings(
            building_id,
            default_too_cold,
            default_comfort,
            default_too_warm,
            default_temperature,
            default_humidity,
            default_co2,
            default_noise,
            default_light,
            apply_today=bool(data.get('apply_today', False)),
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    return jsonify({'message': 'Building settings updated successfully'})


@app.route('/api/settings/buildings/<int:building_id>', methods=['DELETE'])
@require_operator_auth
def delete_building_from_settings(building_id):
    if not db.get_building_by_id(building_id):
        return jsonify({'error': 'Building not found'}), 404
    db.delete_building(building_id)
    if db.get_building_by_id(building_id):
        return jsonify({'error': 'Building still exists after delete attempt'}), 500
    return jsonify({'message': 'Building deleted successfully', 'deleted_building_id': building_id})


@app.route('/api/settings/weights', methods=['PUT'])
@require_operator_auth
def update_algorithm_settings():
    data = request.get_json(silent=True)
    required_fields = ['too_cold', 'comfort', 'too_warm', 'temp_factor']
    if not data or not all(field in data for field in required_fields):
        return jsonify({'error': 'All weight fields are required'}), 400

    try:
        weights = {
            'too_cold': float(data['too_cold']),
            'comfort': float(data['comfort']),
            'too_warm': float(data['too_warm']),
            'temp_factor': float(data['temp_factor']),
        }
    except (TypeError, ValueError):
        return jsonify({'error': 'Weight values must be numeric'}), 400

    db.update_algorithm_weights(weights)
    return jsonify({'message': 'Algorithm weights updated successfully', 'algorithmWeights': db.get_algorithm_weights()})


@app.route('/api/operator/export.csv', methods=['GET'])
@require_operator_auth
def export_operator_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'building_id',
        'building_name',
        'building_description',
        'vote_date',
        'too_cold',
        'comfort',
        'too_warm',
        'total',
        'avg_temperature',
        'avg_humidity',
        'sensor_samples',
    ])
    for row in db.get_vote_sensor_export_rows():
        writer.writerow([
            row['building_id'],
            row['building_name'],
            row['building_description'],
            row['vote_date'],
            row['too_cold'],
            row['comfort'],
            row['too_warm'],
            row['total'],
            row['avg_temperature'],
            row['avg_humidity'],
            row['sensor_samples'],
        ])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename=ecoplay-export-{date.today().isoformat()}.csv'
        },
    )


@app.route('/api/operator/comfort-analysis', methods=['GET'])
@require_operator_auth
def get_operator_comfort_analysis():
    return jsonify(build_comfort_analysis_response())


@app.route('/api/chat/session', methods=['POST'])
def create_chat_session():
    data = request.get_json(silent=True) or {}
    building_id = data.get('building_id')
    room_label = data.get('room_label', '')
    if building_id is not None and not db.get_building_by_id(building_id):
        return jsonify({'error': 'Building not found'}), 404

    session_id = db.create_chat_session(building_id=building_id, room_label=room_label)
    return jsonify({'session_id': session_id}), 201


@app.route('/api/chat/history/<session_id>', methods=['GET'])
def get_chat_history(session_id):
    session = db.get_chat_session(session_id)
    if not session:
        return jsonify({'error': 'Chat session not found'}), 404

    return jsonify({
        'session': session,
        'messages': db.get_chat_messages(session_id),
        'openRequests': db.get_open_service_requests(session_id),
    })


@app.route('/api/chat', methods=['POST'])
def chat():
    data = request.get_json(silent=True)
    if not data or not data.get('message'):
        return jsonify({'error': 'Message is required'}), 400

    session_id = data.get('session_id')
    if not session_id:
        session_id = db.create_chat_session(
            building_id=data.get('building_id'),
            room_label=data.get('room_label', ''),
        )

    try:
        result = chat_service.process_chat(
            session_id=session_id,
            user_message=data['message'],
            building_id=data.get('building_id'),
            room_label=data.get('room_label', ''),
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404

    return jsonify(result)


@app.route('/api/chat/service-requests/<int:request_id>/close', methods=['POST'])
def close_service_request(request_id):
    if not db.close_service_request(request_id):
        return jsonify({'error': 'Service request not found or already closed'}), 404
    return jsonify({'message': 'Service request closed successfully'})


@app.route('/api/chat/messages/<int:message_id>', methods=['DELETE'])
def delete_chat_message(message_id):
    if not db.delete_chat_message(message_id):
        return jsonify({'error': 'Chat message not found'}), 404
    return jsonify({'message': 'Chat message deleted successfully'})

# 启动服务（适配树莓派）
if __name__ == '__main__':
    app.run(
        host='0.0.0.0',  # 允许局域网访问
        port=5001,       # 端口
        debug=False,     # 树莓派关闭debug（减少资源占用）
        threaded=True    # 多线程处理请求
    )
