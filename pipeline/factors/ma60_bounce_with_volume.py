"""
MA60 支撑反弹因子

信号特征：
- 前一天跌破 MA60
- 当天重新站上 MA60，且强力拉升（涨幅 > 5%）
- 成交量放大 2 倍以上

用途：
- 捕捉跌破关键支撑位后的强力反弹信号
- 适合短线交易，后续在阴线时择机进入
"""

from typing import Optional
import pandas as pd

from .base import Factor, FactorResult


class MA60BounceWithVolumeFactor(Factor):
    """MA60 支撑反弹因子"""
    
    def __init__(
        self,
        min_gain: float = 5.0,        # 最小涨幅（%）
        volume_ratio: float = 2.0,    # 成交量倍数
        lookback_days: int = 5,       # 回溯天数（检查之前是否在 MA60 上方）
    ):
        """
        初始化因子

        Args:
            min_gain: 最小涨幅（%），默认 5%
            volume_ratio: 成交量倍数，默认 2 倍
            lookback_days: 回溯天数，检查前 N 天是否在 MA60 上方，默认 5 天
        """
        super().__init__(
            id="ma60_bounce_volume",
            label="MA60支撑反弹",
            params={
                "min_gain": min_gain,
                "volume_ratio": volume_ratio,
                "lookback_days": lookback_days,
            },
        )
        self.min_gain = min_gain
        self.volume_ratio = volume_ratio
        self.lookback_days = lookback_days
    
    def compute(self, df: pd.DataFrame) -> FactorResult:
        """
        计算因子
        
        Args:
            df: 股票历史数据，必须包含 close, volume, pct_chg 列
        
        Returns:
            FactorResult: 通过时返回当天涨幅，否则返回 None
        """
        # 至少需要 60 + lookback_days + 1 天数据
        min_days = 60 + self.lookback_days + 1
        if len(df) < min_days:
            return FactorResult(
                passed=False,
                value=None,
                detail=f"数据不足 {min_days} 天",
            )

        # 计算 MA60
        df = df.copy()
        df["ma60"] = df["close"].rolling(window=60).mean()

        # 取最后 lookback_days + 2 天（用于检查之前是否在 MA60 上方）
        lookback_window = self.lookback_days + 2
        recent_df = df.iloc[-lookback_window:]

        yesterday = recent_df.iloc[-2]
        today = recent_df.iloc[-1]
        # 前 lookback_days 天（不包括昨天和今天）
        before_days = recent_df.iloc[:-2]

        # 检查数据完整性
        if pd.isna(yesterday["ma60"]) or pd.isna(today["ma60"]):
            return FactorResult(
                passed=False,
                value=None,
                detail="MA60 数据缺失",
            )

        if pd.isna(today["volume"]) or pd.isna(yesterday["volume"]):
            return FactorResult(
                passed=False,
                value=None,
                detail="成交量数据缺失",
            )

        if pd.isna(today["pct_chg"]):
            return FactorResult(
                passed=False,
                value=None,
                detail="涨跌幅数据缺失",
            )
        
        # 条件 0: 前 lookback_days 天至少有一天在 MA60 上方（说明是"刚跌破"）
        was_above_ma60 = (before_days["close"] > before_days["ma60"]).any()
        condition0 = was_above_ma60

        # 条件 1: 前一天跌破 MA60
        condition1 = yesterday["close"] < yesterday["ma60"]

        # 条件 2: 当天重新站上 MA60
        condition2 = today["close"] > today["ma60"]

        # 条件 3: 当天涨幅 > min_gain
        condition3 = today["pct_chg"] > self.min_gain

        # 条件 4: 成交量放大
        volume_increase = today["volume"] / yesterday["volume"] if yesterday["volume"] > 0 else 0
        condition4 = volume_increase >= self.volume_ratio

        # 判断是否通过
        passed = condition0 and condition1 and condition2 and condition3 and condition4
        
        if passed:
            detail = (
                f"涨幅 {today['pct_chg']:.2f}%, "
                f"成交量放大 {volume_increase:.2f}x, "
                f"收盘 {today['close']:.2f} vs MA60 {today['ma60']:.2f}"
            )
            return FactorResult(
                passed=True,
                value=today["pct_chg"],  # 返回涨幅用于排序
                detail=detail,
            )
        else:
            # 诊断信息
            reasons = []
            if not condition0:
                reasons.append(f"前{self.lookback_days}天未在MA60上方（已连续跌破）")
            if not condition1:
                reasons.append(f"前一天未跌破MA60 ({yesterday['close']:.2f} >= {yesterday['ma60']:.2f})")
            if not condition2:
                reasons.append(f"当天未站上MA60 ({today['close']:.2f} <= {today['ma60']:.2f})")
            if not condition3:
                reasons.append(f"涨幅不足 ({today['pct_chg']:.2f}% < {self.min_gain}%)")
            if not condition4:
                reasons.append(f"成交量未放大 ({volume_increase:.2f}x < {self.volume_ratio}x)")

            return FactorResult(
                passed=False,
                value=None,
                detail="; ".join(reasons) if reasons else "未通过",
            )

    def scan(self, df: pd.DataFrame) -> pd.Series:
        """向量化扫描：一次性计算所有行是否通过"""
        min_days = 60 + self.lookback_days + 1
        if len(df) < min_days:
            return pd.Series(False, index=df.index)

        ma60 = df["close"].rolling(window=60).mean()

        # 条件0: 前 lookback_days 天内至少有一天在 MA60 上方
        above = (df["close"] > ma60).astype(float)
        was_above = above.shift(2).rolling(self.lookback_days, min_periods=1).max() >= 1

        # 条件1: 前一天跌破 MA60
        cond1 = df["close"].shift(1) < ma60.shift(1)

        # 条件2: 当天站上 MA60
        cond2 = df["close"] > ma60

        # 条件3: 涨幅 > min_gain
        cond3 = df["pct_chg"] > self.min_gain

        # 条件4: 成交量放大（避免除以 0）
        vol_yesterday = df["volume"].shift(1).replace(0, float("nan"))
        cond4 = (df["volume"] / vol_yesterday) >= self.volume_ratio

        mask = was_above & cond1 & cond2 & cond3 & cond4
        return mask.fillna(False)

