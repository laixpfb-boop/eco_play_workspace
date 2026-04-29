import sqlite3
import os
from datetime import date
from uuid import uuid4

# 数据库文件路径（树莓派本地）
BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, 'eco_play.db')
SCHEMA_PATH = os.path.join(BASE_DIR, 'schema.sql')

DEFAULT_ALGORITHM_WEIGHTS = {
    'too_cold': -0.5,
    'comfort': 1.0,
    'too_warm': -0.3,
    'temp_factor': 0.1,
}

def get_db_connection():
    """创建数据库连接"""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row  # 支持按列名访问
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA busy_timeout = 30000')
    return conn

def init_db():
    """初始化数据库（首次运行）"""
    conn = get_db_connection()
    conn.execute('PRAGMA journal_mode = WAL')
    conn.execute('PRAGMA synchronous = NORMAL')
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        conn.executescript(f.read())

    _ensure_building_settings_columns(conn)
    _ensure_comfort_events_table(conn)
    _deduplicate_votes(conn)
    
    # 初始化默认建筑数据
    default_buildings = [
        ('Engineering Hall A',),
        ('Library Building',),
        ('Academic Building',),
        ('Business Building',),
        ('Student Union',),
        ('Shaw Auditorium',),
        ('Sustainability Office',),
    ]
    conn.executemany('INSERT OR IGNORE INTO buildings (name) VALUES (?)', default_buildings)
    
    # 初始化默认投票数据
    default_votes = [
        (1, 89, 245, 67, 401, date.today()),
        (2, 67, 312, 89, 468, date.today()),
        (3, 121, 198, 95, 414, date.today()),
        (4, 145, 156, 78, 379, date.today()),
        (5, 98, 187, 71, 356, date.today()),
        (6, 88, 142, 54, 284, date.today())
    ]
    for building_id, too_cold, comfort, too_warm, total, vote_date in default_votes:
        existing = conn.execute(
            'SELECT 1 FROM votes WHERE building_id = ? AND vote_date = ?',
            (building_id, vote_date),
        ).fetchone()
        if not existing:
            conn.execute(
                '''
                INSERT INTO votes (building_id, too_cold, comfort, too_warm, total, vote_date)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (building_id, too_cold, comfort, too_warm, total, vote_date),
            )

    _ensure_default_building_settings(conn)
    _ensure_default_algorithm_settings(conn)

    conn.commit()
    conn.close()


def _deduplicate_votes(conn):
    """清理历史重复投票记录，保留每栋楼每天最新的一条。"""
    duplicate_groups = conn.execute(
        '''
        SELECT building_id, vote_date, MAX(id) AS keep_id
        FROM votes
        GROUP BY building_id, vote_date
        HAVING COUNT(*) > 1
        '''
    ).fetchall()
    for group in duplicate_groups:
        conn.execute(
            '''
            DELETE FROM votes
            WHERE building_id = ? AND vote_date = ? AND id != ?
            ''',
            (group['building_id'], group['vote_date'], group['keep_id']),
        )


def _ensure_building_settings_columns(conn):
    columns = {
        row['name']
        for row in conn.execute("PRAGMA table_info(building_settings)").fetchall()
    }
    column_specs = {
        'default_co2': 'REAL DEFAULT 650.0',
        'default_noise': 'REAL DEFAULT 45.0',
        'default_light': 'REAL DEFAULT 450.0',
    }
    for column_name, column_sql in column_specs.items():
        if column_name not in columns:
            conn.execute(f'ALTER TABLE building_settings ADD COLUMN {column_name} {column_sql}')


def _ensure_comfort_events_table(conn):
    existing_table = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'comfort_events'"
    ).fetchone()
    if existing_table and "'comfort'" not in (existing_table['sql'] or ''):
        conn.execute('ALTER TABLE comfort_events RENAME TO comfort_events_old')
        _create_comfort_events_table(conn)
        conn.execute(
            '''
            INSERT INTO comfort_events (
                id,
                building_id,
                vote_type,
                delta_count,
                total_after,
                too_cold_after,
                comfort_after,
                too_warm_after,
                sensor_temperature,
                sensor_humidity,
                sensor_co2,
                sensor_read_time,
                notification_status,
                notification_error,
                created_at
            )
            SELECT
                id,
                building_id,
                vote_type,
                delta_count,
                total_after,
                too_cold_after,
                0,
                too_warm_after,
                NULL,
                NULL,
                NULL,
                '',
                notification_status,
                notification_error,
                created_at
            FROM comfort_events_old
            '''
        )
        conn.execute('DROP TABLE comfort_events_old')
    else:
        _create_comfort_events_table(conn)

    columns = {
        row['name']
        for row in conn.execute("PRAGMA table_info(comfort_events)").fetchall()
    }
    if 'comfort_after' not in columns:
        conn.execute('ALTER TABLE comfort_events ADD COLUMN comfort_after INTEGER NOT NULL DEFAULT 0')
    sensor_column_specs = {
        'sensor_temperature': 'REAL',
        'sensor_humidity': 'REAL',
        'sensor_co2': 'REAL',
        'sensor_read_time': "TEXT DEFAULT ''",
    }
    for column_name, column_sql in sensor_column_specs.items():
        if column_name not in columns:
            conn.execute(f'ALTER TABLE comfort_events ADD COLUMN {column_name} {column_sql}')
    _ensure_comfort_events_indexes(conn)


def _create_comfort_events_table(conn):
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS comfort_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            building_id INTEGER NOT NULL,
            vote_type TEXT NOT NULL CHECK (vote_type IN ('too_cold', 'comfort', 'too_warm')),
            delta_count INTEGER NOT NULL DEFAULT 1,
            total_after INTEGER NOT NULL DEFAULT 0,
            too_cold_after INTEGER NOT NULL DEFAULT 0,
            comfort_after INTEGER NOT NULL DEFAULT 0,
            too_warm_after INTEGER NOT NULL DEFAULT 0,
            sensor_temperature REAL,
            sensor_humidity REAL,
            sensor_co2 REAL,
            sensor_read_time TEXT DEFAULT '',
            notification_status TEXT DEFAULT 'pending',
            notification_error TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (building_id) REFERENCES buildings(id)
        )
        '''
    )


def _ensure_comfort_events_indexes(conn):
    conn.execute(
        '''
        CREATE INDEX IF NOT EXISTS idx_comfort_events_created_at
        ON comfort_events (created_at)
        '''
    )
    conn.execute(
        '''
        CREATE INDEX IF NOT EXISTS idx_comfort_events_building_created_at
        ON comfort_events (building_id, created_at)
        '''
    )


def _ensure_default_building_settings(conn):
    building_rows = conn.execute('SELECT id FROM buildings ORDER BY id').fetchall()
    for building in building_rows:
        building_id = building['id']
        existing = conn.execute(
            'SELECT 1 FROM building_settings WHERE building_id = ?',
            (building_id,),
        ).fetchone()
        if existing:
            continue

        default_votes = conn.execute(
            '''
            SELECT too_cold, comfort, too_warm
            FROM votes
            WHERE building_id = ?
            ORDER BY vote_date DESC, id DESC
            LIMIT 1
            ''',
            (building_id,),
        ).fetchone()
        too_cold = default_votes['too_cold'] if default_votes else 0
        comfort = default_votes['comfort'] if default_votes else 0
        too_warm = default_votes['too_warm'] if default_votes else 0
        conn.execute(
            '''
            INSERT INTO building_settings (
                building_id,
                default_too_cold,
                default_comfort,
                default_too_warm,
                default_temperature,
                default_humidity,
                default_co2,
                default_noise,
                default_light
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (building_id, too_cold, comfort, too_warm, 24.0, 50.0, 650.0, 45.0, 450.0),
        )


def _ensure_default_algorithm_settings(conn):
    for key, value in DEFAULT_ALGORITHM_WEIGHTS.items():
        conn.execute(
            '''
            INSERT OR IGNORE INTO algorithm_settings (setting_key, setting_value)
            VALUES (?, ?)
            ''',
            (key, value),
        )

# ========== 建筑CRUD ==========
def get_all_buildings():
    """获取所有建筑"""
    conn = get_db_connection()
    buildings = conn.execute('SELECT * FROM buildings').fetchall()
    conn.close()
    return [dict(b) for b in buildings]

def get_building_by_name(name):
    """按名称获取建筑"""
    conn = get_db_connection()
    building = conn.execute('SELECT * FROM buildings WHERE name = ?', (name,)).fetchone()
    conn.close()
    return dict(building) if building else None


def get_building_by_id(building_id):
    """按ID获取建筑"""
    conn = get_db_connection()
    building = conn.execute('SELECT * FROM buildings WHERE id = ?', (building_id,)).fetchone()
    conn.close()
    return dict(building) if building else None

def add_building(name, description=''):
    """添加建筑"""
    conn = get_db_connection()
    cursor = conn.execute('INSERT INTO buildings (name, description) VALUES (?, ?)', (name, description))
    building_id = cursor.lastrowid
    conn.execute(
        '''
        INSERT INTO building_settings (
            building_id,
            default_too_cold,
            default_comfort,
            default_too_warm,
            default_temperature,
            default_humidity,
            default_co2,
            default_noise,
            default_light
        )
        VALUES (?, 0, 0, 0, 24.0, 50.0, 650.0, 45.0, 450.0)
        ''',
        (building_id,),
    )
    conn.commit()
    conn.close()

def update_building(id, name, description=''):
    """更新建筑"""
    conn = get_db_connection()
    conn.execute('UPDATE buildings SET name = ?, description = ? WHERE id = ?', (name, description, id))
    conn.commit()
    conn.close()

def delete_building(id):
    """删除建筑（级联删除投票/传感器数据）"""
    conn = get_db_connection()
    conn.execute('DELETE FROM votes WHERE building_id = ?', (id,))
    conn.execute('DELETE FROM sensor_data WHERE building_id = ?', (id,))
    conn.execute('DELETE FROM building_settings WHERE building_id = ?', (id,))
    conn.execute('DELETE FROM buildings WHERE id = ?', (id,))
    conn.commit()
    conn.close()

# ========== 投票CRUD ==========
def get_votes_by_building_date(building_id, vote_date=None):
    """按建筑+日期获取投票数据"""
    target_date = vote_date or date.today()
    conn = get_db_connection()
    votes = conn.execute(
        '''
        SELECT * FROM votes
        WHERE building_id = ? AND vote_date = ?
        ORDER BY id DESC
        LIMIT 1
        ''',
        (building_id, target_date),
    ).fetchone()
    conn.close()
    return dict(votes) if votes else None

def update_votes(building_id, too_cold, comfort, too_warm, total, vote_date=None):
    """更新投票数据，不存在则插入。"""
    target_date = vote_date or date.today()
    conn = get_db_connection()
    existing = conn.execute(
        'SELECT id FROM votes WHERE building_id = ? AND vote_date = ? ORDER BY id DESC LIMIT 1',
        (building_id, target_date),
    ).fetchone()
    if existing:
        conn.execute(
            '''
            UPDATE votes
            SET too_cold = ?, comfort = ?, too_warm = ?, total = ?
            WHERE id = ?
            ''',
            (too_cold, comfort, too_warm, total, existing['id']),
        )
        conn.execute(
            '''
            DELETE FROM votes
            WHERE building_id = ? AND vote_date = ? AND id != ?
            ''',
            (building_id, target_date, existing['id']),
        )
    else:
        conn.execute(
            '''
            INSERT INTO votes (building_id, too_cold, comfort, too_warm, total, vote_date)
            VALUES (?, ?, ?, ?, ?, ?)
            ''',
            (building_id, too_cold, comfort, too_warm, total, target_date),
        )
    conn.commit()
    conn.close()


def add_comfort_event(
    building_id,
    vote_type,
    delta_count,
    total_after,
    too_cold_after,
    comfort_after,
    too_warm_after,
    sensor_temperature=None,
    sensor_humidity=None,
    sensor_co2=None,
    sensor_read_time='',
    notification_status='pending',
    notification_error='',
):
    conn = get_db_connection()
    cursor = conn.execute(
        '''
        INSERT INTO comfort_events (
            building_id,
            vote_type,
            delta_count,
            total_after,
            too_cold_after,
            comfort_after,
            too_warm_after,
            sensor_temperature,
            sensor_humidity,
            sensor_co2,
            sensor_read_time,
            notification_status,
            notification_error
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            building_id,
            vote_type,
            delta_count,
            total_after,
            too_cold_after,
            comfort_after,
            too_warm_after,
            sensor_temperature,
            sensor_humidity,
            sensor_co2,
            sensor_read_time,
            notification_status,
            notification_error,
        ),
    )
    event_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return event_id


def update_comfort_event_notification(event_id, notification_status, notification_error=''):
    conn = get_db_connection()
    conn.execute(
        '''
        UPDATE comfort_events
        SET notification_status = ?, notification_error = ?
        WHERE id = ?
        ''',
        (notification_status, notification_error, event_id),
    )
    conn.commit()
    conn.close()


def get_comfort_events(limit=100, building_id=None):
    conn = get_db_connection()
    params = []
    where_sql = ''
    if building_id is not None:
        where_sql = 'WHERE ce.building_id = ?'
        params.append(building_id)
    params.append(limit)
    rows = conn.execute(
        f'''
        SELECT
            ce.*,
            b.name AS building_name
        FROM comfort_events ce
        JOIN buildings b ON b.id = ce.building_id
        {where_sql}
        ORDER BY ce.id DESC
        LIMIT ?
        ''',
        params,
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_comfort_event_summary(days=7, building_id=None):
    conn = get_db_connection()
    params = [f'-{days} days']
    where_parts = ["ce.created_at >= datetime('now', ?)"]
    if building_id is not None:
        where_parts.append('ce.building_id = ?')
        params.append(building_id)
    where_sql = ' AND '.join(where_parts)
    rows = conn.execute(
        f'''
        SELECT
            b.id AS building_id,
            b.name AS building_name,
            ce.vote_type,
            SUM(ce.delta_count) AS event_count,
            COUNT(*) AS interaction_count,
            MAX(ce.created_at) AS latest_event_at
        FROM comfort_events ce
        JOIN buildings b ON b.id = ce.building_id
        WHERE {where_sql}
        GROUP BY b.id, b.name, ce.vote_type
        ORDER BY event_count DESC, latest_event_at DESC
        ''',
        params,
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]

def add_votes(building_id, too_cold=0, comfort=0, too_warm=0, total=0, vote_date=None):
    """新增投票数据"""
    target_date = vote_date or date.today()
    conn = get_db_connection()
    conn.execute('''
        INSERT INTO votes (building_id, too_cold, comfort, too_warm, total, vote_date)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (building_id, too_cold, comfort, too_warm, total, target_date))
    conn.commit()
    conn.close()


def ensure_votes_for_date(building_id, vote_date=None):
    """如果当日投票不存在，则按默认配置创建。"""
    target_date = vote_date or date.today()
    existing = get_votes_by_building_date(building_id, target_date)
    if existing:
        return existing

    settings = get_building_settings(building_id)
    too_cold = settings['default_too_cold'] if settings else 0
    comfort = settings['default_comfort'] if settings else 0
    too_warm = settings['default_too_warm'] if settings else 0
    total = too_cold + comfort + too_warm
    add_votes(building_id, too_cold, comfort, too_warm, total, target_date)
    return get_votes_by_building_date(building_id, target_date)

# ========== 传感器数据CRUD ==========
def add_sensor_data(building_id, temperature, humidity):
    """添加传感器数据"""
    conn = get_db_connection()
    conn.execute('INSERT INTO sensor_data (building_id, temperature, humidity) VALUES (?, ?, ?)', (building_id, temperature, humidity))
    conn.commit()
    conn.close()

def get_latest_sensor_data(building_id):
    """获取建筑最新传感器数据"""
    conn = get_db_connection()
    data = conn.execute('''
        SELECT * FROM sensor_data 
        WHERE building_id = ? 
        ORDER BY read_time DESC LIMIT 1
    ''', (building_id,)).fetchone()
    conn.close()
    return dict(data) if data else None


def get_building_settings(building_id):
    conn = get_db_connection()
    settings = conn.execute(
        'SELECT * FROM building_settings WHERE building_id = ?',
        (building_id,),
    ).fetchone()
    conn.close()
    return dict(settings) if settings else None


def update_building_settings(
    building_id,
    too_cold,
    comfort,
    too_warm,
    temperature,
    humidity,
    co2=650.0,
    noise=45.0,
    light=450.0,
    apply_today=False,
):
    conn = get_db_connection()
    conn.execute(
        '''
        INSERT INTO building_settings (
            building_id,
            default_too_cold,
            default_comfort,
            default_too_warm,
            default_temperature,
            default_humidity,
            default_co2,
            default_noise,
            default_light
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(building_id) DO UPDATE SET
            default_too_cold = excluded.default_too_cold,
            default_comfort = excluded.default_comfort,
            default_too_warm = excluded.default_too_warm,
            default_temperature = excluded.default_temperature,
            default_humidity = excluded.default_humidity,
            default_co2 = excluded.default_co2,
            default_noise = excluded.default_noise,
            default_light = excluded.default_light
        ''',
        (building_id, too_cold, comfort, too_warm, temperature, humidity, co2, noise, light),
    )
    if apply_today:
        total = too_cold + comfort + too_warm
        existing = conn.execute(
            'SELECT id FROM votes WHERE building_id = ? AND vote_date = ? ORDER BY id DESC LIMIT 1',
            (building_id, date.today()),
        ).fetchone()
        if existing:
            conn.execute(
                '''
                UPDATE votes
                SET too_cold = ?, comfort = ?, too_warm = ?, total = ?
                WHERE id = ?
                ''',
                (too_cold, comfort, too_warm, total, existing['id']),
            )
        else:
            conn.execute(
                '''
                INSERT INTO votes (building_id, too_cold, comfort, too_warm, total, vote_date)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (building_id, too_cold, comfort, too_warm, total, date.today()),
            )
    conn.commit()
    conn.close()


def get_algorithm_weights():
    conn = get_db_connection()
    rows = conn.execute('SELECT setting_key, setting_value FROM algorithm_settings').fetchall()
    conn.close()
    weights = DEFAULT_ALGORITHM_WEIGHTS.copy()
    for row in rows:
        weights[row['setting_key']] = row['setting_value']
    return weights


def update_algorithm_weights(weights):
    conn = get_db_connection()
    for key, value in weights.items():
        conn.execute(
            '''
            INSERT INTO algorithm_settings (setting_key, setting_value)
            VALUES (?, ?)
            ON CONFLICT(setting_key) DO UPDATE SET
                setting_value = excluded.setting_value
            ''',
            (key, value),
        )
    conn.commit()
    conn.close()


def get_settings_overview():
    conn = get_db_connection()
    rows = conn.execute(
        '''
        SELECT
            b.id,
            b.name,
            COALESCE(b.description, '') AS description,
            COALESCE(bs.default_too_cold, 0) AS default_too_cold,
            COALESCE(bs.default_comfort, 0) AS default_comfort,
            COALESCE(bs.default_too_warm, 0) AS default_too_warm,
            COALESCE(bs.default_temperature, 24.0) AS default_temperature,
            COALESCE(bs.default_humidity, 50.0) AS default_humidity,
            COALESCE(bs.default_co2, 650.0) AS default_co2,
            COALESCE(bs.default_noise, 45.0) AS default_noise,
            COALESCE(bs.default_light, 450.0) AS default_light
        FROM buildings b
        LEFT JOIN building_settings bs ON bs.building_id = b.id
        ORDER BY b.id
        '''
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def create_chat_session(building_id=None, room_label=''):
    session_id = str(uuid4())
    conn = get_db_connection()
    conn.execute(
        '''
        INSERT INTO chat_sessions (id, building_id, room_label)
        VALUES (?, ?, ?)
        ''',
        (session_id, building_id, room_label),
    )
    conn.commit()
    conn.close()
    return session_id


def get_chat_session(session_id):
    conn = get_db_connection()
    session = conn.execute(
        'SELECT * FROM chat_sessions WHERE id = ?',
        (session_id,),
    ).fetchone()
    conn.close()
    return dict(session) if session else None


def update_chat_session(session_id, building_id=None, room_label=None):
    conn = get_db_connection()
    current = conn.execute('SELECT * FROM chat_sessions WHERE id = ?', (session_id,)).fetchone()
    if not current:
        conn.close()
        return False

    next_building_id = current['building_id'] if building_id is None else building_id
    next_room_label = current['room_label'] if room_label is None else room_label
    conn.execute(
        '''
        UPDATE chat_sessions
        SET building_id = ?, room_label = ?, last_active_at = CURRENT_TIMESTAMP
        WHERE id = ?
        ''',
        (next_building_id, next_room_label, session_id),
    )
    conn.commit()
    conn.close()
    return True


def add_chat_message(session_id, role, content, intent=''):
    conn = get_db_connection()
    conn.execute(
        '''
        INSERT INTO chat_messages (session_id, role, content, intent)
        VALUES (?, ?, ?, ?)
        ''',
        (session_id, role, content, intent),
    )
    conn.execute(
        '''
        UPDATE chat_sessions
        SET last_active_at = CURRENT_TIMESTAMP
        WHERE id = ?
        ''',
        (session_id,),
    )
    conn.commit()
    conn.close()


def get_chat_messages(session_id, limit=20):
    conn = get_db_connection()
    rows = conn.execute(
        '''
        SELECT * FROM chat_messages
        WHERE session_id = ?
        ORDER BY id DESC
        LIMIT ?
        ''',
        (session_id, limit),
    ).fetchall()
    conn.close()
    messages = [dict(row) for row in rows]
    messages.reverse()
    return messages


def create_service_request(session_id, building_id, room_label, request_type, severity, summary):
    conn = get_db_connection()
    cursor = conn.execute(
        '''
        INSERT INTO service_requests (
            session_id,
            building_id,
            room_label,
            request_type,
            severity,
            summary,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, 'open')
        ''',
        (session_id, building_id, room_label, request_type, severity, summary),
    )
    request_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return request_id


def get_open_service_requests(session_id):
    conn = get_db_connection()
    rows = conn.execute(
        '''
        SELECT * FROM service_requests
        WHERE session_id = ? AND status = 'open'
        ORDER BY id DESC
        ''',
        (session_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def close_service_request(request_id):
    conn = get_db_connection()
    cursor = conn.execute(
        '''
        UPDATE service_requests
        SET status = 'closed', updated_at = CURRENT_TIMESTAMP
        WHERE id = ? AND status != 'closed'
        ''',
        (request_id,),
    )
    conn.commit()
    updated = cursor.rowcount
    conn.close()
    return updated > 0


def delete_chat_message(message_id):
    conn = get_db_connection()
    cursor = conn.execute(
        'DELETE FROM chat_messages WHERE id = ?',
        (message_id,),
    )
    conn.commit()
    deleted = cursor.rowcount
    conn.close()
    return deleted > 0


def get_vote_sensor_export_rows():
    conn = get_db_connection()
    rows = conn.execute(
        '''
        WITH sensor_daily AS (
            SELECT
                building_id,
                DATE(read_time) AS sensor_date,
                ROUND(AVG(temperature), 2) AS avg_temperature,
                ROUND(AVG(humidity), 2) AS avg_humidity,
                COUNT(*) AS sensor_samples
            FROM sensor_data
            GROUP BY building_id, DATE(read_time)
        )
        SELECT
            b.id AS building_id,
            b.name AS building_name,
            COALESCE(b.description, '') AS building_description,
            v.vote_date,
            v.too_cold,
            v.comfort,
            v.too_warm,
            v.total,
            sd.avg_temperature,
            sd.avg_humidity,
            COALESCE(sd.sensor_samples, 0) AS sensor_samples
        FROM votes v
        JOIN buildings b ON b.id = v.building_id
        LEFT JOIN sensor_daily sd ON sd.building_id = v.building_id AND sd.sensor_date = v.vote_date
        ORDER BY v.vote_date DESC, b.id ASC
        '''
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_comfort_analysis_rows():
    conn = get_db_connection()
    rows = conn.execute(
        '''
        WITH sensor_daily AS (
            SELECT
                building_id,
                DATE(read_time) AS sensor_date,
                AVG(temperature) AS avg_temperature,
                AVG(humidity) AS avg_humidity
            FROM sensor_data
            GROUP BY building_id, DATE(read_time)
        )
        SELECT
            b.id AS building_id,
            b.name AS building_name,
            v.vote_date,
            v.total,
            CASE WHEN v.total > 0 THEN ROUND((v.comfort * 100.0) / v.total, 2) ELSE 0 END AS comfort_percent,
            sd.avg_temperature,
            sd.avg_humidity
        FROM votes v
        JOIN buildings b ON b.id = v.building_id
        LEFT JOIN sensor_daily sd ON sd.building_id = v.building_id AND sd.sensor_date = v.vote_date
        WHERE v.total > 0
        ORDER BY v.vote_date DESC, b.id ASC
        '''
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]
