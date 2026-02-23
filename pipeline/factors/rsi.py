"""
因子5: RSI 超卖反弹

逻辑：RSI 从超卖区（< oversold）向上穿越
"""

from dataclasses import dataclass, field
from typing import Dict, Any
import pandas as pd
import numpy as np

from .base import Factor, FactorResult


@dataclass
class RSIFactor(Factor):
    """RSI 超卖反弹因子"""
    
    id: str = "rsi"
    label: str = "RSI超卖反弹"
    params: Dict[str, Any] = field(default_factory=lambda: {
        "period": 14,        # RSI 周期
        "oversold": 35,      # 超卖阈值
        "check_days": 3,     # 检查最近多少天
    })
    
    def _calculate_rsi(self, df: pd.DataFrame, period: int) -> pd.Series:
        """计算 RSI"""
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        
        avg_gain = gain.rolling(window=period, min_periods=period).mean()
        avg_loss = loss.rolling(window=period, min_periods=period).mean()
        
        rs = avg_gain / avg_loss.replace(0, np.inf)
        rsi = 100 - (100 / (1 + rs))
        
        return rsi
    
    def compute(self, df: pd.DataFrame) -> FactorResult:
        """
        计算是否发生 RSI 超卖反弹
        
        Args:
            df: 单只股票的历史数据，按日期升序
        
        Returns:
            FactorResult
        """
        period = self.get_param("period", 14)
        oversold = self.get_param("oversold", 35)
        check_days = self.get_param("check_days", 3)
        
        # 数据不足
        min_data = period + check_days + 1
        if len(df) < min_data:
            return FactorResult(
                passed=False,
                detail=f"数据不足{min_data}条"
            )
        
        # 计算 RSI
        df = df.copy()
        df["rsi"] = self._calculate_rsi(df, period)
        
        # 取最近 check_days + 1 天
        recent = df.tail(check_days + 1)
        
        # 检查是否从超卖区向上穿越
        passed = False
        cross_day = None
        
        for i in range(1, len(recent)):
            prev_rsi = recent["rsi"].iloc[i - 1]
            curr_rsi = recent["rsi"].iloc[i]
            
            if pd.notna(prev_rsi) and pd.notna(curr_rsi):
                # 超卖反弹：前一天在超卖区，当天向上穿越
                if prev_rsi < oversold and curr_rsi >= oversold:
                    passed = True
                    cross_day = i
                    break
        
        current_rsi = recent["rsi"].iloc[-1]
        
        if passed:
            days_ago = len(recent) - 1 - cross_day
            detail = f"{days_ago}天前RSI从{oversold}向上穿越"
        else:
            detail = f"当前RSI: {current_rsi:.1f}，无超卖反弹"
        
        return FactorResult(
            passed=passed,
            value=round(current_rsi, 1) if pd.notna(current_rsi) else None,
            detail=detail
        )

