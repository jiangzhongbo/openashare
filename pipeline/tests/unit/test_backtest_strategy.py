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

    def test_should_exit_below_ma10(self):
        s = EntryExitStrategy()
        assert s.should_exit(9.5, 10.0) is True

    def test_should_not_exit_above_ma10(self):
        s = EntryExitStrategy()
        assert s.should_exit(10.5, 10.0) is False

    def test_should_not_exit_equal_ma10(self):
        s = EntryExitStrategy()
        assert s.should_exit(10.0, 10.0) is False
