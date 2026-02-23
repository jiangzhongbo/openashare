-- 0001_initial_schema.sql
-- D1 数据库初始化脚本

-- 股票列表
CREATE TABLE IF NOT EXISTS stocks (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    market TEXT,
    updated_at TEXT
);

-- 筛选结果（每日通过的股票 + 关键因子值）
-- 每行是一个不可变快照：记录当天哪只股票通过了哪个组合
-- 同一股票同一天可以有多行（通过多个组合各存一行）
-- 组合定义变更不会回溯修改历史记录
CREATE TABLE IF NOT EXISTS screening_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    combination TEXT NOT NULL,   -- 组合 ID，e.g. "watch" / "buy"
    code TEXT NOT NULL,
    name TEXT,
    latest_price REAL,
    ma60_change_pct REAL,
    ma60_angle REAL,
    ma20_change_pct REAL,
    ma_distance REAL,
    macd_days_ago INTEGER,
    rsi REAL,
    turnover_avg REAL,
    n_day_return REAL,
    passed_factors TEXT,         -- JSON: ["ma60_monotonic","macd_golden_cross",...]
    factor_config_snapshot TEXT, -- JSON: 当次运行的因子参数快照，便于回溯
    created_at TEXT
);

-- 运行日志
CREATE TABLE IF NOT EXISTS run_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    total_stocks INTEGER,
    passed_stocks INTEGER,
    duration_seconds REAL,
    status TEXT,
    error_msg TEXT,
    created_at TEXT
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_screening_run_date ON screening_results(run_date);
CREATE INDEX IF NOT EXISTS idx_screening_code ON screening_results(code);
CREATE INDEX IF NOT EXISTS idx_screening_run_combination ON screening_results(run_date, combination);
CREATE INDEX IF NOT EXISTS idx_run_logs_date ON run_logs(run_date);

