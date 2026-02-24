# 组合回测系统 实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为现有 A 股选股系统添加组合回测引擎，验证因子组合在历史数据上的选股效果。

**Architecture:** 在 `pipeline/backtest/` 下新建模块，复用现有因子系统 + 本地 SQLite 数据。分为两阶段：Phase 1 信号检测（逐日对每只股票跑因子），Phase 2 交易模拟（管理仓位、计算净值）。

**Tech Stack:** Python 3.11+, pandas, numpy（均为现有依赖，零新增）

---

### Task 1: 创建模块骨架 + 数据模型

**Files:**
- Create: `pipeline/backtest/__init__.py`
- Create: `pipeline/backtest/models.py`

**Step 1: 创建目录和 `__init__.py`**

```bash
mkdir -p pipeline/backtest
```

```python
# pipeline/backtest/__init__.py
```

**Step 2: 编写 `models.py`**

```python
# pipeline/backtest/models.py
"""回测数据模型"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Tuple, Dict, Optional


@dataclass
class PendingSignal:
    """等待入场的信号"""
    code: str
    name: str
    signal_date: str
    days_waited: int = 0


@dataclass
class Position:
    """持仓"""
    code: str
    name: str
    entry_date: str
    entry_price: float
    shares: int


@dataclass
class Trade:
    """已完成的交易"""
    code: str
    name: str
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    shares: int

    @property
    def pnl(self) -> float:
        return (self.exit_price - self.entry_price) * self.shares

    @property
    def return_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        return (self.exit_price - self.entry_price) / self.entry_price * 100

    @property
    def holding_days(self) -> int:
        d1 = datetime.strptime(self.entry_date, "%Y-%m-%d")
        d2 = datetime.strptime(self.exit_date, "%Y-%m-%d")
        return (d2 - d1).days


@dataclass
class BacktestResult:
    """回测结果"""
    combination_id: str
    combination_label: str
    start_date: str
    end_date: str
    initial_capital: float
    final_nav: float
    trades: List[Trade] = field(default_factory=list)
    nav_history: List[Tuple[str, float]] = field(default_factory=list)
    metrics: Dict[str, float] = field(default_factory=dict)
```

**Step 3: Commit**

```bash
git add pipeline/backtest/__init__.py pipeline/backtest/models.py
git commit -m "feat(backtest): add module skeleton and data models"
```

---

### Task 2: 交易策略 strategy.py（TDD）

**Files:**
- Create: `pipeline/tests/unit/test_backtest_strategy.py`
- Create: `pipeline/backtest/strategy.py`

**Step 1: 编写失败测试**

```python
# pipeline/tests/unit/test_backtest_strategy.py
"""回测策略单元测试"""

import pytest
import pandas as pd
import numpy as np

from pipeline.backtest.strategy import EntryExitStrategy


class TestEntryExitStrategy:

    def test_bearish_candle_true(self):
        """收盘 < 开盘 → 阴线"""
        s = EntryExitStrategy()
        assert s.is_bearish_candle({"open": 10.0, "close": 9.5}) is True

    def test_bearish_candle_false(self):
        """收盘 >= 开盘 → 非阴线"""
        s = EntryExitStrategy()
        assert s.is_bearish_candle({"open": 10.0, "close": 10.5}) is False

    def test_bearish_candle_equal(self):
        """收盘 == 开盘 → 非阴线"""
        s = EntryExitStrategy()
        assert s.is_bearish_candle({"open": 10.0, "close": 10.0}) is False

    def test_should_exit_below_ma10(self):
        """收盘跌破 MA10 → 应卖出"""
        s = EntryExitStrategy()
        assert s.should_exit(9.5, 10.0) is True

    def test_should_not_exit_above_ma10(self):
        """收盘在 MA10 上方 → 不卖"""
        s = EntryExitStrategy()
        assert s.should_exit(10.5, 10.0) is False

    def test_should_not_exit_equal_ma10(self):
        """收盘 == MA10 → 不卖"""
        s = EntryExitStrategy()
        assert s.should_exit(10.0, 10.0) is False
```

**Step 2: 验证测试失败**

Run: `python -m pytest pipeline/tests/unit/test_backtest_strategy.py -v`
Expected: FAIL (ImportError: cannot import 'EntryExitStrategy')

**Step 3: 编写实现**

```python
# pipeline/backtest/strategy.py
"""交易策略：阴线入场 + 跌破 MA10 出场"""

from pipeline.factors.base import calculate_ma
import pandas as pd


class EntryExitStrategy:
    """入场/出场策略"""

    def __init__(self, entry_window: int = 5):
        self.entry_window = entry_window

    def is_bearish_candle(self, row) -> bool:
        """当日是否为阴线（收盘 < 开盘）"""
        return float(row["close"]) < float(row["open"])

    def should_exit(self, close: float, ma10: float) -> bool:
        """收盘是否跌破 MA10"""
        return close < ma10
```

**Step 4: 验证测试通过**

Run: `python -m pytest pipeline/tests/unit/test_backtest_strategy.py -v`
Expected: 6 passed

**Step 5: Commit**

```bash
git add pipeline/backtest/strategy.py pipeline/tests/unit/test_backtest_strategy.py
git commit -m "feat(backtest): add entry/exit strategy with tests"
```

---

### Task 3: 仓位管理 portfolio.py（TDD）

**Files:**
- Create: `pipeline/tests/unit/test_backtest_portfolio.py`
- Create: `pipeline/backtest/portfolio.py`

**Step 1: 编写失败测试**

```python
# pipeline/tests/unit/test_backtest_portfolio.py
"""回测仓位管理单元测试"""

import pytest
from pipeline.backtest.portfolio import Portfolio


class TestPortfolio:

    def test_initial_state(self):
        p = Portfolio(initial_capital=100_000)
        assert p.cash == 100_000
        assert len(p.positions) == 0
        assert len(p.closed_trades) == 0

    def test_buy(self):
        """正常买入"""
        p = Portfolio(initial_capital=100_000)
        p.buy("000001", "平安银行", 10.0, "2026-01-01", 50_000)
        assert "000001" in p.positions
        assert p.positions["000001"].shares == 5000
        assert p.cash == pytest.approx(50_000)

    def test_buy_rounds_to_100(self):
        """买入股数取整到 100 股"""
        p = Portfolio(initial_capital=100_000)
        p.buy("000001", "平安银行", 33.0, "2026-01-01", 50_000)
        # 50000 / 33.0 = 1515.15 → 取整到 100 → 1500 股
        assert p.positions["000001"].shares == 1500
        assert p.cash == pytest.approx(100_000 - 1500 * 33.0)

    def test_buy_insufficient_cash(self):
        """资金不足时不买入"""
        p = Portfolio(initial_capital=1_000)
        p.buy("000001", "平安银行", 100.0, "2026-01-01", 50_000)
        assert "000001" not in p.positions
        assert p.cash == 1_000

    def test_buy_zero_shares(self):
        """金额太小买不到 100 股时不买入"""
        p = Portfolio(initial_capital=100_000)
        p.buy("000001", "平安银行", 600.0, "2026-01-01", 5_000)
        # 5000 / 600 = 8.33 → 取整到 100 → 0 股
        assert "000001" not in p.positions

    def test_sell(self):
        """正常卖出"""
        p = Portfolio(initial_capital=100_000)
        p.buy("000001", "平安银行", 10.0, "2026-01-01", 50_000)
        p.sell("000001", 12.0, "2026-01-10")
        assert "000001" not in p.positions
        assert len(p.closed_trades) == 1
        trade = p.closed_trades[0]
        assert trade.entry_price == 10.0
        assert trade.exit_price == 12.0
        assert trade.return_pct == pytest.approx(20.0)
        assert trade.holding_days == 9
        assert p.cash == pytest.approx(50_000 + 5000 * 12.0)

    def test_sell_nonexistent(self):
        """卖出不存在的持仓不报错"""
        p = Portfolio(initial_capital=100_000)
        p.sell("000001", 12.0, "2026-01-10")
        assert len(p.closed_trades) == 0

    def test_nav(self):
        """净值计算"""
        p = Portfolio(initial_capital=100_000)
        p.buy("000001", "平安银行", 10.0, "2026-01-01", 50_000)
        nav = p.get_nav({"000001": 12.0})
        # 现金 50000 + 持仓 5000 * 12.0 = 110000
        assert nav == pytest.approx(110_000)

    def test_nav_no_positions(self):
        """无持仓时净值等于现金"""
        p = Portfolio(initial_capital=100_000)
        assert p.get_nav({}) == pytest.approx(100_000)

    def test_has_position(self):
        p = Portfolio(initial_capital=100_000)
        assert p.has_position("000001") is False
        p.buy("000001", "平安银行", 10.0, "2026-01-01", 50_000)
        assert p.has_position("000001") is True

    def test_no_duplicate_buy(self):
        """不重复买入同一只股票"""
        p = Portfolio(initial_capital=100_000)
        p.buy("000001", "平安银行", 10.0, "2026-01-01", 50_000)
        p.buy("000001", "平安银行", 11.0, "2026-01-02", 30_000)
        # 第二次买入被忽略
        assert p.positions["000001"].entry_price == 10.0
        assert p.positions["000001"].shares == 5000
```

**Step 2: 验证测试失败**

Run: `python -m pytest pipeline/tests/unit/test_backtest_portfolio.py -v`
Expected: FAIL (ImportError)

**Step 3: 编写实现**

```python
# pipeline/backtest/portfolio.py
"""仓位管理：持仓、买卖、净值"""

from typing import Dict, List
from .models import Position, Trade


class Portfolio:
    """投资组合管理器"""

    def __init__(self, initial_capital: float = 1_000_000):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: Dict[str, Position] = {}
        self.closed_trades: List[Trade] = []

    def buy(self, code: str, name: str, price: float, date: str, amount: float):
        """
        买入股票

        Args:
            code: 股票代码
            name: 股票名称
            price: 买入价格
            date: 买入日期
            amount: 分配资金
        """
        if self.has_position(code):
            return

        shares = int(amount / price / 100) * 100
        if shares <= 0:
            return

        cost = shares * price
        if cost > self.cash:
            return

        self.cash -= cost
        self.positions[code] = Position(
            code=code, name=name,
            entry_date=date, entry_price=price, shares=shares,
        )

    def sell(self, code: str, price: float, date: str):
        """卖出股票"""
        pos = self.positions.pop(code, None)
        if pos is None:
            return

        proceeds = pos.shares * price
        self.cash += proceeds
        self.closed_trades.append(Trade(
            code=pos.code, name=pos.name,
            entry_date=pos.entry_date, entry_price=pos.entry_price,
            exit_date=date, exit_price=price, shares=pos.shares,
        ))

    def get_nav(self, market_prices: Dict[str, float]) -> float:
        """计算当前净值"""
        position_value = sum(
            pos.shares * market_prices.get(pos.code, pos.entry_price)
            for pos in self.positions.values()
        )
        return self.cash + position_value

    def has_position(self, code: str) -> bool:
        return code in self.positions
```

**Step 4: 验证测试通过**

Run: `python -m pytest pipeline/tests/unit/test_backtest_portfolio.py -v`
Expected: 11 passed

**Step 5: Commit**

```bash
git add pipeline/backtest/portfolio.py pipeline/tests/unit/test_backtest_portfolio.py
git commit -m "feat(backtest): add portfolio management with tests"
```

---

### Task 4: 绩效指标 metrics.py（TDD）

**Files:**
- Create: `pipeline/tests/unit/test_backtest_metrics.py`
- Create: `pipeline/backtest/metrics.py`

**Step 1: 编写失败测试**

```python
# pipeline/tests/unit/test_backtest_metrics.py
"""回测绩效指标单元测试"""

import pytest
from pipeline.backtest.models import Trade
from pipeline.backtest.metrics import calc_metrics


class TestCalcMetrics:

    def test_total_return(self):
        nav_history = [("2026-01-01", 100_000), ("2026-01-10", 102_000)]
        m = calc_metrics([], nav_history, 100_000)
        assert m["total_return_pct"] == pytest.approx(2.0)

    def test_annualized_return(self):
        """250 天翻倍 → 年化 100%"""
        nav_history = [(f"day{i}", 100_000 + i * 400) for i in range(250)]
        # 末尾净值: 100000 + 249*400 = 199600
        m = calc_metrics([], nav_history, 100_000)
        assert m["annualized_return_pct"] == pytest.approx(99.6, abs=0.5)

    def test_max_drawdown(self):
        nav_history = [
            ("d1", 100_000),
            ("d2", 110_000),   # peak
            ("d3", 99_000),    # trough: (110000-99000)/110000 = 10%
            ("d4", 105_000),
        ]
        m = calc_metrics([], nav_history, 100_000)
        assert m["max_drawdown_pct"] == pytest.approx(10.0)

    def test_max_drawdown_no_drawdown(self):
        """持续上涨 → 回撤 0"""
        nav_history = [("d1", 100_000), ("d2", 110_000), ("d3", 120_000)]
        m = calc_metrics([], nav_history, 100_000)
        assert m["max_drawdown_pct"] == pytest.approx(0.0)

    def test_win_rate(self):
        trades = [
            Trade("A", "A", "2026-01-01", 10.0, "2026-01-10", 12.0, 100),  # win
            Trade("B", "B", "2026-01-01", 10.0, "2026-01-10", 8.0, 100),   # loss
            Trade("C", "C", "2026-01-01", 10.0, "2026-01-10", 11.0, 100),  # win
        ]
        nav_history = [("d1", 100_000)]
        m = calc_metrics(trades, nav_history, 100_000)
        assert m["win_rate_pct"] == pytest.approx(66.67, abs=0.01)
        assert m["total_trades"] == 3

    def test_profit_loss_ratio(self):
        trades = [
            Trade("A", "A", "2026-01-01", 10.0, "2026-01-10", 12.0, 100),  # +20%
            Trade("B", "B", "2026-01-01", 10.0, "2026-01-10", 8.0, 100),   # -20%
        ]
        nav_history = [("d1", 100_000)]
        m = calc_metrics(trades, nav_history, 100_000)
        assert m["profit_loss_ratio"] == pytest.approx(1.0)

    def test_avg_holding_days(self):
        trades = [
            Trade("A", "A", "2026-01-01", 10.0, "2026-01-11", 12.0, 100),  # 10 days
            Trade("B", "B", "2026-01-01", 10.0, "2026-01-06", 11.0, 100),  # 5 days
        ]
        nav_history = [("d1", 100_000)]
        m = calc_metrics(trades, nav_history, 100_000)
        assert m["avg_holding_days"] == pytest.approx(7.5)

    def test_no_trades(self):
        nav_history = [("d1", 100_000)]
        m = calc_metrics([], nav_history, 100_000)
        assert m["total_trades"] == 0
        assert "win_rate_pct" not in m

    def test_empty_nav_history(self):
        m = calc_metrics([], [], 100_000)
        assert m == {}
```

**Step 2: 验证测试失败**

Run: `python -m pytest pipeline/tests/unit/test_backtest_metrics.py -v`
Expected: FAIL (ImportError)

**Step 3: 编写实现**

```python
# pipeline/backtest/metrics.py
"""绩效指标计算"""

from typing import List, Tuple, Dict
from .models import Trade


def calc_metrics(
    trades: List[Trade],
    nav_history: List[Tuple[str, float]],
    initial_capital: float,
) -> Dict[str, float]:
    """
    计算回测绩效指标

    Args:
        trades: 已完成交易列表
        nav_history: 净值历史 [(date, nav), ...]
        initial_capital: 初始资金

    Returns:
        绩效指标字典
    """
    if not nav_history:
        return {}

    metrics: Dict[str, float] = {}

    # 总收益率
    final_nav = nav_history[-1][1]
    total_return = (final_nav - initial_capital) / initial_capital * 100
    metrics["total_return_pct"] = round(total_return, 2)

    # 年化收益率
    trading_days = len(nav_history)
    if trading_days > 1:
        annual_factor = 250 / trading_days
        annualized = ((final_nav / initial_capital) ** annual_factor - 1) * 100
        metrics["annualized_return_pct"] = round(annualized, 2)

    # 最大回撤
    peak = initial_capital
    max_dd = 0.0
    for _, nav in nav_history:
        if nav > peak:
            peak = nav
        dd = (peak - nav) / peak * 100
        if dd > max_dd:
            max_dd = dd
    metrics["max_drawdown_pct"] = round(max_dd, 2)

    # 交易统计
    metrics["total_trades"] = len(trades)

    if trades:
        winners = [t for t in trades if t.return_pct > 0]
        losers = [t for t in trades if t.return_pct <= 0]

        metrics["win_rate_pct"] = round(len(winners) / len(trades) * 100, 2)

        avg_win = (sum(t.return_pct for t in winners) / len(winners)) if winners else 0
        avg_loss = (abs(sum(t.return_pct for t in losers) / len(losers))) if losers else 0
        metrics["profit_loss_ratio"] = round(avg_win / avg_loss, 2) if avg_loss > 0 else float("inf")

        metrics["avg_holding_days"] = round(
            sum(t.holding_days for t in trades) / len(trades), 1
        )
        metrics["max_win_pct"] = round(max(t.return_pct for t in trades), 2)
        metrics["max_loss_pct"] = round(min(t.return_pct for t in trades), 2)

    return metrics
```

**Step 4: 验证测试通过**

Run: `python -m pytest pipeline/tests/unit/test_backtest_metrics.py -v`
Expected: 9 passed

**Step 5: Commit**

```bash
git add pipeline/backtest/metrics.py pipeline/tests/unit/test_backtest_metrics.py
git commit -m "feat(backtest): add performance metrics with tests"
```

---

### Task 5: 回测引擎 engine.py（TDD）

这是最核心也最复杂的部分。引擎分两个阶段：

- **Phase 1 - 信号检测：** 对每只股票逐日运行因子组合，找出所有信号日
- **Phase 2 - 交易模拟：** 按时间顺序遍历，管理入场等待、买卖、净值

**Files:**
- Create: `pipeline/tests/unit/test_backtest_engine.py`
- Create: `pipeline/backtest/engine.py`

**Step 1: 编写失败测试**

```python
# pipeline/tests/unit/test_backtest_engine.py
"""回测引擎单元测试"""

import pytest
import pandas as pd
import numpy as np

from pipeline.factors.base import Factor, FactorResult
from pipeline.factors.combination import Combination
from pipeline.backtest.engine import BacktestEngine


class AlwaysPassFactor(Factor):
    """测试用因子：总是通过"""
    def __init__(self):
        super().__init__(id="always_pass", label="Always Pass")

    def compute(self, df: pd.DataFrame) -> FactorResult:
        return FactorResult(passed=True, value=1.0)


class NeverPassFactor(Factor):
    """测试用因子：永远不通过"""
    def __init__(self):
        super().__init__(id="never_pass", label="Never Pass")

    def compute(self, df: pd.DataFrame) -> FactorResult:
        return FactorResult(passed=False)


class PassOnDatesFactor(Factor):
    """测试用因子：仅在指定日期通过"""
    def __init__(self, pass_dates):
        super().__init__(id="pass_on_dates", label="Pass On Dates")
        self.pass_dates = set(pass_dates)

    def compute(self, df: pd.DataFrame) -> FactorResult:
        last_date = df.iloc[-1]["date"]
        return FactorResult(passed=last_date in self.pass_dates, value=1.0)


def make_stock_data(days=100, start_price=10.0, bearish_every=5):
    """
    生成测试用股票数据

    Args:
        days: 天数
        start_price: 起始价格
        bearish_every: 每隔 N 天制造一根阴线
    """
    dates = pd.bdate_range(end="2026-02-20", periods=days)
    np.random.seed(42)

    closes = [start_price]
    opens = [start_price]
    for i in range(1, days):
        change = np.random.uniform(-0.01, 0.015)
        close = closes[-1] * (1 + change)
        if i % bearish_every == 0:
            open_price = close * 1.015  # 阴线
        else:
            open_price = close * 0.985  # 阳线
        closes.append(close)
        opens.append(open_price)

    df = pd.DataFrame({
        "date": dates.strftime("%Y-%m-%d"),
        "open": opens,
        "close": closes,
        "high": [max(o, c) * 1.01 for o, c in zip(opens, closes)],
        "low": [min(o, c) * 0.99 for o, c in zip(opens, closes)],
        "volume": [1_000_000] * days,
        "amount": [10_000_000] * days,
        "turn": [2.0] * days,
        "pct_chg": [0.0] + [
            (closes[i] - closes[i - 1]) / closes[i - 1] * 100
            for i in range(1, days)
        ],
    })
    return df


class TestBacktestEngine:

    def _make_engine(self, factor, combination=None):
        """创建测试用引擎"""
        if combination is None:
            combination = Combination(
                id="test_combo", label="测试组合",
                factors=[factor.id],
            )
        return BacktestEngine(
            combination=combination,
            factors=[factor],
            initial_capital=1_000_000,
        )

    def test_engine_runs_no_error(self):
        """引擎运行不报错"""
        engine = self._make_engine(NeverPassFactor())
        stock_data = {"000001": make_stock_data()}
        result = engine.run(stock_data, {"000001": "测试"})
        assert result is not None
        assert result.combination_id == "test_combo"

    def test_no_signal_no_trades(self):
        """无信号时无交易"""
        engine = self._make_engine(NeverPassFactor())
        stock_data = {"000001": make_stock_data()}
        result = engine.run(stock_data, {"000001": "测试"})
        assert len(result.trades) == 0
        assert result.final_nav == pytest.approx(1_000_000)

    def test_always_signal_has_trades(self):
        """持续有信号时应产生交易"""
        engine = self._make_engine(AlwaysPassFactor())
        stock_data = {"000001": make_stock_data(days=100, bearish_every=5)}
        result = engine.run(stock_data, {"000001": "测试"})
        assert len(result.trades) > 0

    def test_nav_history_recorded(self):
        """净值历史被记录"""
        engine = self._make_engine(NeverPassFactor())
        stock_data = {"000001": make_stock_data()}
        result = engine.run(stock_data, {"000001": "测试"})
        assert len(result.nav_history) > 0

    def test_specific_signal_date(self):
        """在特定日期产生信号"""
        df = make_stock_data(days=100, bearish_every=3)
        signal_date = df.iloc[70]["date"]  # 第 70 天产生信号
        factor = PassOnDatesFactor([signal_date])
        engine = self._make_engine(factor)
        result = engine.run({"000001": df}, {"000001": "测试"})
        # 信号后遇阴线应有交易
        if result.trades:
            assert result.trades[0].code == "000001"

    def test_date_range_filter(self):
        """日期范围过滤"""
        df = make_stock_data(days=100)
        start = df.iloc[70]["date"]
        end = df.iloc[90]["date"]
        engine = BacktestEngine(
            combination=Combination(id="t", label="t", factors=["always_pass"]),
            factors=[AlwaysPassFactor()],
            start_date=start,
            end_date=end,
        )
        result = engine.run({"000001": df}, {"000001": "测试"})
        # 净值历史应限定在日期范围内
        if result.nav_history:
            first_date = result.nav_history[0][0]
            last_date = result.nav_history[-1][0]
            assert first_date >= start
            assert last_date <= end

    def test_metrics_calculated(self):
        """回测结果包含绩效指标"""
        engine = self._make_engine(AlwaysPassFactor())
        result = engine.run(
            {"000001": make_stock_data(days=100, bearish_every=5)},
            {"000001": "测试"},
        )
        assert "total_return_pct" in result.metrics
        assert "max_drawdown_pct" in result.metrics
```

**Step 2: 验证测试失败**

Run: `python -m pytest pipeline/tests/unit/test_backtest_engine.py -v`
Expected: FAIL (ImportError)

**Step 3: 编写实现**

```python
# pipeline/backtest/engine.py
"""
回测引擎

两阶段架构：
- Phase 1: 信号检测（逐日对每只股票运行因子组合）
- Phase 2: 交易模拟（管理入场等待、买卖、净值）
"""

import logging
from typing import Dict, List, Tuple, Optional
import pandas as pd

from pipeline.factors.base import Factor, FactorResult, calculate_ma
from pipeline.factors.combination import Combination
from pipeline.factors.registry import get_combination, get_factor
from pipeline.backtest.models import (
    PendingSignal, BacktestResult, Trade,
)
from pipeline.backtest.strategy import EntryExitStrategy
from pipeline.backtest.portfolio import Portfolio
from pipeline.backtest.metrics import calc_metrics

logger = logging.getLogger(__name__)


class BacktestEngine:
    """回测引擎"""

    # 因子预热期（MA60 需要 60 天数据）
    WARMUP_DAYS = 61

    def __init__(
        self,
        combination_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        initial_capital: float = 1_000_000,
        entry_window: int = 5,
        combination: Optional[Combination] = None,
        factors: Optional[List[Factor]] = None,
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.entry_window = entry_window

        if combination is not None and factors is not None:
            self.combination = combination
            self.factors = factors
            self.combination_id = combination.id
        else:
            self.combination_id = combination_id
            self.combination = get_combination(combination_id)
            self.factors = [get_factor(fid) for fid in self.combination.factors]

        self.strategy = EntryExitStrategy(entry_window=entry_window)

    def run(
        self,
        stock_data: Dict[str, pd.DataFrame],
        stock_names: Optional[Dict[str, str]] = None,
        progress_callback=None,
    ) -> BacktestResult:
        """
        运行回测

        Args:
            stock_data: {股票代码: K线 DataFrame}
            stock_names: {股票代码: 名称}
            progress_callback: 进度回调 (current, total, phase)

        Returns:
            BacktestResult
        """
        stock_names = stock_names or {}

        # Phase 1: 信号检测
        logger.info("Phase 1: 检测信号...")
        signals = self._detect_all_signals(stock_data, stock_names, progress_callback)

        # Phase 2: 准备数据
        all_dates = self._get_trading_dates(stock_data)
        ma10_lookup = self._precompute_ma10(stock_data)
        price_lookup = self._build_price_lookup(stock_data)

        # Phase 3: 交易模拟
        logger.info("Phase 2: 模拟交易...")
        portfolio = Portfolio(self.initial_capital)
        pending: Dict[str, PendingSignal] = {}
        nav_history: List[Tuple[str, float]] = []

        for date in all_dates:
            # (a) 检查出场
            codes_to_sell = []
            for code in list(portfolio.positions.keys()):
                if code not in price_lookup or date not in price_lookup[code]:
                    continue
                close = price_lookup[code][date]["close"]
                ma10 = ma10_lookup.get(code, {}).get(date)
                if ma10 is not None and self.strategy.should_exit(close, ma10):
                    codes_to_sell.append((code, close))

            for code, price in codes_to_sell:
                portfolio.sell(code, price, date)

            # (b) 检查入场
            entries_today = []
            expired = []
            for code, sig in pending.items():
                sig.days_waited += 1
                if code in price_lookup and date in price_lookup[code]:
                    row = price_lookup[code][date]
                    if self.strategy.is_bearish_candle(row):
                        entries_today.append((code, sig.name, row["close"]))
                        continue
                if sig.days_waited > self.entry_window:
                    expired.append(code)

            for code in expired:
                pending.pop(code, None)

            if entries_today:
                per_stock = portfolio.cash / len(entries_today)
                for code, name, price in entries_today:
                    pending.pop(code, None)
                    portfolio.buy(code, name, price, date, per_stock)

            # (c) 新信号进入等待队列
            if date in signals:
                for code, name in signals[date]:
                    if not portfolio.has_position(code) and code not in pending:
                        pending[code] = PendingSignal(
                            code=code, name=name, signal_date=date,
                        )

            # (d) 记录净值
            market_prices = {}
            for code in portfolio.positions:
                if code in price_lookup and date in price_lookup[code]:
                    market_prices[code] = price_lookup[code][date]["close"]
            nav = portfolio.get_nav(market_prices)
            nav_history.append((date, nav))

        # 回测结束：强制平仓
        if all_dates:
            last_date = all_dates[-1]
            for code in list(portfolio.positions.keys()):
                if code in price_lookup and last_date in price_lookup[code]:
                    portfolio.sell(
                        code,
                        price_lookup[code][last_date]["close"],
                        last_date,
                    )

        # 计算指标
        metrics = calc_metrics(
            portfolio.closed_trades, nav_history, self.initial_capital,
        )

        return BacktestResult(
            combination_id=self.combination_id,
            combination_label=self.combination.label,
            start_date=self.start_date or (all_dates[0] if all_dates else ""),
            end_date=self.end_date or (all_dates[-1] if all_dates else ""),
            initial_capital=self.initial_capital,
            final_nav=nav_history[-1][1] if nav_history else self.initial_capital,
            trades=portfolio.closed_trades,
            nav_history=nav_history,
            metrics=metrics,
        )

    def _detect_all_signals(
        self,
        stock_data: Dict[str, pd.DataFrame],
        stock_names: Dict[str, str],
        progress_callback=None,
    ) -> Dict[str, List[Tuple[str, str]]]:
        """
        Phase 1: 检测所有信号

        Returns:
            {日期: [(股票代码, 名称), ...]}
        """
        signals: Dict[str, List[Tuple[str, str]]] = {}
        total = len(stock_data)

        for i, (code, df) in enumerate(stock_data.items()):
            if progress_callback:
                progress_callback(i + 1, total, "signal")

            df = df.sort_values("date").reset_index(drop=True)
            if len(df) < self.WARMUP_DAYS:
                continue

            name = stock_names.get(code, "")

            for T in range(self.WARMUP_DAYS - 1, len(df)):
                date = df.iloc[T]["date"]

                if self.start_date and date < self.start_date:
                    continue
                if self.end_date and date > self.end_date:
                    continue

                # 对截止到 T 的数据计算因子
                slice_df = df.iloc[: T + 1]
                factor_results: Dict[str, FactorResult] = {}
                for factor in self.factors:
                    factor_results[factor.id] = factor.compute(slice_df)

                if self.combination.evaluate(factor_results):
                    signals.setdefault(date, []).append((code, name))

        return signals

    def _get_trading_dates(
        self, stock_data: Dict[str, pd.DataFrame],
    ) -> List[str]:
        """获取回测区间内所有交易日（排序）"""
        all_dates = set()
        for df in stock_data.values():
            all_dates.update(df["date"].tolist())

        dates = sorted(all_dates)

        # 过滤日期范围
        if self.start_date:
            dates = [d for d in dates if d >= self.start_date]
        if self.end_date:
            dates = [d for d in dates if d <= self.end_date]

        return dates

    def _precompute_ma10(
        self, stock_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, Dict[str, float]]:
        """预计算所有股票的 MA10（用于出场判断）"""
        ma10_lookup: Dict[str, Dict[str, float]] = {}
        for code, df in stock_data.items():
            df = df.sort_values("date").reset_index(drop=True)
            ma10 = calculate_ma(df, 10)
            ma10_lookup[code] = {}
            for idx, val in ma10.items():
                if pd.notna(val):
                    ma10_lookup[code][df.iloc[idx]["date"]] = val
        return ma10_lookup

    def _build_price_lookup(
        self, stock_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, Dict[str, dict]]:
        """构建价格查找表 {code: {date: {open, close, ...}}}"""
        lookup: Dict[str, Dict[str, dict]] = {}
        for code, df in stock_data.items():
            lookup[code] = {}
            for _, row in df.iterrows():
                lookup[code][row["date"]] = {
                    "open": float(row["open"]),
                    "close": float(row["close"]),
                }
        return lookup
```

**Step 4: 验证测试通过**

Run: `python -m pytest pipeline/tests/unit/test_backtest_engine.py -v`
Expected: 7 passed

**Step 5: Commit**

```bash
git add pipeline/backtest/engine.py pipeline/tests/unit/test_backtest_engine.py
git commit -m "feat(backtest): add backtest engine with signal detection and trade simulation"
```

---

### Task 6: 报告输出 report.py

**Files:**
- Create: `pipeline/backtest/report.py`

**Step 1: 编写实现**

```python
# pipeline/backtest/report.py
"""回测报告：终端格式化 + CSV 导出"""

import csv
from typing import Optional
from .models import BacktestResult


def print_report(result: BacktestResult):
    """打印终端回测报告"""
    m = result.metrics

    print()
    print("=" * 50)
    print(f"  回测报告：{result.combination_label}")
    print(f"  组合 ID：{result.combination_id}")
    print(f"  回测区间：{result.start_date} ~ {result.end_date}")
    print(f"  初始资金：{result.initial_capital:,.0f}")
    print("=" * 50)

    print()
    print("【绩效概览】")
    total_ret = m.get("total_return_pct", 0)
    sign = "+" if total_ret >= 0 else ""
    print(f"  总收益率:      {sign}{total_ret:.2f}%")

    if "annualized_return_pct" in m:
        ann_ret = m["annualized_return_pct"]
        sign = "+" if ann_ret >= 0 else ""
        print(f"  年化收益率:    {sign}{ann_ret:.2f}%")

    print(f"  最大回撤:      -{m.get('max_drawdown_pct', 0):.2f}%")

    total_trades = m.get("total_trades", 0)
    if total_trades > 0:
        win_rate = m.get("win_rate_pct", 0)
        winners = round(total_trades * win_rate / 100)
        print(f"  胜率:          {win_rate:.1f}%  ({winners}/{total_trades})")
        print(f"  盈亏比:        {m.get('profit_loss_ratio', 0):.2f}")

    print()
    print("【交易统计】")
    print(f"  总交易笔数:    {total_trades}")

    if total_trades > 0:
        print(f"  平均持仓天数:  {m.get('avg_holding_days', 0):.1f}")

        # 找最大盈亏交易
        best = max(result.trades, key=lambda t: t.return_pct)
        worst = min(result.trades, key=lambda t: t.return_pct)
        print(f"  单笔最大盈利:  +{best.return_pct:.2f}%  ({best.code} {best.name})")
        print(f"  单笔最大亏损:  {worst.return_pct:.2f}%  ({worst.code} {worst.name})")

    # 交易明细（最近 10 笔）
    if result.trades:
        print()
        recent = result.trades[-10:]
        print(f"【交易明细】(最近 {len(recent)} 笔)")
        print(f"  {'买入日':>10}  {'代码':>6}  {'名称':<6}  {'买入价':>7}  {'卖出价':>7}  {'收益率':>7}  {'天数':>4}")
        for t in recent:
            sign = "+" if t.return_pct >= 0 else ""
            print(
                f"  {t.entry_date:>10}  {t.code:>6}  {t.name:<6}  "
                f"{t.entry_price:>7.2f}  {t.exit_price:>7.2f}  "
                f"{sign}{t.return_pct:>6.2f}%  {t.holding_days:>4}"
            )

    print()
    print(f"  期末净值: {result.final_nav:,.2f}")
    print("=" * 50)
    print()


def export_csv(result: BacktestResult, path: str):
    """导出交易明细到 CSV"""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "代码", "名称", "买入日期", "买入价格",
            "卖出日期", "卖出价格", "股数",
            "盈亏金额", "收益率(%)", "持仓天数",
        ])
        for t in result.trades:
            writer.writerow([
                t.code, t.name, t.entry_date, f"{t.entry_price:.2f}",
                t.exit_date, f"{t.exit_price:.2f}", t.shares,
                f"{t.pnl:.2f}", f"{t.return_pct:.2f}", t.holding_days,
            ])
    print(f"交易明细已导出: {path} ({len(result.trades)} 笔)")
```

**Step 2: Commit**

```bash
git add pipeline/backtest/report.py
git commit -m "feat(backtest): add report formatting and CSV export"
```

---

### Task 7: CLI 入口 __main__.py

**Files:**
- Create: `pipeline/backtest/__main__.py`

**Step 1: 编写实现**

```python
# pipeline/backtest/__main__.py
"""
回测 CLI 入口

用法:
    python -m pipeline.backtest --combination ma60_bounce_uptrend
    python -m pipeline.backtest --combination ma60_bounce_uptrend --start 2025-06-01 --end 2026-02-21
    python -m pipeline.backtest --combination ma60_bounce_uptrend --csv result.csv
"""

import argparse
import logging
import sys
import os
import time

from tqdm import tqdm

# 确保 pipeline 的父目录在路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pipeline.data.local_db import LocalDB
from pipeline.backtest.engine import BacktestEngine
from pipeline.backtest.report import print_report, export_csv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="A股组合回测")
    parser.add_argument(
        "--combination", "-c", required=True,
        help="组合 ID，如 ma60_bounce_uptrend",
    )
    parser.add_argument("--start", type=str, help="回测起始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="回测结束日期 (YYYY-MM-DD)")
    parser.add_argument(
        "--capital", type=float, default=1_000_000,
        help="初始资金（默认 1000000）",
    )
    parser.add_argument(
        "--entry-window", type=int, default=5,
        help="等待阴线入场的最大天数（默认 5）",
    )
    parser.add_argument("--csv", type=str, help="导出交易明细到 CSV 文件")
    parser.add_argument(
        "--db-path", type=str, default="data/kline.db",
        help="本地数据库路径",
    )
    args = parser.parse_args()

    start_time = time.time()

    # 加载数据
    logger.info(f"加载本地数据库: {args.db_path}")
    db = LocalDB(args.db_path)
    info = db.get_database_info()
    logger.info(f"数据库: {info.get('stock_count', 0)} 只股票, "
                f"{info.get('record_count', 0)} 条记录, "
                f"最新日期: {info.get('latest_date', 'N/A')}")

    logger.info("加载全市场 K 线数据...")
    all_data = db.get_all_stocks_data()
    stock_data = {
        code: group.reset_index(drop=True)
        for code, group in all_data.groupby("code")
    }
    logger.info(f"共 {len(stock_data)} 只股票")

    # 创建引擎
    logger.info(f"初始化回测引擎: 组合={args.combination}, 资金={args.capital:,.0f}")
    engine = BacktestEngine(
        combination_id=args.combination,
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital,
        entry_window=args.entry_window,
    )

    # 进度条
    pbar = None

    def progress_callback(current, total, phase):
        nonlocal pbar
        if pbar is None:
            pbar = tqdm(total=total, desc="检测信号")
        pbar.update(1)

    # 运行回测
    result = engine.run(stock_data, progress_callback=progress_callback)

    if pbar:
        pbar.close()

    duration = time.time() - start_time
    logger.info(f"回测完成，耗时 {duration:.1f} 秒")

    # 输出报告
    print_report(result)

    # 导出 CSV
    if args.csv:
        export_csv(result, args.csv)


if __name__ == "__main__":
    main()
```

**Step 2: 手动测试 CLI help**

Run: `cd /Users/jiangzhongbo/workspace/product/A-Share-Quant/openashare && python -m pipeline.backtest --help`
Expected: 显示参数帮助信息

**Step 3: Commit**

```bash
git add pipeline/backtest/__main__.py
git commit -m "feat(backtest): add CLI entry point"
```

---

### Task 8: 运行全部测试 + 集成验证

**Step 1: 运行所有回测单元测试**

```bash
cd /Users/jiangzhongbo/workspace/product/A-Share-Quant/openashare
python -m pytest pipeline/tests/unit/test_backtest_strategy.py pipeline/tests/unit/test_backtest_portfolio.py pipeline/tests/unit/test_backtest_metrics.py pipeline/tests/unit/test_backtest_engine.py -v
```

Expected: 全部通过

**Step 2: 运行现有测试确认无破坏**

```bash
python -m pytest pipeline/tests/unit/ pipeline/tests/mock/ -v --tb=short
```

Expected: 全部通过（现有测试不受影响）

**Step 3: 用真实数据运行回测（如果本地有 kline.db）**

```bash
python -m pipeline.backtest --combination ma60_bounce_uptrend
```

Expected: 输出回测报告，包含绩效指标和交易明细

**Step 4: 最终 Commit**

```bash
git add -A
git commit -m "feat(backtest): complete combination backtesting system"
```
