-- 组合元数据表：从 Python pipeline 同步
CREATE TABLE IF NOT EXISTS combinations (
    id TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    description TEXT,
    entry_rule TEXT,
    exit_rule TEXT,
    factors TEXT,
    updated_at TEXT
);
