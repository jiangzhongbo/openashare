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
        nav_history = [(f"day{i}", 100_000 + i * 400) for i in range(250)]
        m = calc_metrics([], nav_history, 100_000)
        assert m["annualized_return_pct"] == pytest.approx(99.6, abs=0.5)

    def test_max_drawdown(self):
        nav_history = [
            ("d1", 100_000),
            ("d2", 110_000),
            ("d3", 99_000),
            ("d4", 105_000),
        ]
        m = calc_metrics([], nav_history, 100_000)
        assert m["max_drawdown_pct"] == pytest.approx(10.0)

    def test_max_drawdown_no_drawdown(self):
        nav_history = [("d1", 100_000), ("d2", 110_000), ("d3", 120_000)]
        m = calc_metrics([], nav_history, 100_000)
        assert m["max_drawdown_pct"] == pytest.approx(0.0)

    def test_win_rate(self):
        trades = [
            Trade("A", "A", "2026-01-01", 10.0, "2026-01-10", 12.0, 100),
            Trade("B", "B", "2026-01-01", 10.0, "2026-01-10", 8.0, 100),
            Trade("C", "C", "2026-01-01", 10.0, "2026-01-10", 11.0, 100),
        ]
        nav_history = [("d1", 100_000)]
        m = calc_metrics(trades, nav_history, 100_000)
        assert m["win_rate_pct"] == pytest.approx(66.67, abs=0.01)
        assert m["total_trades"] == 3

    def test_profit_loss_ratio(self):
        trades = [
            Trade("A", "A", "2026-01-01", 10.0, "2026-01-10", 12.0, 100),
            Trade("B", "B", "2026-01-01", 10.0, "2026-01-10", 8.0, 100),
        ]
        nav_history = [("d1", 100_000)]
        m = calc_metrics(trades, nav_history, 100_000)
        assert m["profit_loss_ratio"] == pytest.approx(1.0)

    def test_avg_holding_days(self):
        trades = [
            Trade("A", "A", "2026-01-01", 10.0, "2026-01-11", 12.0, 100),
            Trade("B", "B", "2026-01-01", 10.0, "2026-01-06", 11.0, 100),
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
