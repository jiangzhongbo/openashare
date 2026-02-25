"""
因子注册表 + 组合定义

所有因子和组合的统一注册点。
- 添加新因子：在 FACTORS 列表中添加实例
- 修改组合：调整 COMBINATIONS 中的 factors 列表
"""

from typing import Dict, List

from .base import Factor
from .combination import Combination
from .ma60_monotonic import MA60MonotonicFactor
from .ma20_consolidation import MA20ConsolidationFactor
from .ma_distance import MADistanceFactor
from .macd_golden_cross import MACDGoldenCrossFactor
from .rsi import RSIFactor
from .turnover import TurnoverFactor
from .n_day_return import NDayReturnFactor
from .ma60_bounce_with_volume import MA60BounceWithVolumeFactor
from .ma60_recent_uptrend import MA60RecentUptrendFactor
from .signal_quality_filter import SignalQualityFilterFactor


# ============================================================
# 因子注册表
# ============================================================

FACTORS: List[Factor] = [
    MA60MonotonicFactor(),
    MA20ConsolidationFactor(),
    MADistanceFactor(),
    MACDGoldenCrossFactor(),
    RSIFactor(),
    TurnoverFactor(),
    NDayReturnFactor(),
    MA60BounceWithVolumeFactor(),
    MA60RecentUptrendFactor(),
    SignalQualityFilterFactor(),
]

# 因子 ID -> 因子实例 的映射
FACTOR_MAP: Dict[str, Factor] = {f.id: f for f in FACTORS}


# ============================================================
# 组合定义
# ============================================================

COMBINATIONS: List[Combination] = [
    Combination(
        id="ma60_bounce_uptrend",
        label="MA60支撑反弹+趋势向上",
        description="跌破MA60后强力反弹+趋势向上+信号质量过滤（跌破≤5天、量比5d≥1.5、换手率5~12%）。10%止盈、15天最大持仓、5天入场窗口。",
        entry_rule="信号日出现阴线时买入（5天入场窗口）。条件：跌破MA60后反弹涨幅≥5%、量比5d≥1.5、换手率5~12%、跌破天数≤5天、MA60近10日持续上升",
        exit_rule="止盈：涨幅达10%卖出 | 最大持仓：15个交易日强制卖出",
        factors=[
            "ma60_bounce_volume",      # MA60 支撑反弹因子
            "ma60_recent_uptrend",     # MA60 近期上升趋势（10天）
            "signal_quality_filter",   # 信号质量过滤
        ],
    ),
]

# 组合 ID -> 组合实例 的映射
COMBINATION_MAP: Dict[str, Combination] = {c.id: c for c in COMBINATIONS}


# ============================================================
# 辅助函数
# ============================================================

def get_factor(factor_id: str) -> Factor:
    """获取因子实例"""
    factor = FACTOR_MAP.get(factor_id)
    if factor is None:
        raise ValueError(f"Unknown factor: {factor_id}")
    return factor


def get_combination(combination_id: str) -> Combination:
    """获取组合实例"""
    combination = COMBINATION_MAP.get(combination_id)
    if combination is None:
        raise ValueError(f"Unknown combination: {combination_id}")
    return combination


def get_all_factors() -> List[Factor]:
    """获取所有因子"""
    return FACTORS.copy()


def get_all_combinations() -> List[Combination]:
    """获取所有组合"""
    return COMBINATIONS.copy()


def get_required_factors() -> List[str]:
    """获取所有组合需要的因子 ID（去重）"""
    required = set()
    for combination in COMBINATIONS:
        required.update(combination.factors)
    return list(required)

