# CLAUDE.md — A股选股工具

## 项目概述

自动化 A 股选股系统，每个交易日运行，筛选符合技术因子条件的股票。结果展示在 Web 端，并永久存储在云数据库。

- **线上地址：** https://ashare.aigc.it
- **完全免费：** 基于 Cloudflare 免费服务 + GitHub Actions

## 技术栈

| 层 | 技术 |
|---|---|
| 数据管线 | Python 3.11+, pandas, numpy, BaoStock |
| 前端 | 纯 HTML/CSS/JS 单页应用 |
| API | Cloudflare Worker (TypeScript) |
| 数据库 | Cloudflare D1 (SQLite) |
| CI/CD | GitHub Actions（工作日 18:00 BJT） |

## 目录结构

```
openashare/
├── pipeline/              # Python 数据管线（核心业务逻辑）
│   ├── main.py            # 入口文件
│   ├── requirements.txt   # Python 依赖
│   ├── test_factors.py    # 因子测试 CLI
│   ├── data/              # 数据获取与本地缓存（BaoStock + SQLite）
│   ├── factors/           # 技术指标因子
│   │   ├── base.py        # 因子抽象基类
│   │   ├── combination.py # 因子组合逻辑（AND 求值）
│   │   ├── registry.py    # 因子 + 组合注册表
│   │   └── *.py           # 各个具体因子
│   ├── screening/         # 选股引擎
│   ├── backtest/          # 组合回测引擎
│   │   ├── engine.py      # 回测引擎（信号检测 + 交易模拟）
│   │   ├── strategy.py    # 交易策略（阴线入场 + 跌破 MA10 出场）
│   │   ├── portfolio.py   # 仓位管理（买卖、净值）
│   │   ├── metrics.py     # 绩效指标
│   │   └── report.py      # 报告输出 + CSV 导出
│   ├── sync/              # Cloudflare Worker HTTP 客户端
│   └── tests/             # unit / mock / integration 测试
├── worker/                # Cloudflare Worker API + D1
│   ├── wrangler.toml      # Wrangler 配置
│   └── src/index.ts       # API 端点
├── web/                   # 静态前端
│   └── index.html         # 单页应用
├── migrations/            # D1 数据库迁移脚本
├── docs/                  # 文档（部署指南、设计文档等）
└── .github/workflows/     # GitHub Actions 工作流
```

## 常用命令

### Python 管线

```bash
# 安装依赖
cd pipeline && pip install -r requirements.txt

# 运行选股（需设置环境变量）
export WORKER_URL=http://localhost:8787
export WORKER_WRITE_TOKEN=test-token-local
python3 main.py                    # 正常运行
python3 main.py --dry-run          # 仅测试，不上传
python3 main.py --date 2026-02-23  # 指定日期
```

### 测试

```bash
cd pipeline

# 单元测试 + Mock 测试（日常开发必跑）
python -m pytest tests/unit/ tests/mock/ -v --tb=short

# 集成测试
python -m pytest tests/integration/ -v

# 单因子调试
python test_factors.py --factor ma60_bounce_volume --stock 000001
```

### 回测

```bash
# 基本用法（从项目根目录运行）
python -m pipeline.backtest -c ma60_bounce_uptrend --db-path pipeline/data/kline.db

# 指定日期范围
python -m pipeline.backtest -c ma60_bounce_uptrend --start 2025-06-01 --end 2026-02-21

# 导出交易明细到 CSV
python -m pipeline.backtest -c ma60_bounce_uptrend --csv result.csv

# 自定义初始资金和入场窗口
python -m pipeline.backtest -c ma60_bounce_uptrend --capital 500000 --entry-window 3
```

### Worker 开发

```bash
cd worker
npm install
npx wrangler dev --port 8787    # 本地开发
wrangler deploy                 # 部署到生产
```

## 架构要点

### 数据流

```
BaoStock API → BaoStockFetcher → LocalDB (SQLite 缓存)
    → Screener (计算因子) → WorkerClient (POST)
    → Cloudflare Worker D1 (永久存储)
```

### 因子系统

- **基类：** `pipeline/factors/base.py`，抽象方法 `compute(df) -> FactorResult`
- **每个因子独立、无状态**，接收按日期升序排列的 K 线 DataFrame
- **FactorResult** 包含：`passed` (bool)、`value` (float)、`detail` (str)
- **参数可通过环境变量覆盖：** `FACTOR_<ID>_<PARAM>`，如 `FACTOR_MA60_BOUNCE_WITH_VOLUME_MIN_GAIN=8.0`

### 因子组合

- 定义在 `pipeline/factors/registry.py`
- 多因子以 AND 逻辑组合（全部通过才算命中）
- 组合与因子解耦：因子不感知组合的存在

### K 线 DataFrame 格式

列：`date`, `open`, `high`, `low`, `close`, `volume`, `amount`, `turn`, `pct_chg`
排序：按日期升序
Screener 会在因子求值前自动添加 MA 列

## 命名约定

| 类型 | 格式 | 示例 |
|---|---|---|
| 因子 ID | 小写下划线 | `ma60_bounce_volume` |
| 组合 ID | 小写下划线 | `ma60_bounce_uptrend` |
| 股票代码 | 6 位数字字符串 | `000001` |
| 日期 | ISO 8601 | `2026-02-24` |

## Worker API 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/combinations` | 所有组合元数据 |
| GET | `/api/screening/latest` | 最新选股结果 |
| GET | `/api/screening/history` | 最近 30 次运行记录 |
| GET | `/api/screening/by-date?date=YYYY-MM-DD` | 指定日期结果 |
| GET | `/api/stocks/:code` | 单只股票历史记录 |
| POST | `/api/ingest` | 写入选股结果（需 Bearer Token） |

## 添加新因子

1. 在 `pipeline/factors/` 下新建文件，继承 `Factor` 基类
2. 实现 `compute(df) -> FactorResult` 方法
3. 在 `pipeline/factors/registry.py` 中注册因子
4. 在 `pipeline/tests/unit/` 下添加单元测试
5. 如需组合，在 registry 中定义新组合

## 注意事项

- 修改因子逻辑后务必跑 `pytest tests/unit/ tests/mock/`
- 不要手动修改 `pipeline/data/kline.db`，它是自动缓存（保留 250 天）
- Worker 部署需在 Cloudflare 设置 `WORKER_WRITE_TOKEN` Secret
- GitHub Actions 需配置 Secrets：`WORKER_URL`、`WORKER_WRITE_TOKEN`
