"""
因子2: MA20 整盘

逻辑：近 check_days 天 MA20 涨幅 ≤ max_rise%
"""

from dataclasses import dataclass, field
from typing import Dict, Any
import pandas as pd

from .base import Factor, FactorResult, calculate_ma


@dataclass
class MA20ConsolidationFactor(Factor):
    """MA20 整盘因子"""
    
    id: str = "ma20_consolidation"
    label: str = "MA20整盘"
    params: Dict[str, Any] = field(default_factory=lambda: {
        "check_days": 20,    # 检查最近多少天
        "max_rise": 1.0,     # MA20 允许的最大涨幅百分比
    })
    
    def compute(self, df: pd.DataFrame) -> FactorResult:
        """
        计算 MA20 是否在整盘状态
        
        Args:
            df: 单只股票的历史数据，按日期升序
        
        Returns:
            FactorResult
        """
        check_days = self.get_param("check_days", 20)
        max_rise = self.get_param("max_rise", 1.0)
        
        # 数据不足
        if len(df) < 20 + check_days:
            return FactorResult(
                passed=False,
                detail="数据不足"
            )
        
        # 计算 MA20
        df = df.copy()
        df["ma20"] = calculate_ma(df, 20)
        ma20 = df["ma20"].dropna()
        
        if len(ma20) < check_days:
            return FactorResult(
                passed=False,
                detail=f"MA20数据不足{check_days}天"
            )
        
        # 取最近 check_days 天的 MA20
        recent_ma20 = ma20.tail(check_days)
        
        # 计算涨幅
        ma20_start = recent_ma20.iloc[0]
        ma20_end = recent_ma20.iloc[-1]
        change_pct = (ma20_end - ma20_start) / ma20_start * 100
        
        # 检查是否在整盘（涨幅 ≤ max_rise）
        # 允许下跌，所以用绝对值判断上涨
        is_consolidating = change_pct <= max_rise
        
        if is_consolidating:
            detail = f"MA20涨幅: {change_pct:.2f}% ≤ {max_rise}%"
        else:
            detail = f"MA20涨幅过大: {change_pct:.2f}% > {max_rise}%"
        
        return FactorResult(
            passed=is_consolidating,
            value=round(change_pct, 2),
            detail=detail
        )

