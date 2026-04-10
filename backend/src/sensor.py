from datetime import datetime
import os
import random
import socket

try:
    import Adafruit_DHT
    SENSOR_AVAILABLE = True
except ImportError:
    Adafruit_DHT = None
    SENSOR_AVAILABLE = False


REAL_SENSOR_BUILDING_ID = 7
REAL_SENSOR_BUILDING_NAME = 'Sustainability Office'
PRIMARY_SENSOR_INTERFACE = {
    'interface_id': 'primary_dht11',
    'label': 'Primary DHT11 Sensor',
    'sensor_type': 'DHT11',
    'gpio_pin': 11,
    'source_building_id': REAL_SENSOR_BUILDING_ID,
    'source_building_name': REAL_SENSOR_BUILDING_NAME,
}
SENSOR_TYPE = Adafruit_DHT.DHT11 if SENSOR_AVAILABLE else None
SENSOR_STATUS_CACHE = {}


def _iso_now():
    return datetime.utcnow().isoformat() + 'Z'


def _read_file_value(path):
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            return handle.read().strip()
    except OSError:
        return None


def _base_sensor_status():
    return {
        **PRIMARY_SENSOR_INTERFACE,
        'driver_available': SENSOR_AVAILABLE,
        'configured': True,
        'mode': 'hardware' if SENSOR_AVAILABLE else 'fallback',
        'last_read_success': False,
        'checked_at': _iso_now(),
        'message': '',
    }


def _cache_status(status):
    SENSOR_STATUS_CACHE[status['interface_id']] = status
    return status


def get_sensor_status():
    cached = SENSOR_STATUS_CACHE.get(PRIMARY_SENSOR_INTERFACE['interface_id'])
    if cached:
        return {**cached, 'checked_at': _iso_now()}

    status = _base_sensor_status()
    if not status['driver_available']:
        status['message'] = 'DHT driver unavailable; shared hardware interface is currently in fallback mode.'
    else:
        status['message'] = 'Primary DHT11 hardware interface is configured and ready.'
    return status


def get_all_sensor_statuses():
    return [get_sensor_status()]


def get_network_status():
    local_ip = None
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.settimeout(1.0)
        probe.connect(('8.8.8.8', 80))
        local_ip = probe.getsockname()[0]
        probe.close()
        connected = True
        message = 'Network interface is reachable.'
    except OSError:
        connected = False
        message = 'Unable to confirm outbound network connectivity.'

    hostname = socket.gethostname()
    return {
        'connected': connected,
        'hostname': hostname,
        'local_ip': local_ip,
        'checked_at': _iso_now(),
        'message': message,
    }


def get_battery_status():
    power_supply_root = '/sys/class/power_supply'
    if not os.path.isdir(power_supply_root):
        return {
            'available': False,
            'level_percent': None,
            'state': 'not_supported',
            'checked_at': _iso_now(),
            'message': 'No battery interface exposed by this Raspberry Pi setup.',
        }

    battery_dirs = [
        entry
        for entry in os.listdir(power_supply_root)
        if entry.startswith('BAT')
    ]
    if not battery_dirs:
        return {
            'available': False,
            'level_percent': None,
            'state': 'not_supported',
            'checked_at': _iso_now(),
            'message': 'No battery pack detected on the Raspberry Pi power supply interface.',
        }

    battery_dir = os.path.join(power_supply_root, battery_dirs[0])
    capacity = _read_file_value(os.path.join(battery_dir, 'capacity'))
    status = _read_file_value(os.path.join(battery_dir, 'status'))
    level_percent = int(capacity) if capacity and capacity.isdigit() else None

    return {
        'available': True,
        'level_percent': level_percent,
        'state': status.lower() if status else 'unknown',
        'checked_at': _iso_now(),
        'message': 'Battery status read from Linux power_supply interface.',
    }


def get_raspberry_pi_status():
    sensor_statuses = get_all_sensor_statuses()
    working = sum(1 for item in sensor_statuses if item['last_read_success'])
    fallback = sum(1 for item in sensor_statuses if item['mode'] == 'fallback')
    return {
        'service': 'EcoPlay Raspberry Pi bridge',
        'checked_at': _iso_now(),
        'sensor_count': len(sensor_statuses),
        'working_count': working,
        'fallback_count': fallback,
        'driver_available': SENSOR_AVAILABLE,
        'network': get_network_status(),
        'battery': get_battery_status(),
    }


def read_sensor_snapshot(building_id, default_temperature=None, default_humidity=None):
    status = _base_sensor_status()

    if building_id == REAL_SENSOR_BUILDING_ID and SENSOR_AVAILABLE:
        pin = PRIMARY_SENSOR_INTERFACE['gpio_pin']
        humidity, temperature = Adafruit_DHT.read_retry(SENSOR_TYPE, pin)
        if humidity is not None and temperature is not None:
            status.update({
                'last_read_success': True,
                'message': f'Hardware sensor read succeeded on GPIO{pin}.',
                'temperature': round(temperature, 1),
                'humidity': round(humidity, 1),
            })
            return status['temperature'], status['humidity'], _cache_status(status)

        status['message'] = f'Hardware sensor read failed on GPIO{pin}; using fallback values for {REAL_SENSOR_BUILDING_NAME}.'
    elif building_id == REAL_SENSOR_BUILDING_ID:
        status['message'] = f'DHT driver unavailable; using fallback values for {REAL_SENSOR_BUILDING_NAME}.'
    else:
        status.update({
            'mode': 'fallback',
            'message': 'This area currently uses preset default values until additional hardware or positioning is introduced.',
        })

    if default_temperature is not None and default_humidity is not None:
        status.update({
            'temperature': round(default_temperature, 1),
            'humidity': round(default_humidity, 1),
        })
    else:
        status.update({
            'temperature': round(random.uniform(18.0, 28.0), 1),
            'humidity': round(random.uniform(30.0, 70.0), 1),
        })

    return status['temperature'], status['humidity'], _cache_status(status)


def read_sensor_data(building_id, default_temperature=None, default_humidity=None):
    temperature, humidity, _ = read_sensor_snapshot(
        building_id,
        default_temperature=default_temperature,
        default_humidity=default_humidity,
    )
    return temperature, humidity
