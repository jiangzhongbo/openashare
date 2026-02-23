"""
因子7: N日涨幅区间

逻辑：近 days 日累计涨幅在 min% ~ max%
"""

from dataclasses import dataclass, field
from typing import Dict, Any
import pandas as pd

from .base import Factor, FactorResult


@dataclass
class NDayReturnFactor(Factor):
    """N日涨幅区间因子"""
    
    id: str = "n_day_return"
    label: str = "N日涨幅区间"
    params: Dict[str, Any] = field(default_factory=lambda: {
        "days": 20,          # 检查最近多少天
        "min_return": -5.0,  # 最小涨幅百分比
        "max_return": 15.0,  # 最大涨幅百分比
    })
    
    def compute(self, df: pd.DataFrame) -> FactorResult:
        """
        计算 N 日涨幅是否在区间内
        
        Args:
            df: 单只股票的历史数据，按日期升序
        
        Returns:
            FactorResult
        """
        days = self.get_param("days", 20)
        min_return = self.get_param("min_return", -5.0)
        max_return = self.get_param("max_return", 15.0)
        
        # 数据不足
        if len(df) < days:
            return FactorResult(
                passed=False,
                detail=f"数据不足{days}天"
            )
        
        # 取最近 days 天
        recent = df.tail(days)
        
        # 计算涨幅
        start_price = recent["close"].iloc[0]
        end_price = recent["close"].iloc[-1]
        
        if start_price <= 0:
            return FactorResult(
                passed=False,
                detail="起始价格无效"
            )
        
        return_pct = (end_price - start_price) / start_price * 100
        
        # 检查是否在范围内
        passed = min_return <= return_pct <= max_return
        
        if passed:
            detail = f"{days}日涨幅: {return_pct:.2f}% (在{min_return}%~{max_return}%内)"
        elif return_pct < min_return:
            detail = f"{days}日跌幅过大: {return_pct:.2f}% < {min_return}%"
        else:
            detail = f"{days}日涨幅过大: {return_pct:.2f}% > {max_return}%"
        
        return FactorResult(
            passed=passed,
            value=round(return_pct, 2),
            detail=detail
        )

