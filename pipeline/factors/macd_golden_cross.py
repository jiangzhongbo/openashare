"""
因子4: MACD 金叉

逻辑：近 check_days 天内 MACD 线上穿信号线
"""

from dataclasses import dataclass, field
from typing import Dict, Any
import pandas as pd

from .base import Factor, FactorResult, calculate_ema


@dataclass
class MACDGoldenCrossFactor(Factor):
    """MACD 金叉因子"""
    
    id: str = "macd_golden_cross"
    label: str = "MACD金叉"
    params: Dict[str, Any] = field(default_factory=lambda: {
        "check_days": 2,     # 检查最近多少天内发生金叉
        "fast_period": 12,   # 快线周期
        "slow_period": 26,   # 慢线周期
        "signal_period": 9,  # 信号线周期
    })
    
    def compute(self, df: pd.DataFrame) -> FactorResult:
        """
        计算是否发生 MACD 金叉
        
        Args:
            df: 单只股票的历史数据，按日期升序
        
        Returns:
            FactorResult
        """
        check_days = self.get_param("check_days", 2)
        fast_period = self.get_param("fast_period", 12)
        slow_period = self.get_param("slow_period", 26)
        signal_period = self.get_param("signal_period", 9)
        
        # 数据不足
        min_data = slow_period + signal_period + check_days
        if len(df) < min_data:
            return FactorResult(
                passed=False,
                detail=f"数据不足{min_data}条"
            )
        
        # 计算 MACD
        df = df.copy()
        df["ema_fast"] = calculate_ema(df, fast_period)
        df["ema_slow"] = calculate_ema(df, slow_period)
        df["macd"] = df["ema_fast"] - df["ema_slow"]
        df["signal"] = df["macd"].ewm(span=signal_period, adjust=False).mean()
        df["diff"] = df["macd"] - df["signal"]
        
        # 检查最近 check_days 天是否有金叉
        recent = df.tail(check_days + 1)  # 多取一天用于检测穿越
        
        golden_cross_day = None
        for i in range(1, len(recent)):
            prev_diff = recent["diff"].iloc[i - 1]
            curr_diff = recent["diff"].iloc[i]
            
            # 金叉：从负变正
            if prev_diff < 0 and curr_diff >= 0:
                golden_cross_day = i
                break
        
        passed = golden_cross_day is not None
        
        if passed:
            days_ago = len(recent) - 1 - golden_cross_day
            detail = f"{days_ago}天前发生金叉"
            value = float(days_ago)
        else:
            detail = f"近{check_days}天内无金叉"
            value = None
        
        return FactorResult(
            passed=passed,
            value=value,
            detail=detail
        )

