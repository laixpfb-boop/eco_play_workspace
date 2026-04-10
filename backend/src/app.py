from flask import Flask, jsonify, request
from flask_cors import CORS
import sqlite3
from . import db
from . import sensor
from . import algorithms
from . import chat_service
from datetime import date, datetime

# 初始化Flask应用
app = Flask(__name__)
CORS(app)  # 解决跨域（前端调用）

# 首次运行初始化数据库
try:
    db.init_db()
except Exception as e:
    raise RuntimeError(f"数据库初始化失败: {e}") from e


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
    if not db.get_building_by_id(building_id):
        return jsonify({'error': 'Building not found'}), 404

    too_cold = data['too_cold']
    comfort = data['comfort']
    too_warm = data['too_warm']
    total = data['total']
    if any(not isinstance(value, int) or value < 0 for value in [too_cold, comfort, too_warm, total]):
        return jsonify({'error': 'Vote values must be non-negative integers'}), 400
    if total != too_cold + comfort + too_warm:
        return jsonify({'error': 'Total must equal too_cold + comfort + too_warm'}), 400
    
    db.update_votes(
        building_id,
        too_cold,
        comfort,
        too_warm,
        total,
        data.get('vote_date', date.today())
    )
    return jsonify({'message': 'Votes updated successfully', 'building_id': building_id})

# ========== 传感器接口 ==========
@app.route('/api/sensor/<int:building_id>', methods=['GET'])
def get_sensor_data(building_id):
    """获取指定建筑的传感器数据（实时读取）"""
    if not db.get_building_by_id(building_id):
        return jsonify({'error': 'Building not found'}), 404

    building_settings = db.get_building_settings(building_id) or {}
    temp, humi = sensor.read_sensor_data(
        building_id,
        default_temperature=building_settings.get('default_temperature'),
        default_humidity=building_settings.get('default_humidity'),
    )
    # 存储传感器数据到数据库
    db.add_sensor_data(building_id, temp, humi)
    return jsonify({
        'building_id': building_id,
        'temperature': temp,
        'humidity': humi,
        'read_time': datetime.utcnow().isoformat() + 'Z'
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
def get_settings():
    return jsonify({
        'buildings': db.get_settings_overview(),
        'algorithmWeights': db.get_algorithm_weights(),
    })


@app.route('/api/settings/buildings', methods=['POST'])
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
def delete_building_from_settings(building_id):
    if not db.get_building_by_id(building_id):
        return jsonify({'error': 'Building not found'}), 404
    db.delete_building(building_id)
    if db.get_building_by_id(building_id):
        return jsonify({'error': 'Building still exists after delete attempt'}), 500
    return jsonify({'message': 'Building deleted successfully', 'deleted_building_id': building_id})


@app.route('/api/settings/weights', methods=['PUT'])
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
