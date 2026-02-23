"""
因子6: 换手率适中

逻辑：近 check_days 天平均换手率在 min% ~ max%
"""

from dataclasses import dataclass, field
from typing import Dict, Any
import pandas as pd

from .base import Factor, FactorResult


@dataclass
class TurnoverFactor(Factor):
    """换手率适中因子"""
    
    id: str = "turnover"
    label: str = "换手率适中"
    params: Dict[str, Any] = field(default_factory=lambda: {
        "check_days": 5,     # 检查最近多少天
        "min_rate": 1.0,     # 最小换手率百分比
        "max_rate": 10.0,    # 最大换手率百分比
    })
    
    def compute(self, df: pd.DataFrame) -> FactorResult:
        """
        计算换手率是否适中
        
        Args:
            df: 单只股票的历史数据，按日期升序
                需包含 turn 列
        
        Returns:
            FactorResult
        """
        check_days = self.get_param("check_days", 5)
        min_rate = self.get_param("min_rate", 1.0)
        max_rate = self.get_param("max_rate", 10.0)
        
        # 检查是否有换手率数据
        if "turn" not in df.columns:
            return FactorResult(
                passed=False,
                detail="无换手率数据"
            )
        
        # 数据不足
        if len(df) < check_days:
            return FactorResult(
                passed=False,
                detail=f"数据不足{check_days}天"
            )
        
        # 取最近 check_days 天的换手率
        recent_turn = df["turn"].tail(check_days)
        
        # 去除空值
        valid_turn = recent_turn.dropna()
        
        if len(valid_turn) == 0:
            return FactorResult(
                passed=False,
                detail="换手率数据全为空"
            )
        
        # 计算平均换手率
        avg_turn = valid_turn.mean()
        
        # 检查是否在范围内
        passed = min_rate <= avg_turn <= max_rate
        
        if passed:
            detail = f"平均换手率: {avg_turn:.2f}% (在{min_rate}%~{max_rate}%内)"
        elif avg_turn < min_rate:
            detail = f"换手率过低: {avg_turn:.2f}% < {min_rate}%"
        else:
            detail = f"换手率过高: {avg_turn:.2f}% > {max_rate}%"
        
        return FactorResult(
            passed=passed,
            value=round(avg_turn, 2),
            detail=detail
        )

