"""回测策略单元测试"""

import pytest
from pipeline.backtest.strategy import EntryExitStrategy


class TestEntryExitStrategy:

    def test_bearish_candle_true(self):
        s = EntryExitStrategy()
        assert s.is_bearish_candle({"open": 10.0, "close": 9.5}) is True

    def test_bearish_candle_false(self):
        s = EntryExitStrategy()
        assert s.is_bearish_candle({"open": 10.0, "close": 10.5}) is False

    def test_bearish_candle_equal(self):
        s = EntryExitStrategy()
        assert s.is_bearish_candle({"open": 10.0, "close": 10.0}) is False

    def test_should_exit_take_profit(self):
        """收益达到止盈线（默认10%）应退出"""
        s = EntryExitStrategy()
        assert s.should_exit(11.0, 10.0) is True

    def test_should_not_exit_below_take_profit(self):
        """收益未达止盈线不应退出"""
        s = EntryExitStrategy()
        assert s.should_exit(10.5, 10.0) is False

    def test_should_not_exit_at_entry(self):
        """价格不变不应退出"""
        s = EntryExitStrategy()
        assert s.should_exit(10.0, 10.0) is False

    def test_should_exit_stop_loss(self):
        """设置止损后，亏损达到止损线应退出"""
        s = EntryExitStrategy(stop_loss_pct=5.0)
        assert s.should_exit(9.4, 10.0) is True

    def test_should_not_exit_no_stop_loss(self):
        """默认不设止损，亏损不触发退出"""
        s = EntryExitStrategy()
        assert s.should_exit(9.0, 10.0) is False
