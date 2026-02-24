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
        p = Portfolio(initial_capital=100_000)
        p.buy("000001", "平安银行", 10.0, "2026-01-01", 50_000)
        assert "000001" in p.positions
        assert p.positions["000001"].shares == 5000
        assert p.cash == pytest.approx(50_000)

    def test_buy_rounds_to_100(self):
        p = Portfolio(initial_capital=100_000)
        p.buy("000001", "平安银行", 33.0, "2026-01-01", 50_000)
        assert p.positions["000001"].shares == 1500
        assert p.cash == pytest.approx(100_000 - 1500 * 33.0)

    def test_buy_insufficient_cash(self):
        p = Portfolio(initial_capital=1_000)
        p.buy("000001", "平安银行", 100.0, "2026-01-01", 50_000)
        assert "000001" not in p.positions
        assert p.cash == 1_000

    def test_buy_zero_shares(self):
        p = Portfolio(initial_capital=100_000)
        p.buy("000001", "平安银行", 600.0, "2026-01-01", 5_000)
        assert "000001" not in p.positions

    def test_sell(self):
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
        p = Portfolio(initial_capital=100_000)
        p.sell("000001", 12.0, "2026-01-10")
        assert len(p.closed_trades) == 0

    def test_nav(self):
        p = Portfolio(initial_capital=100_000)
        p.buy("000001", "平安银行", 10.0, "2026-01-01", 50_000)
        nav = p.get_nav({"000001": 12.0})
        assert nav == pytest.approx(110_000)

    def test_nav_no_positions(self):
        p = Portfolio(initial_capital=100_000)
        assert p.get_nav({}) == pytest.approx(100_000)

    def test_has_position(self):
        p = Portfolio(initial_capital=100_000)
        assert p.has_position("000001") is False
        p.buy("000001", "平安银行", 10.0, "2026-01-01", 50_000)
        assert p.has_position("000001") is True

    def test_no_duplicate_buy(self):
        p = Portfolio(initial_capital=100_000)
        p.buy("000001", "平安银行", 10.0, "2026-01-01", 50_000)
        p.buy("000001", "平安银行", 11.0, "2026-01-02", 30_000)
        assert p.positions["000001"].entry_price == 10.0
        assert p.positions["000001"].shares == 5000
