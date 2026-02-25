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

    def scan(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(True, index=df.index)


class NeverPassFactor(Factor):
    """测试用因子：永远不通过"""
    def __init__(self):
        super().__init__(id="never_pass", label="Never Pass")

    def compute(self, df: pd.DataFrame) -> FactorResult:
        return FactorResult(passed=False)

    def scan(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(False, index=df.index)


class PassOnDatesFactor(Factor):
    """测试用因子：仅在指定日期通过"""
    def __init__(self, pass_dates):
        super().__init__(id="pass_on_dates", label="Pass On Dates")
        self.pass_dates = set(pass_dates)

    def compute(self, df: pd.DataFrame) -> FactorResult:
        last_date = df.iloc[-1]["date"]
        return FactorResult(passed=last_date in self.pass_dates, value=1.0)

    def scan(self, df: pd.DataFrame) -> pd.Series:
        return df["date"].isin(self.pass_dates)


def make_stock_data(days=100, start_price=10.0, bearish_every=5):
    dates = pd.bdate_range(end="2026-02-20", periods=days)
    np.random.seed(42)

    closes = [start_price]
    opens = [start_price]
    for i in range(1, days):
        change = np.random.uniform(-0.01, 0.015)
        close = closes[-1] * (1 + change)
        if i % bearish_every == 0:
            open_price = close * 1.015
        else:
            open_price = close * 0.985
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

    def _make_engine(self, factor, combination=None, **kwargs):
        if combination is None:
            combination = Combination(
                id="test_combo", label="测试组合",
                factors=[factor.id],
            )
        return BacktestEngine(
            combination=combination,
            factors=[factor],
            initial_capital=1_000_000,
            **kwargs,
        )

    def test_engine_runs_no_error(self):
        engine = self._make_engine(NeverPassFactor())
        stock_data = {"000001": make_stock_data()}
        result = engine.run(stock_data, {"000001": "测试"})
        assert result is not None
        assert result.combination_id == "test_combo"

    def test_no_signal_no_trades(self):
        engine = self._make_engine(NeverPassFactor())
        stock_data = {"000001": make_stock_data()}
        result = engine.run(stock_data, {"000001": "测试"})
        assert len(result.trades) == 0
        assert result.final_nav == pytest.approx(1_000_000)

    def test_always_signal_has_trades(self):
        engine = self._make_engine(AlwaysPassFactor())
        stock_data = {"000001": make_stock_data(days=100, bearish_every=5)}
        result = engine.run(stock_data, {"000001": "测试"})
        assert len(result.trades) > 0

    def test_nav_history_recorded(self):
        engine = self._make_engine(NeverPassFactor())
        stock_data = {"000001": make_stock_data()}
        result = engine.run(stock_data, {"000001": "测试"})
        assert len(result.nav_history) > 0

    def test_specific_signal_date(self):
        df = make_stock_data(days=100, bearish_every=3)
        signal_date = df.iloc[70]["date"]
        factor = PassOnDatesFactor([signal_date])
        engine = self._make_engine(factor)
        result = engine.run({"000001": df}, {"000001": "测试"})
        if result.trades:
            assert result.trades[0].code == "000001"

    def test_date_range_filter(self):
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
        if result.nav_history:
            first_date = result.nav_history[0][0]
            last_date = result.nav_history[-1][0]
            assert first_date >= start
            assert last_date <= end

    def test_metrics_calculated(self):
        engine = self._make_engine(AlwaysPassFactor())
        result = engine.run(
            {"000001": make_stock_data(days=100, bearish_every=5)},
            {"000001": "测试"},
        )
        assert "total_return_pct" in result.metrics
        assert "max_drawdown_pct" in result.metrics
