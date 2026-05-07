import os
import socket
import threading
import time
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))
except ImportError:
    pass

try:
    from smbus2 import SMBus, i2c_msg
    SENSOR_AVAILABLE = True
except ImportError:
    SMBus = None
    i2c_msg = None
    SENSOR_AVAILABLE = False


REAL_SENSOR_BUILDING_ID = int(os.getenv('ECOPLAY_REAL_SENSOR_BUILDING_ID', '7'))
REAL_SENSOR_BUILDING_NAME = 'Sustainability Office'
PRIMARY_SENSOR_INTERFACE = {
    'interface_id': 'primary_scd4x',
    'label': 'Primary SCD4x Sensor',
    'sensor_type': 'SCD4x',
    'i2c_bus': 1,
    'i2c_address_hex': '0x62',
    'source_building_id': REAL_SENSOR_BUILDING_ID,
    'source_building_name': REAL_SENSOR_BUILDING_NAME,
}

SCD4X_I2C_ADDR = 0x62
I2C_BUS_ID = 1
CACHE_SECONDS = 5

_last_read_time = 0.0
_last_data = {
    'temperature': 24.0,
    'humidity': 50.0,
    'co2': 650.0,
}
_measurement_started = False
_consecutive_failures = 0
SENSOR_STATUS_CACHE = {}
SENSOR_LOCK = threading.Lock()


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


def _crc8(data: bytes) -> int:
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x31) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def _check_word_crc(msb: int, lsb: int, crc: int) -> bool:
    return _crc8(bytes([msb, lsb])) == crc


def _send_command(bus, cmd: int, delay_s: float = 0.0) -> None:
    write = i2c_msg.write(SCD4X_I2C_ADDR, [(cmd >> 8) & 0xFF, cmd & 0xFF])
    bus.i2c_rdwr(write)
    if delay_s > 0:
        time.sleep(delay_s)


def _read_response(bus, num_bytes: int) -> bytes:
    read = i2c_msg.read(SCD4X_I2C_ADDR, num_bytes)
    bus.i2c_rdwr(read)
    return bytes(read)


def _get_data_ready_status(bus) -> bool:
    _send_command(bus, 0xE4B8, delay_s=0.002)
    raw = _read_response(bus, 3)
    if len(raw) != 3 or not _check_word_crc(raw[0], raw[1], raw[2]):
        return False
    return (((raw[0] << 8) | raw[1]) & 0x07FF) != 0


def _start_periodic_measurement(bus) -> None:
    _send_command(bus, 0x21B1, delay_s=0.01)


def _stop_periodic_measurement(bus) -> None:
    _send_command(bus, 0x3F86, delay_s=0.5)


def _read_measurement(bus):
    if not _get_data_ready_status(bus):
        return None

    _send_command(bus, 0xEC05, delay_s=0.002)
    raw = _read_response(bus, 9)
    if len(raw) != 9:
        return None

    co2_msb, co2_lsb, co2_crc = raw[0], raw[1], raw[2]
    t_msb, t_lsb, t_crc = raw[3], raw[4], raw[5]
    rh_msb, rh_lsb, rh_crc = raw[6], raw[7], raw[8]

    if not _check_word_crc(co2_msb, co2_lsb, co2_crc):
        return None
    if not _check_word_crc(t_msb, t_lsb, t_crc):
        return None
    if not _check_word_crc(rh_msb, rh_lsb, rh_crc):
        return None

    co2_raw = (co2_msb << 8) | co2_lsb
    if co2_raw <= 0:
        return None

    t_raw = (t_msb << 8) | t_lsb
    rh_raw = (rh_msb << 8) | rh_lsb

    temperature = -45 + 175 * (t_raw / 65535.0)
    humidity = 100 * (rh_raw / 65535.0)

    return {
        'co2': round(float(co2_raw), 1),
        'temperature': round(float(temperature), 1),
        'humidity': round(float(humidity), 1),
    }


def _default_result(default_temperature=None, default_humidity=None, default_co2=None):
    return {
        'temperature': round(default_temperature if default_temperature is not None else 24.0, 1),
        'humidity': round(default_humidity if default_humidity is not None else 50.0, 1),
        'co2': round(default_co2 if default_co2 is not None else 650.0, 1),
    }


def _restart_periodic_and_read(bus):
    global _measurement_started

    try:
        _stop_periodic_measurement(bus)
    except Exception as stop_exc:
        print(f'SCD4x stop skipped/failed ({stop_exc}); continuing restart.')

    _start_periodic_measurement(bus)
    _measurement_started = True
    time.sleep(6.0)
    return _read_measurement(bus)


def _read_hardware_or_default(defaults):
    global _last_read_time, _last_data, _measurement_started, _consecutive_failures

    with SENSOR_LOCK:
        now = time.time()
        if now - _last_read_time < CACHE_SECONDS:
            return dict(_last_data), True, 'Using cached SCD4x sample.'

        try:
            with SMBus(I2C_BUS_ID) as bus:
                if not _measurement_started:
                    try:
                        _start_periodic_measurement(bus)
                    except Exception as start_exc:
                        print(f'SCD4x start skipped/failed ({start_exc}); trying recovery cycle.')
                    _measurement_started = True
                    time.sleep(6.0)

                try:
                    data = _read_measurement(bus)
                except Exception as read_exc:
                    # This sensor can intermittently NACK reads; force one restart cycle before giving up.
                    try:
                        data = _restart_periodic_and_read(bus)
                        if data is not None:
                            _last_data = data
                            _last_read_time = time.time()
                            _consecutive_failures = 0
                            return dict(data), True, 'SCD4x hardware read recovered after restart.'
                    except Exception as recover_exc:
                        _consecutive_failures += 1
                        if _last_read_time > 0:
                            return dict(_last_data), True, f'SCD4x read/recovery failed ({read_exc}; {recover_exc}); using cached values.'
                        return defaults, False, f'SCD4x read/recovery failed ({read_exc}; {recover_exc}); using fallback values.'

                    if _last_read_time > 0:
                        _consecutive_failures += 1
                        return dict(_last_data), False, f'SCD4x sample unavailable ({read_exc}); using cached values.'
                    return defaults, False, f'SCD4x sample unavailable ({read_exc}); using fallback values.'

                if data is not None:
                    _last_data = data
                    _last_read_time = time.time()
                    _consecutive_failures = 0
                    return dict(data), True, 'SCD4x hardware read succeeded.'

                _consecutive_failures += 1
                if _consecutive_failures >= 2:
                    try:
                        data = _restart_periodic_and_read(bus)
                    except Exception as recover_exc:
                        if _last_read_time > 0:
                            return dict(_last_data), False, f'SCD4x restart failed ({recover_exc}); using cached values.'
                        return defaults, False, f'SCD4x restart failed ({recover_exc}); using fallback values.'

                    if data is not None:
                        _last_data = data
                        _last_read_time = time.time()
                        _consecutive_failures = 0
                        return dict(data), True, 'SCD4x hardware read recovered after no-ready restart.'

                if _last_read_time > 0:
                    return dict(_last_data), False, 'SCD4x returned no valid CO2 sample; using cached values.'
                return defaults, False, 'SCD4x returned no valid CO2 sample; using fallback values.'
        except Exception as exc:
            print(f'SCD4x read failed: {exc}')
            _consecutive_failures += 1
            if _last_read_time > 0:
                return dict(_last_data), False, f'SCD4x bus error ({exc}); using cached values.'
            return defaults, False, f'SCD4x read failed ({exc}); using fallback values.'


def get_sensor_status():
    cached = SENSOR_STATUS_CACHE.get(PRIMARY_SENSOR_INTERFACE['interface_id'])
    if cached:
        return {**cached, 'checked_at': _iso_now()}

    status = _base_sensor_status()
    if not status['driver_available']:
        status['message'] = 'smbus2 unavailable; SCD4x interface is currently in fallback mode.'
    else:
        status['message'] = 'Primary SCD4x hardware interface is configured and ready.'
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

    battery_dirs = [entry for entry in os.listdir(power_supply_root) if entry.startswith('BAT')]
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


def read_sensor_snapshot(building_id, default_temperature=None, default_humidity=None, default_co2=None):
    status = _base_sensor_status()
    defaults = _default_result(default_temperature, default_humidity, default_co2)

    if building_id != REAL_SENSOR_BUILDING_ID:
        status.update({
            'mode': 'fallback',
            'message': 'This building currently uses configured default values.',
            **defaults,
        })
        return status['temperature'], status['humidity'], _cache_status(status)

    if not SENSOR_AVAILABLE:
        status.update({
            'mode': 'fallback',
            'message': 'smbus2 unavailable; using configured fallback values for SCD4x building.',
            **defaults,
        })
        return status['temperature'], status['humidity'], _cache_status(status)

    data, ok, message = _read_hardware_or_default(defaults)
    status.update({
        **data,
        'last_read_success': ok,
        'mode': 'hardware' if ok else 'fallback',
        'message': message,
    })
    return status['temperature'], status['humidity'], _cache_status(status)


def read_sensor_data(building_id, default_temperature=None, default_humidity=None, default_co2=None):
    temperature, humidity, status = read_sensor_snapshot(
        building_id,
        default_temperature=default_temperature,
        default_humidity=default_humidity,
        default_co2=default_co2,
    )
    return {
        'temperature': round(float(temperature), 1),
        'humidity': round(float(humidity), 1),
        'co2': round(float(status.get('co2', _default_result(default_co2=default_co2)['co2'])), 1),
    }
