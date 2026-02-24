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
        """买入股票"""
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
