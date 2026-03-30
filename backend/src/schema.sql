-- 建筑表
CREATE TABLE IF NOT EXISTS buildings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 投票表
CREATE TABLE IF NOT EXISTS votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    building_id INTEGER NOT NULL,
    too_cold INTEGER DEFAULT 0,
    comfort INTEGER DEFAULT 0,
    too_warm INTEGER DEFAULT 0,
    total INTEGER DEFAULT 0,
    vote_date DATE DEFAULT CURRENT_DATE,
    FOREIGN KEY (building_id) REFERENCES buildings(id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_votes_building_date
ON votes (building_id, vote_date);

-- 传感器数据表
CREATE TABLE IF NOT EXISTS sensor_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    building_id INTEGER NOT NULL,
    temperature REAL NOT NULL,
    humidity REAL NOT NULL,
    read_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (building_id) REFERENCES buildings(id)
);

CREATE INDEX IF NOT EXISTS idx_sensor_data_building_read_time
ON sensor_data (building_id, read_time);

-- 建筑默认配置
CREATE TABLE IF NOT EXISTS building_settings (
    building_id INTEGER PRIMARY KEY,
    default_too_cold INTEGER DEFAULT 0,
    default_comfort INTEGER DEFAULT 0,
    default_too_warm INTEGER DEFAULT 0,
    default_temperature REAL DEFAULT 24.0,
    default_humidity REAL DEFAULT 50.0,
    default_co2 REAL DEFAULT 650.0,
    default_noise REAL DEFAULT 45.0,
    default_light REAL DEFAULT 450.0,
    FOREIGN KEY (building_id) REFERENCES buildings(id)
);

-- 算法权重配置
CREATE TABLE IF NOT EXISTS algorithm_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value REAL NOT NULL
);

-- 聊天会话
CREATE TABLE IF NOT EXISTS chat_sessions (
    id TEXT PRIMARY KEY,
    building_id INTEGER,
    room_label TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (building_id) REFERENCES buildings(id)
);

-- 聊天消息
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    intent TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id)
);

-- 服务请求
CREATE TABLE IF NOT EXISTS service_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    building_id INTEGER,
    room_label TEXT DEFAULT '',
    request_type TEXT NOT NULL,
    severity TEXT DEFAULT 'medium',
    summary TEXT NOT NULL,
    status TEXT DEFAULT 'open',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES chat_sessions(id),
    FOREIGN KEY (building_id) REFERENCES buildings(id)
);
