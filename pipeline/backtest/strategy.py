"""交易策略：阴线入场 + 止盈出场"""

from pipeline.factors.base import calculate_ma
import pandas as pd


class EntryExitStrategy:
    """入场/出场策略"""

    def __init__(self, entry_window: int = 5, take_profit_pct: float = 10.0,
                 stop_loss_pct: float = 0, max_hold_days: int = 0):
        self.entry_window = entry_window
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct = stop_loss_pct  # 0 表示不设止损
        self.max_hold_days = max_hold_days  # 0 表示不限制

    def is_bearish_candle(self, row) -> bool:
        """当日是否为阴线（收盘 < 开盘）"""
        return float(row["close"]) < float(row["open"])

    def should_exit(self, close: float, entry_price: float) -> bool:
        """收益达到止盈线或跌破止损线则退出"""
        if entry_price <= 0:
            return False
        return_pct = (close - entry_price) / entry_price * 100
        if return_pct >= self.take_profit_pct:
            return True
        if self.stop_loss_pct > 0 and return_pct <= -self.stop_loss_pct:
            return True
        return False
