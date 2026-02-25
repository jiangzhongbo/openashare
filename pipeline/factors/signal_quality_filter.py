"""
信号质量过滤因子

基于参数网格搜索确定的最优过滤条件：
1. 跌破MA60天数 ≤ 5
2. 20日波动率 ≤ 999.0（不限制）
3. 成交量 vs 5日均量 ≥ 1.5
4. 换手率 5%~12%
"""

import pandas as pd
import numpy as np

from .base import Factor, FactorResult


class SignalQualityFilterFactor(Factor):
    """信号质量过滤因子"""

    def __init__(
        self,
        max_days_below: int = 5,
        max_volatility: float = 999.0,
        min_vol_ratio_5d: float = 1.5,
        min_turn: float = 5.0,
        max_turn: float = 12.0,
    ):
        super().__init__(
            id="signal_quality_filter",
            label="信号质量过滤",
            params={
                "max_days_below": max_days_below,
                "max_volatility": max_volatility,
                "min_vol_ratio_5d": min_vol_ratio_5d,
                "min_turn": min_turn,
                "max_turn": max_turn,
            },
        )
        self.max_days_below = max_days_below
        self.max_volatility = max_volatility
        self.min_vol_ratio_5d = min_vol_ratio_5d
        self.min_turn = min_turn
        self.max_turn = max_turn

    def compute(self, df: pd.DataFrame) -> FactorResult:
        if len(df) < 61:
            return FactorResult(passed=False, value=None, detail="数据不足")

        df = df.copy()
        df["ma60"] = df["close"].rolling(window=60).mean()

        today = df.iloc[-1]
        if pd.isna(today["ma60"]):
            return FactorResult(passed=False, value=None, detail="MA60缺失")

        # 条件1: 跌破MA60天数
        days_below = 0
        for i in range(len(df) - 2, max(len(df) - 22, -1), -1):
            row = df.iloc[i]
            if pd.isna(row["ma60"]):
                break
            if row["close"] < row["ma60"]:
                days_below += 1
            else:
                break

        cond1 = days_below <= self.max_days_below

        # 条件2: 20日波动率
        if len(df) >= 20:
            pct_chg = df["pct_chg"].iloc[-20:]
            volatility = float(pct_chg.std()) if pct_chg.notna().sum() >= 10 else 0
        else:
            volatility = 0
        cond2 = volatility <= self.max_volatility

        # 条件3: 成交量 vs 5日均量
        vol_today = float(today.get("volume", 0) or 0)
        vol_5d = df["volume"].iloc[-6:-1].mean()
        vol_ratio_5d = vol_today / vol_5d if vol_5d > 0 else 0
        cond3 = vol_ratio_5d >= self.min_vol_ratio_5d

        # 条件4: 换手率范围
        turn = float(today.get("turn", 0) or 0)
        cond4 = self.min_turn <= turn <= self.max_turn

        passed = cond1 and cond2 and cond3 and cond4

        if passed:
            detail = (
                f"破位{days_below}天, 波动{volatility:.1f}, "
                f"量比5d {vol_ratio_5d:.1f}x, 换手{turn:.1f}%"
            )
            return FactorResult(passed=True, value=vol_ratio_5d, detail=detail)
        else:
            reasons = []
            if not cond1:
                reasons.append(f"破位{days_below}天>{self.max_days_below}")
            if not cond2:
                reasons.append(f"波动{volatility:.1f}>{self.max_volatility}")
            if not cond3:
                reasons.append(f"量比5d {vol_ratio_5d:.1f}<{self.min_vol_ratio_5d}")
            if not cond4:
                reasons.append(f"换手{turn:.1f}%不在{self.min_turn}~{self.max_turn}%")
            return FactorResult(passed=False, value=None, detail="; ".join(reasons))

    def scan(self, df: pd.DataFrame) -> pd.Series:
        """向量化扫描：一次性计算所有行是否通过"""
        if len(df) < 61:
            return pd.Series(False, index=df.index)

        ma60 = df["close"].rolling(window=60).mean()

        # 条件1: 连续跌破 MA60 天数（到昨天为止）<= max_days_below
        below = (df["close"] < ma60).astype(int)
        not_below = (below == 0)
        groups = not_below.cumsum()
        streak = below.groupby(groups).cumsum()
        days_below = streak.shift(1).fillna(0)
        cond1 = days_below <= self.max_days_below

        # 条件2: 20日波动率
        volatility = df["pct_chg"].rolling(20, min_periods=10).std()
        cond2 = volatility.fillna(0) <= self.max_volatility

        # 条件3: 成交量 vs 5日均量
        vol_5d = df["volume"].shift(1).rolling(5).mean()
        vol_5d_safe = vol_5d.replace(0, float("nan"))
        vol_ratio = df["volume"] / vol_5d_safe
        cond3 = vol_ratio >= self.min_vol_ratio_5d

        # 条件4: 换手率范围
        turn = df["turn"] if "turn" in df.columns else pd.Series(0, index=df.index)
        turn = turn.fillna(0)
        cond4 = (turn >= self.min_turn) & (turn <= self.max_turn)

        mask = cond1 & cond2 & cond3 & cond4
        return mask.fillna(False)
