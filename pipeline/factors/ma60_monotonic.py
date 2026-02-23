"""
因子1: MA60 单调不减

逻辑：全部 MA60 历史无下降 + 总涨幅 ≥ min_change%
"""

from dataclasses import dataclass, field
from typing import Dict, Any
import pandas as pd

from .base import Factor, FactorResult, calculate_ma


@dataclass
class MA60MonotonicFactor(Factor):
    """MA60 单调不减因子"""
    
    id: str = "ma60_monotonic"
    label: str = "MA60单调不减"
    params: Dict[str, Any] = field(default_factory=lambda: {
        "min_days": 10,      # 至少需要多少天 MA60 数据
        "min_change": 1.0,   # MA60 最小涨幅百分比
    })
    
    def compute(self, df: pd.DataFrame) -> FactorResult:
        """
        计算 MA60 是否单调不减
        
        Args:
            df: 单只股票的历史数据，按日期升序
        
        Returns:
            FactorResult
        """
        min_days = self.get_param("min_days", 10)
        min_change = self.get_param("min_change", 1.0)
        
        # 数据不足
        if len(df) < 60:
            return FactorResult(
                passed=False,
                detail="数据不足60条"
            )
        
        # 计算 MA60
        df = df.copy()
        df["ma60"] = calculate_ma(df, 60)
        ma60 = df["ma60"].dropna()
        
        if len(ma60) < min_days:
            return FactorResult(
                passed=False,
                detail=f"MA60数据不足{min_days}天"
            )
        
        # 检查是否单调不减
        down_days = 0
        for i in range(1, len(ma60)):
            if ma60.iloc[i] < ma60.iloc[i - 1]:
                down_days += 1
        
        is_monotonic = (down_days == 0)
        
        # 计算涨幅
        ma60_start = ma60.iloc[0]
        ma60_end = ma60.iloc[-1]
        change_pct = (ma60_end - ma60_start) / ma60_start * 100
        
        # 是否满足最小涨幅
        meets_min_change = change_pct >= min_change
        
        passed = is_monotonic and meets_min_change
        
        if not is_monotonic:
            detail = f"非单调，下跌天数: {down_days}"
        elif not meets_min_change:
            detail = f"涨幅不足: {change_pct:.2f}% < {min_change}%"
        else:
            detail = f"涨幅: {change_pct:.2f}%"
        
        return FactorResult(
            passed=passed,
            value=round(change_pct, 2),
            detail=detail
        )

