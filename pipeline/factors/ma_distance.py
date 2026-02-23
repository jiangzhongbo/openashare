"""
因子3: MA20/MA60 距离

逻辑：两线偏差 ≤ max_dist%
"""

from dataclasses import dataclass, field
from typing import Dict, Any
import pandas as pd

from .base import Factor, FactorResult, calculate_ma


@dataclass
class MADistanceFactor(Factor):
    """MA20/MA60 距离因子"""
    
    id: str = "ma_distance"
    label: str = "MA20/MA60距离"
    params: Dict[str, Any] = field(default_factory=lambda: {
        "check_days": 5,     # 检查最近多少天
        "max_dist": 10.0,    # 两线最大距离百分比
    })
    
    def compute(self, df: pd.DataFrame) -> FactorResult:
        """
        计算 MA20 和 MA60 的距离
        
        Args:
            df: 单只股票的历史数据，按日期升序
        
        Returns:
            FactorResult
        """
        check_days = self.get_param("check_days", 5)
        max_dist = self.get_param("max_dist", 10.0)
        
        # 数据不足
        if len(df) < 60:
            return FactorResult(
                passed=False,
                detail="数据不足60条"
            )
        
        # 计算 MA20 和 MA60
        df = df.copy()
        df["ma20"] = calculate_ma(df, 20)
        df["ma60"] = calculate_ma(df, 60)
        
        # 取最近 check_days 天
        recent = df.tail(check_days)
        
        # 检查是否有有效数据
        if recent["ma60"].isna().any():
            return FactorResult(
                passed=False,
                detail="MA60数据不足"
            )
        
        # 计算最大距离（百分比）
        distances = []
        for _, row in recent.iterrows():
            ma20 = row["ma20"]
            ma60 = row["ma60"]
            if pd.notna(ma20) and pd.notna(ma60) and ma60 > 0:
                dist = abs(ma20 - ma60) / ma60 * 100
                distances.append(dist)
        
        if not distances:
            return FactorResult(
                passed=False,
                detail="无法计算距离"
            )
        
        max_distance = max(distances)
        avg_distance = sum(distances) / len(distances)
        
        passed = max_distance <= max_dist
        
        if passed:
            detail = f"最大距离: {max_distance:.2f}% ≤ {max_dist}%"
        else:
            detail = f"距离过大: {max_distance:.2f}% > {max_dist}%"
        
        return FactorResult(
            passed=passed,
            value=round(avg_distance, 2),
            detail=detail
        )

