# 组合回测系统设计

## 概述

为现有选股系统增加回测能力，验证因子组合在历史数据上的选股效果。复用现有因子系统，自建轻量回测引擎，零新依赖。

## 回测流程

```
1. 加载数据：从 LocalDB 读取全市场 K 线（250 个交易日）
2. 逐日遍历：从第 61 天开始（MA60 预热期）
   对每个交易日 T：
   a. 用 Screener 对所有股票运行因子组合 → 当日选出的股票列表
   b. 新选出的股票进入「等待入场」队列
   c. 检查「等待入场」队列：T+1 起如遇阴线（收盘 < 开盘）→ 买入
   d. 检查「持仓中」股票：收盘跌破 MA10 → 卖出
   e. 记录所有交易
3. 汇总：计算绩效指标，输出报告
```

### 无未来信息泄露

- 因子只看到 T 日及之前的数据：`Factor.compute(df[:T])`
- 买卖在 T+1 及之后执行

## 交易规则

| 项 | 规则 |
|---|---|
| 入场信号 | 组合因子全部通过（AND 逻辑） |
| 入场时机 | 信号后 5 个交易日内遇阴线（收盘 < 开盘），尾盘买入 |
| 入场价格 | 阴线当日收盘价 |
| 出场条件 | 收盘价跌破 MA10 |
| 出场价格 | 跌破当日收盘价 |
| 同一股票 | 持仓中不重复买入 |
| 窗口超时 | 5 天内无阴线则放弃该信号 |

## 仓位管理

- **等权分配：** 同一天多只股票入场时，可用资金等权分配
- **初始资金：** 默认 100 万（可配置）
- **满仓操作：** 有信号就买，不限制同时持仓数量
- **简化处理：** 第一版不考虑手续费、滑点、涨跌停限制

## 净值计算

每个交易日结算：
- 持仓市值 = Σ（各持仓股票当日收盘价 × 持有股数）
- 账户净值 = 现金 + 持仓市值
- 净值曲线 = 逐日净值 / 初始资金

## 绩效指标

| 指标 | 说明 |
|---|---|
| 总收益率 | (期末净值 - 初始资金) / 初始资金 |
| 年化收益率 | 按交易天数折算 |
| 最大回撤 | 净值从峰值到谷底的最大跌幅 |
| 胜率 | 盈利交易笔数 / 总交易笔数 |
| 盈亏比 | 平均盈利金额 / 平均亏损金额 |
| 总交易笔数 | 完整买卖闭环数量 |
| 平均持仓天数 | 所有交易的平均持有时间 |
| 单笔最大盈利/亏损 | 极值表现 |

## 命令行报告

```
========================================
  回测报告：ma60_bounce_uptrend
  回测区间：2025-04-01 ~ 2026-02-21
========================================

【绩效概览】
  总收益率:      +18.5%
  年化收益率:    +21.2%
  最大回撤:      -8.3%
  胜率:          62.5%  (25/40)
  盈亏比:        1.85

【交易统计】
  总交易笔数:    40
  平均持仓天数:  7.2
  单笔最大盈利:  +12.3%  (000858 五粮液)
  单笔最大亏损:  -5.1%   (601318 中国平安)

【交易明细】(最近 10 笔)
  日期        代码    名称      买入价  卖出价  收益率  持仓天数
  2026-02-15  000858  五粮液    156.20  175.40  +12.3%     8
  ...
```

支持导出完整交易记录到 CSV。

## CLI 入口

```bash
# 基本用法
python3 -m pipeline.backtest --combination ma60_bounce_uptrend

# 指定日期范围
python3 -m pipeline.backtest --combination ma60_bounce_uptrend \
    --start 2025-06-01 --end 2026-02-21

# 导出 CSV
python3 -m pipeline.backtest --combination ma60_bounce_uptrend --csv result.csv
```

## 模块结构

```
pipeline/
├── backtest/
│   ├── __init__.py
│   ├── __main__.py        # CLI 入口（python -m pipeline.backtest）
│   ├── engine.py          # 回测引擎：逐日遍历、调度因子、管理状态
│   ├── strategy.py        # 交易策略：阴线入场 + 跌破 MA10 出场
│   ├── portfolio.py       # 组合管理：仓位、净值、现金、持仓记录
│   ├── metrics.py         # 绩效计算
│   └── report.py          # 报告输出：终端格式化 + CSV 导出
└── tests/
    └── unit/
        └── test_backtest.py
```

## 核心类

```python
# engine.py
class BacktestEngine:
    def __init__(self, combination_id, start_date, end_date, initial_capital)
    def run(self) -> BacktestResult

# strategy.py
class EntryExitStrategy:
    def should_enter(self, row) -> bool       # 当日是否阴线
    def should_exit(self, row, ma10) -> bool   # 是否跌破 MA10

# portfolio.py
class Portfolio:
    def buy(self, code, price, date, amount)
    def sell(self, code, price, date)
    def get_nav(self, market_prices) -> float

# metrics.py
def calc_metrics(trades, nav_series) -> dict

# report.py
def print_report(result: BacktestResult)
def export_csv(result: BacktestResult, path)
```

## 数据流

```
LocalDB.get_all_stocks_data()
    → Dict[code, DataFrame]
    → BacktestEngine.run()
        → 逐日循环:
            Screener.screen_single_stock(df[:T])  # 复用现有因子
            EntryExitStrategy.should_enter/exit()
            Portfolio.buy/sell()
        → calc_metrics(trades, nav_series)
    → print_report() / export_csv()
```

## 数据源

直接使用现有本地 SQLite 缓存（250 个交易日，4000+ 股票），不需要额外下载数据。
