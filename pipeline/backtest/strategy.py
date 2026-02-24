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
