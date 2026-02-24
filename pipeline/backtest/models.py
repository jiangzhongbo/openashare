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
