"""
MA60 近期上升趋势因子

检查最近 N 天的 MA60 是否严格向上（每天都比前一天高）

用途：
- 短期趋势确认：确保当前处于上升趋势中
- 过滤震荡股：排除 MA60 来回波动的股票
- 组合前置条件：只在趋势向上时考虑其他买入信号
"""

from typing import Optional
import pandas as pd

from .base import Factor, FactorResult


class MA60RecentUptrendFactor(Factor):
    """MA60 近期上升趋势因子"""
    
    def __init__(
        self,
        lookback_days: int = 10,      # 检查最近 N 天
        min_change: float = 0.5,      # 最小涨幅（%）
    ):
        """
        初始化因子
        
        Args:
            lookback_days: 检查最近 N 天，默认 10 天
            min_change: 最近 N 天 MA60 最小涨幅（%），默认 0.5%
        """
        super().__init__(
            id="ma60_recent_uptrend",
            label="MA60近期上升",
            params={
                "lookback_days": lookback_days,
                "min_change": min_change,
            },
        )
        self.lookback_days = lookback_days
        self.min_change = min_change
    
    def compute(self, df: pd.DataFrame) -> FactorResult:
        """
        计算因子
        
        Args:
            df: 股票历史数据，必须包含 close 列
        
        Returns:
            FactorResult: 通过时返回最近 N 天 MA60 涨幅，否则返回 None
        """
        # 至少需要 60 + lookback_days 天数据
        min_days = 60 + self.lookback_days
        if len(df) < min_days:
            return FactorResult(
                passed=False,
                value=None,
                detail=f"数据不足 {min_days} 天",
            )
        
        # 计算 MA60
        df = df.copy()
        df["ma60"] = df["close"].rolling(window=60).mean()
        
        # 取最近 lookback_days 天的 MA60
        recent_ma60 = df["ma60"].dropna().iloc[-self.lookback_days:]
        
        if len(recent_ma60) < self.lookback_days:
            return FactorResult(
                passed=False,
                value=None,
                detail=f"MA60 数据不足 {self.lookback_days} 天",
            )
        
        # 检查是否严格向上（每天都比前一天高）
        down_days = 0
        flat_days = 0
        for i in range(1, len(recent_ma60)):
            if recent_ma60.iloc[i] < recent_ma60.iloc[i - 1]:
                down_days += 1
            elif recent_ma60.iloc[i] == recent_ma60.iloc[i - 1]:
                flat_days += 1
        
        is_strictly_up = (down_days == 0 and flat_days == 0)
        
        # 计算涨幅
        ma60_start = recent_ma60.iloc[0]
        ma60_end = recent_ma60.iloc[-1]
        change_pct = (ma60_end - ma60_start) / ma60_start * 100
        
        # 是否满足最小涨幅
        meets_min_change = change_pct >= self.min_change
        
        # 判断是否通过
        passed = is_strictly_up and meets_min_change
        
        if passed:
            detail = (
                f"最近{self.lookback_days}天严格向上, "
                f"涨幅 {change_pct:.2f}%, "
                f"MA60: {ma60_start:.2f} → {ma60_end:.2f}"
            )
            return FactorResult(
                passed=True,
                value=change_pct,  # 返回涨幅用于排序
                detail=detail,
            )
        else:
            # 诊断信息
            reasons = []
            if down_days > 0:
                reasons.append(f"有{down_days}天下降")
            if flat_days > 0:
                reasons.append(f"有{flat_days}天持平")
            if not meets_min_change:
                reasons.append(f"涨幅不足 ({change_pct:.2f}% < {self.min_change}%)")
            
            return FactorResult(
                passed=False,
                value=None,
                detail="; ".join(reasons) if reasons else "未通过",
            )

