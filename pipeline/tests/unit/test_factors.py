"""
Layer 1 单元测试 - 因子
测试 7 个因子的 compute() 方法
"""

import pytest
import pandas as pd
import numpy as np

from pipeline.factors.ma60_monotonic import MA60MonotonicFactor
from pipeline.factors.ma20_consolidation import MA20ConsolidationFactor
from pipeline.factors.ma_distance import MADistanceFactor
from pipeline.factors.macd_golden_cross import MACDGoldenCrossFactor
from pipeline.factors.rsi import RSIFactor
from pipeline.factors.turnover import TurnoverFactor
from pipeline.factors.n_day_return import NDayReturnFactor


def generate_monotonic_data(days: int = 100, start_price: float = 10.0, daily_growth: float = 0.001):
    """生成单调上涨的数据"""
    dates = pd.date_range(end="2026-02-23", periods=days).strftime("%Y-%m-%d").tolist()
    prices = [start_price * (1 + daily_growth) ** i for i in range(days)]
    return pd.DataFrame({
        "date": dates,
        "close": prices,
        "turn": [2.0] * days,
        "pct_chg": [daily_growth * 100] * days,
    })


def generate_volatile_data(days: int = 100, start_price: float = 10.0):
    """生成波动数据"""
    np.random.seed(42)
    dates = pd.date_range(end="2026-02-23", periods=days).strftime("%Y-%m-%d").tolist()
    prices = [start_price]
    for _ in range(days - 1):
        change = np.random.uniform(-0.02, 0.02)
        prices.append(prices[-1] * (1 + change))
    return pd.DataFrame({
        "date": dates,
        "close": prices,
        "turn": np.random.uniform(0.5, 5.0, days).tolist(),
        "pct_chg": [0.0] + [((prices[i] - prices[i-1]) / prices[i-1] * 100) for i in range(1, days)],
    })


class TestMA60MonotonicFactor:
    """测试 MA60 单调不减因子"""

    def test_insufficient_data(self):
        """数据不足应不通过"""
        df = generate_monotonic_data(days=50)
        factor = MA60MonotonicFactor()
        result = factor.compute(df)
        assert result.passed == False
        assert "数据不足" in result.detail

    def test_monotonic_pass(self):
        """单调上涨应通过"""
        df = generate_monotonic_data(days=100, daily_growth=0.002)
        factor = MA60MonotonicFactor()
        result = factor.compute(df)
        assert result.passed == True
        assert result.value > 0

    def test_not_monotonic_fail(self):
        """波动数据应不通过"""
        df = generate_volatile_data(days=100)
        factor = MA60MonotonicFactor()
        result = factor.compute(df)
        assert result.passed == False


class TestMA20ConsolidationFactor:
    """测试 MA20 整盘因子"""

    def test_insufficient_data(self):
        """数据不足应不通过"""
        df = generate_monotonic_data(days=30)
        factor = MA20ConsolidationFactor()
        result = factor.compute(df)
        assert result.passed == False

    def test_consolidation_pass(self):
        """整盘状态应通过"""
        # 生成平稳数据
        df = generate_monotonic_data(days=60, daily_growth=0.0001)
        factor = MA20ConsolidationFactor()
        result = factor.compute(df)
        assert result.passed == True

    def test_rising_fail(self):
        """快速上涨应不通过"""
        df = generate_monotonic_data(days=60, daily_growth=0.01)
        factor = MA20ConsolidationFactor()
        result = factor.compute(df)
        assert result.passed == False


class TestMADistanceFactor:
    """测试 MA 距离因子"""

    def test_insufficient_data(self):
        """数据不足应不通过"""
        df = generate_monotonic_data(days=50)
        factor = MADistanceFactor()
        result = factor.compute(df)
        assert result.passed == False

    def test_close_distance_pass(self):
        """MA 接近应通过"""
        # 稳定上涨，MA20 和 MA60 会比较接近
        df = generate_monotonic_data(days=100, daily_growth=0.001)
        factor = MADistanceFactor()
        result = factor.compute(df)
        assert result.passed == True


class TestMACDGoldenCrossFactor:
    """测试 MACD 金叉因子"""

    def test_insufficient_data(self):
        """数据不足应不通过"""
        df = generate_monotonic_data(days=30)
        factor = MACDGoldenCrossFactor()
        result = factor.compute(df)
        assert result.passed == False

    def test_no_golden_cross(self):
        """无金叉应不通过"""
        # 单调上涨不会产生金叉
        df = generate_monotonic_data(days=100)
        factor = MACDGoldenCrossFactor()
        result = factor.compute(df)
        assert result.passed == False


class TestRSIFactor:
    """测试 RSI 因子"""

    def test_insufficient_data(self):
        """数据不足应不通过"""
        df = generate_monotonic_data(days=10)
        factor = RSIFactor()
        result = factor.compute(df)
        assert result.passed == False

    def test_normal_rsi(self):
        """正常 RSI 无超卖反弹应不通过"""
        df = generate_monotonic_data(days=50)
        factor = RSIFactor()
        result = factor.compute(df)
        # 单调上涨不会触发超卖反弹
        assert result.passed == False


class TestTurnoverFactor:
    """测试换手率因子"""

    def test_missing_turn_column(self):
        """无换手率列应不通过"""
        df = pd.DataFrame({
            "date": ["2026-02-20", "2026-02-21"],
            "close": [10.0, 10.5],
        })
        factor = TurnoverFactor()
        result = factor.compute(df)
        assert result.passed == False

    def test_turnover_in_range(self):
        """换手率在范围内应通过"""
        df = generate_monotonic_data(days=20)
        df["turn"] = 3.0  # 在 1% ~ 10% 范围内
        factor = TurnoverFactor()
        result = factor.compute(df)
        assert result.passed == True
        assert result.value == 3.0

    def test_turnover_too_low(self):
        """换手率过低应不通过"""
        df = generate_monotonic_data(days=20)
        df["turn"] = 0.5
        factor = TurnoverFactor()
        result = factor.compute(df)
        assert result.passed == False


class TestNDayReturnFactor:
    """测试 N 日涨幅因子"""

    def test_insufficient_data(self):
        """数据不足应不通过"""
        df = generate_monotonic_data(days=10)
        factor = NDayReturnFactor()
        result = factor.compute(df)
        assert result.passed == False

    def test_return_in_range(self):
        """涨幅在范围内应通过"""
        df = generate_monotonic_data(days=30, daily_growth=0.002)
        factor = NDayReturnFactor()
        result = factor.compute(df)
        assert result.passed == True

    def test_return_too_high(self):
        """涨幅过高应不通过"""
        df = generate_monotonic_data(days=30, daily_growth=0.02)
        factor = NDayReturnFactor()
        result = factor.compute(df)
        assert result.passed == False

