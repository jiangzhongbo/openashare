# Plan 0001: A股量化选股工具

## 目标

构建一个给操盘手使用的全栈选股工具。每日自动筛选 A 股中满足技术面指标的股票，结果展示在 Web 界面，减少人工刷选时间。

## 状态

- [ ] 未开始

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 数据管道 | Python + BaoStock + AKShare | 每日拉取行情，计算因子 |
| 调度 | GitHub Actions | 每日 16:30 北京时间自动触发 |
| 数据库 | Cloudflare D1 (SQLite) | 存储筛选结果和运行日志，仅 Worker 直接访问 |
| API / 数据网关 | Cloudflare Worker | 统一入口：POST 写入（鉴权）+ GET 读取（公开） |
| 前端 | 纯静态 HTML + 原生 JS | 部署在 CF Pages，调用 Worker GET 接口渲染数据 |
| 缓存 | GitHub Actions Cache | 本地 SQLite 断点续传，避免每次全量下载 |

### 数据流向

```
写入：GitHub Actions (Python)
         └─→ CF Worker POST /api/ingest  (带 WORKER_WRITE_TOKEN 鉴权)
                 └─→ CF D1 数据库

读取：浏览器 (静态 HTML)
         └─→ CF Worker GET /api/*  (无鉴权)
                 └─→ CF D1 数据库

本地测试：wrangler dev（localhost:8787）
         ├─→ 写入：Python 指向 localhost:8787，数据落本地 SQLite
         └─→ 读取：浏览器指向 localhost:8787，与生产完全一致
```

## 项目结构

```
openashare/
├── .github/workflows/
│   └── daily-screening.yml     # 每日定时任务
├── pipeline/                   # Python 数据管道
│   ├── data/
│   │   ├── fetcher.py          # BaoStock 数据获取（重构自 Demo）
│   │   └── local_db.py         # 本地 SQLite 缓存（GitHub Actions 断点续传）
│   ├── factors/
│   │   ├── base.py             # Factor 抽象基类
│   │   ├── registry.py         # 因子注册表（控制启用/禁用、参数）
│   │   ├── ma60_monotonic.py   # 因子1: MA60 单调不减
│   │   ├── ma20_consolidation.py # 因子2: MA20 整盘
│   │   ├── ma_distance.py      # 因子3: MA20/MA60 距离
│   │   ├── macd_golden_cross.py # 因子4: MACD 金叉
│   │   ├── rsi.py              # 因子5: RSI 超卖反弹（新增）
│   │   ├── turnover.py         # 因子6: 换手率适中（新增）
│   │   └── n_day_return.py     # 因子7: N日涨幅区间（新增）
│   ├── sync/
│   │   └── worker_client.py    # Worker HTTP 客户端（POST 写入，URL 可配）
│   ├── tests/
│   │   ├── unit/
│   │   │   ├── test_factors.py      # 7 个因子的 compute() 单元测试
│   │   │   ├── test_screener.py     # 交集逻辑单元测试
│   │   │   └── test_local_db.py     # SQLite 数据保留/清理逻辑
│   │   ├── mock/
│   │   │   ├── test_fetcher_errors.py      # BaoStock 失败/重试
│   │   │   └── test_worker_client_errors.py # Worker 写入失败/边界
│   │   └── integration/
│   │       └── test_pipeline.py    # 完整管道（需 wrangler dev 运行）
│   ├── screener.py             # 交集筛选主逻辑（向量化）
│   ├── main.py                 # 管道入口
│   └── requirements.txt
├── worker/                     # Cloudflare Worker（读写统一入口）
│   ├── src/
│   │   ├── index.ts            # Worker 入口：POST /api/ingest + GET /api/*
│   │   └── tests/
│   │       ├── unit/
│   │       │   └── index.test.ts       # 路由匹配、鉴权、响应格式
│   │       ├── mock/
│   │       │   └── d1_errors.test.ts   # D1 失败、非法 payload、缺 token
│   │       └── integration/
│   │           └── api.test.ts         # 真实 HTTP 打 wrangler dev 接口
│   ├── wrangler.toml           # D1 binding + WORKER_WRITE_TOKEN secret 配置
│   └── package.json
├── web/                        # 纯静态前端
│   └── index.html              # 单文件，原生 JS 调用 Worker API
├── migrations/
│   └── 0001_initial_schema.sql # D1 建表 SQL
└── docs/plans/
    └── 0001-stock-screener.md
```

### 如何添加新因子

1. 在 `pipeline/factors/` 新建一个 `.py` 文件，继承 `Factor` 基类
2. 实现 `compute(df: pd.DataFrame) -> FactorResult` 方法
3. 在 `pipeline/factors/registry.py` 注册（一行代码）
4. 新因子立即生效，历史记录该列显示 `null`（不追溯）

## 本地 SQLite Schema（GitHub Actions Cache）

原始 K 线数据只存在 Python pipeline 的本地 SQLite 里（GitHub Actions Cache），**不写入 D1**。

```sql
-- 日线数据（滚动保留最近 250 个交易日）
-- MA5/10/20/60 在筛选时由 pandas rolling 实时计算，不预存
CREATE TABLE daily_kline (
    code    TEXT NOT NULL,
    date    TEXT NOT NULL,
    open    REAL,
    high    REAL,
    low     REAL,
    close   REAL,
    volume  REAL,   -- 成交量（股）
    amount  REAL,   -- 成交额（元）
    turn    REAL,   -- 换手率（%），BaoStock 直接提供
    pct_chg REAL,   -- 当日涨跌幅（%），BaoStock 直接提供
    PRIMARY KEY (code, date)
);

CREATE INDEX IF NOT EXISTS idx_kline_date ON daily_kline(date);
CREATE INDEX IF NOT EXISTS idx_kline_code ON daily_kline(code);
```

### 数据保留策略

| 存储位置 | 保留窗口 | 原因 | 超出是否删除 |
|---------|---------|------|------------|
| 本地 SQLite（Actions Cache）| **250 个交易日**（≈1 年）| MA60 单调检查需要约 190 天有效 MA60 值 | ✅ 每次运行前清理 |
| D1 `screening_results` | **永久保留** | 筛选结果是操作日志，不删 | ❌ |
| D1 `run_logs` | **永久保留** | 运行记录量极小 | ❌ |

---

## D1 数据库 Schema（Cloudflare D1，存筛选结果）

```sql
-- 股票列表
CREATE TABLE stocks (
    code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    market TEXT,
    updated_at TEXT
);

-- 筛选结果（每日通过的股票 + 关键因子值）
-- 每行是一个不可变快照：记录当天哪只股票通过了哪个组合
-- 同一股票同一天可以有多行（通过多个组合各存一行）
-- 组合定义变更不会回溯修改历史记录
CREATE TABLE screening_results (
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
CREATE TABLE run_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    total_stocks INTEGER,
    passed_stocks INTEGER,
    duration_seconds REAL,
    status TEXT,
    error_msg TEXT,
    created_at TEXT
);

CREATE INDEX idx_screening_run_date ON screening_results(run_date);
CREATE INDEX idx_screening_code ON screening_results(code);
CREATE INDEX idx_screening_run_combination ON screening_results(run_date, combination);
```

## 因子清单

因子是**原子计算单元**，只关心自己的计算逻辑，不感知自己属于哪个组合。

| # | 因子 ID | 因子名 | 依赖字段 | 默认参数 | 逻辑 |
|---|---------|--------|---------|---------|------|
| 1 | `ma60_monotonic` | MA60 单调不减 | `close` → MA60 | min_change=1% | 全部 MA60 历史无下降 + 总涨幅 ≥ 1% |
| 2 | `ma20_consolidation` | MA20 整盘 | `close` → MA20 | check_days=20, max_rise=1% | 近 20 天 MA20 涨幅 ≤ 1% |
| 3 | `ma_distance` | MA20/MA60 距离 | `close` → MA20/MA60 | check_days=5, max_dist=10% | 两线偏差 ≤ 10% |
| 4 | `macd_golden_cross` | MACD 金叉 | `close` → EMA12/26/Signal | check_days=2 | 近 2 天内 MACD 线上穿信号线 |
| 5 | `rsi` | RSI 超卖反弹 | `close` → RSI14 | oversold=35 | RSI 从超卖区（<35）向上穿越 |
| 6 | `turnover` | 换手率适中 | `turn`（直接使用） | check_days=5, min=1%, max=10% | 近 5 天平均换手率在 1%~10% |
| 7 | `n_day_return` | N日涨幅区间 | `close` 或 `pct_chg` | days=20, min=-5%, max=15% | 近 20 日累计涨幅在合理区间 |

> - MA5/MA10/MA20/MA60 均在筛选时由 `close` 字段实时计算，不预存
> - `turn`、`pct_chg` 由 BaoStock 直接提供，已存入本地 SQLite
> - 参数通过 GitHub Actions 环境变量覆盖，格式：`FACTOR_<ID>_<PARAM>`

---

## 组合定义

组合是**因子 ID 的有序集合**，定义在 `pipeline/factors/registry.py` 中。一只股票若该组合内所有因子全部通过，则出现在该组合的筛选结果里。

```python
# pipeline/factors/registry.py（示意）
COMBINATIONS = [
    Combination(
        id="ma60_bounce_uptrend",
        label="MA60支撑反弹+趋势向上",
        description="捕捉跌破MA60支撑后的强力反弹信号，同时确保MA60处于上升趋势中。适合短线交易，后续在阴线时择机进入。",
        factors=["ma60_bounce_volume", "ma60_recent_uptrend"],
    ),
]
```

**Combination 字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | str | 组合唯一标识，用于 API 查询和数据库存储 |
| `label` | str | 组合显示名称，用于前端展示 |
| `description` | str | 组合详细描述，解释策略逻辑和使用场景 |
| `factors` | List[str] | 因子 ID 列表，所有因子必须全部通过（AND 逻辑） |

**关键设计原则：**

| 原则 | 说明 |
|------|------|
| 因子与组合解耦 | 同一个因子可出现在多个组合中，修改因子逻辑不影响组合定义 |
| 组合定义在代码里 | 通过修改 `registry.py` 增删组合，无需改数据库 Schema |
| 组合元数据通过 API 暴露 | Worker 提供 `GET /api/combinations` 返回所有组合的元数据（id/label/description/factors） |
| 历史记录按组合快照 | `combination` 字段记录当时的组合 ID，组合改变不回溯历史 |
| 每只股票每个组合一行 | 同一天同一股票通过两个组合，写两行，方便 SQL 按组合查询 |
| 前端动态渲染 | 前端通过 API 获取组合列表，动态生成 Tab 页面，无需硬编码 |

---

## Worker API 端点

### `GET /api/combinations`

返回所有组合的元数据，用于前端动态渲染 Tab 页面。

**响应格式：**
```json
{
  "combinations": [
    {
      "id": "ma60_bounce_uptrend",
      "label": "MA60支撑反弹+趋势向上",
      "description": "捕捉跌破MA60支撑后的强力反弹信号，同时确保MA60处于上升趋势中。适合短线交易，后续在阴线时择机进入。",
      "factors": ["ma60_bounce_volume", "ma60_recent_uptrend"]
    }
  ]
}
```

**实现方式：**
- Worker 内部硬编码组合定义（与 `registry.py` 保持同步）
- 或通过环境变量注入组合定义 JSON（更灵活，但增加复杂度）
- **推荐方案**：硬编码，修改组合时同步更新 Worker 代码

### `GET /api/screening/latest?combination=<id>`

返回指定组合的最新筛选结果。

**查询参数：**
- `combination`（可选）：组合 ID，不传则返回所有组合的结果

**响应格式：**
```json
{
  "data": [
    {
      "code": "300719",
      "name": "...",
      "combination": "ma60_bounce_uptrend",
      "latest_price": 20.89,
      "passed_factors": ["ma60_bounce_volume", "ma60_recent_uptrend"],
      "...": "..."
    }
  ]
}
```

## 测试策略

遵循方法论的 4 层测试策略，**从底层开始写，逐层向上**。每一层全部通过后再写上一层。

### 工具选型

| 端 | 框架 | 覆盖率 | 运行命令 |
|----|------|--------|---------|
| Python pipeline | `pytest` + `pytest-cov` | ≥ 80% | `pytest pipeline/tests/` |
| CF Worker (TypeScript) | `vitest`（wrangler 内置） | ≥ 80% | `cd worker && npm test` |

---

### Layer 1：单元测试（纯函数，无外部依赖）

**Python — 因子逻辑**（`pipeline/tests/unit/test_factors.py`）

每个因子用合成 DataFrame 测试，覆盖以下场景：

| 因子 | 正常通过 case | 不通过 case | 边界 case |
|------|-------------|------------|----------|
| MA60 单调不减 | 60天稳定上涨 close | 中间有一天 MA60 下降 | 恰好 60 条数据 |
| MA20 整盘 | 近 20 天 MA20 持平 | MA20 涨幅 > 1% | 数据不足 20 天 |
| MA20/MA60 距离 | 两线偏差 5% | 偏差 15% | MA60 为 NaN |
| MACD 金叉 | 昨天发生金叉 | 金叉在 3 天前 | 数据不足 26 天（EMA 计算） |
| RSI | RSI 从 30 上穿 35 | RSI 从 40 下降 | 数据不足 14 天 |
| 换手率适中 | 近 5 天均换手 3% | 均换手 15%（过热） | turn 字段全为 0（停牌） |
| N日涨幅区间 | 20 日涨幅 8% | 20 日涨幅 25%（暴涨） | 数据不足 20 天 |

**Python — 组合评估逻辑**（`pipeline/tests/unit/test_combinations.py`）

- watch 组合所有因子通过 → 该股票出现在 watch 结果
- buy 组合所有因子通过 → 该股票出现在 buy 结果（同时也会出现在 watch）
- watch 通过但 buy 不通过 → 只出现在 watch，不出现在 buy
- 两个组合都不通过 → 股票不在任何结果中
- 空市场数据 → 两个组合都返回空结果，不报错

**Python — 本地 SQLite 保留策略**（`pipeline/tests/unit/test_local_db.py`）

- 写入 260 条数据后，清理函数只保留最近 250 个交易日
- 重复写入同一 (code, date) → upsert 不报错，数据更新

**Worker — 路由与响应**（`worker/src/tests/unit/index.test.ts`）

- `GET /api/screening/latest` → 返回 `{data: [...], run_date: "..."}`
- `GET /api/screening/history` → 返回历史列表
- `GET /api/stocks/:code` → 返回单股历史
- `POST /api/ingest` 无 token → 返回 `403`
- `GET /unknown` → 返回 `404`

---

### Layer 2：Mock 测试（错误处理、边界情况）

**Python — 外部依赖失败**（`pipeline/tests/mock/`）

| 场景 | 期望行为 |
|------|---------|
| BaoStock `query_history_k_data_plus` 返回空 DataFrame | 跳过该股票，继续处理，记录 warning |
| BaoStock 连续 3 次抛出网络异常 | 指数退避重试 3 次后放弃，写 error log |
| Worker POST 返回 `500` | 重试 3 次，全部失败后整个 run 标记失败 |
| Worker POST 返回 `403` | 立即终止，不重试，抛出 `AuthError` |
| 某股票历史数据全为 NaN close | 所有因子返回 `passed=False`，不抛异常 |
| 某股票数据仅 30 天（不足 60 天） | MA60 因子返回 `passed=False`，原因注明"数据不足" |

**Worker — D1 与 Payload 异常**（`worker/src/tests/mock/d1_errors.test.ts`）

| 场景 | 期望行为 |
|------|---------|
| D1 `prepare().all()` 抛出异常 | GET 接口返回 `500 {"error": "db_error"}` |
| POST payload 缺少 `run_date` 字段 | 返回 `400 {"error": "missing_field"}` |
| POST payload `results` 字段为非数组 | 返回 `400 {"error": "invalid_format"}` |
| POST token 格式正确但值错误 | 返回 `403`，不执行任何 D1 写入 |

---

### Layer 3：集成测试（模块间交互，需 wrangler dev）

**前提**：运行前需执行 `cd worker && wrangler dev`，Worker 起在 `localhost:8787`。

**Python 管道集成**（`pipeline/tests/integration/test_pipeline.py`）

- 用 5 只测试股票（人工构造 SQLite 数据），跑完整 `main.py` 流程
- 验证结果已通过 HTTP POST 写入 `localhost:8787`
- 查询 `GET localhost:8787/api/screening/latest` → 能拿回刚写入的结果
- 验证 `run_logs` 也写入了一条记录

**Worker API 集成**（`worker/src/tests/integration/api.test.ts`）

- `POST /api/ingest`（带正确 token，含 watch 和 buy 行）→ 数据落 D1，返回 `200`
- `GET /api/screening/latest?combination=watch` → 只返回 watch 行
- `GET /api/screening/latest?combination=buy` → 只返回 buy 行
- `GET /api/stocks/:code` → 返回该股票所有组合的历史记录（含 combination 字段）
- 连续写入同一 `run_date` + 同一 `combination` → 数据追加，不覆盖（幂等写入）

---

### Layer 4：E2E 测试（完整工作流）

**手动验证流程**（每个 Stage 完成后执行）：

```
1. cd worker && wrangler dev          # 启动本地 Worker
2. python pipeline/main.py            # 跑 pipeline，写入 localhost:8787
3. 打开 web/index.html（修改 API URL 指向 localhost:8787）
4. 检查：表格显示今日筛选结果，列数据正确
5. 检查：点击股票代码，跳转东方财富对应页面
6. 检查：历史记录区块显示当日通过数
```

**CI 自动化（Stage 7 完成后）**：

GitHub Actions 在每次 PR 时运行 Layer 1 + Layer 2 测试（不依赖 wrangler dev），Layer 3 集成测试在本地手动运行。

---

## 实施阶段

### Stage 1：基础设施
- [ ] 创建 `openashare/` 项目骨架（pipeline / worker / web / migrations 目录）
- [ ] 创建 CF D1 数据库 + 执行 `migrations/0001_initial_schema.sql`
- [ ] 初始化 CF Worker 项目（`worker/`）+ `wrangler.toml` 配置 D1 绑定
- [ ] **测试**：`wrangler dev` 起来，手动 `curl localhost:8787/api/screening/latest` 返回 `200 {data: []}`
- [ ] 验证：CF Worker 可查询 D1 并返回 JSON

### Stage 2：Python 数据管道
- [ ] 重构 Demo 的 fetcher，新增 `turn`/`pct_chg` 字段存储
- [ ] 本地 SQLite 缓存层（支持 GitHub Actions 断点续传）
- [ ] **测试（Layer 1）**：`test_local_db.py` — 写入/清理/upsert 逻辑
- [ ] **测试（Layer 2）**：`test_fetcher_errors.py` — BaoStock 失败重试 Mock
- [ ] 验证：本地可完整下载并缓存全市场数据（≥ 4000 只股票 × 250 天）

### Stage 3：因子系统 + 组合注册表
- [ ] 实现 `Factor` 抽象基类（含 `id`、`label`、`params`、`compute()` 接口）
- [ ] 实现 `Combination` 类（含 `id`、`label`、`factors` 因子 ID 列表）
- [ ] 迁移 Demo 的 4 个因子 + 新增 RSI、换手率、N日涨幅（共 7 个，当前为占位实现）
- [ ] 在 `registry.py` 注册全部因子 + 定义 `watch` / `buy` 两个组合（占位因子分配）
- [ ] **测试（Layer 1）**：`test_factors.py` — 7 个因子全部覆盖（正常 / 不通过 / 边界）
- [ ] **测试（Layer 1）**：`test_combinations.py` — 组合评估逻辑（全通过 / 部分通过 / 全不通过）
- [ ] 验证：`pytest pipeline/tests/unit/` 全部通过，覆盖率 ≥ 80%

### Stage 4：筛选主逻辑 + Worker 写入
- [ ] 实现 `screener.py`：一次遍历全市场，对每只股票计算所有因子，再按组合评估，每个通过的组合写一行结果
- [ ] 实现 `worker_client.py`（POST 结果到 Worker，URL 由环境变量控制）
- [ ] **测试（Layer 1）**：`test_screener.py` — 股票通过 watch 但不通过 buy / 两个都通过 / 都不通过
- [ ] **测试（Layer 2）**：`test_worker_client_errors.py` — 500/403 错误处理 Mock
- [ ] **测试（Layer 3）**：`test_pipeline.py` — 5 只测试股票完整跑通 + 写入 `wrangler dev`，验证 watch/buy 行都落库
- [ ] 验证：本地 `wrangler dev` 运行，Python 写入 `localhost:8787`，数据落本地 D1

### Stage 5：CF Worker API
- [ ] `POST /api/ingest` — 接收 Python 写入（`Authorization: Bearer <token>` 鉴权）
- [ ] `GET /api/combinations` — 返回所有组合的元数据（id/label/description/factors），用于前端动态渲染
- [ ] `GET /api/screening/latest?combination=<id>` — 指定组合的今日结果（默认返回全部）
- [ ] `GET /api/screening/history` — 历史运行日志（按组合统计每日通过数）
- [ ] `GET /api/stocks/:code` — 单股历史筛选记录（含 combination 字段）
- [ ] 配置 CORS，允许 CF Pages 域名访问
- [ ] **测试（Layer 1）**：`index.test.ts` — 路由匹配、`?combination=` 过滤、鉴权、404/403、`/api/combinations` 返回格式
- [ ] **测试（Layer 2）**：`d1_errors.test.ts` — D1 失败、非法 payload、缺 combination 字段
- [ ] **测试（Layer 3）**：`api.test.ts` — 真实 HTTP 打 `wrangler dev`，验证组合元数据和筛选结果
- [ ] 验证：`npm test` 全部通过，再部署到 CF 验证生产

### Stage 6：静态前端
- [ ] `web/index.html`：**动态 Tab 布局**——通过 `GET /api/combinations` 获取组合列表，动态生成 Tab 页面
- [ ] 每个 Tab 显示：组合名称（label）、组合描述（description）、筛选结果表格
- [ ] 各 Tab 分别调用 `GET /api/screening/latest?combination=<id>` 获取对应组合的结果
- [ ] 每个表格支持按任意因子值排序
- [ ] 点击股票代码跳转东方财富行情页（外链，不自建图表）
- [ ] 历史记录区块（每日各组合通过数，近 30 天）
- [ ] **测试（Layer 4 E2E）**：手动执行测试策略中的 E2E 检查清单，验证动态 Tab 正确展示
- [ ] 验证：完整 E2E 流程可用（Actions 写入 → Worker 读取 → HTML 动态 Tab 正确展示）

### Stage 7：GitHub Actions
- [ ] `daily-screening.yml`（cron 16:30 北京时间）
- [ ] Actions Cache 复用本地 SQLite
- [ ] 配置 Secrets（`WORKER_URL` / `WORKER_WRITE_TOKEN`）
- [ ] **测试**：CI 中自动运行 Layer 1 + Layer 2（`pytest pipeline/tests/unit/ pipeline/tests/mock/` + `npm test --testPathPattern=unit\|mock`）
- [ ] 验证：手动触发 workflow 成功运行，网页显示当日结果

## 验收标准

1. [ ] 每个交易日 16:30 后，网页展示当天筛选结果
2. [ ] 筛选覆盖全市场 4000+ 支股票，运行时间 < 10 分钟
3. [ ] 7 个因子全部有 Layer 1 单元测试，Python 覆盖率 ≥ 80%
4. [ ] Worker Layer 1 + Layer 2 测试全部通过（`npm test`）
5. [ ] Layer 3 集成测试：Python pipeline 写入 `wrangler dev` → GET 接口可读回
6. [ ] Layer 4 E2E：手动验证 6 步检查清单全部通过
7. [ ] 前端可按任意因子值排序筛选结果
8. [ ] 历史记录不可变，因子变更不回溯，旧记录新因子列显示 `null`

## 风险

| 风险 | 概率 | 应对 |
|------|------|------|
| BaoStock 限速/封禁 | 中 | 加入请求间隔 + 重试机制 |
| CF D1 写入量超限（免费 100K/天） | 低 | 每日写入约 500~1000 行，远低于限制 |
| GitHub Actions Cache 过期导致重新全量下载 | 中 | 设置 cache key 策略，最多重下 1 次 |
| CF Worker 免费额度耗尽（10万请求/天） | 低 | 工具仅内部使用，日请求量极低 |
| WORKER_WRITE_TOKEN 泄露导致非法写入 | 低 | Token 仅存 GitHub Secrets，Worker 端校验失败返回 403 |

