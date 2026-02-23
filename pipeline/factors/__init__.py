"""因子计算模块"""

from .base import Factor, FactorResult, calculate_ma, calculate_ema
from .combination import Combination
from .registry import (
    FACTORS,
    FACTOR_MAP,
    COMBINATIONS,
    COMBINATION_MAP,
    get_factor,
    get_combination,
    get_all_factors,
    get_all_combinations,
    get_required_factors,
)

__all__ = [
    # 基类
    "Factor",
    "FactorResult",
    "Combination",
    # 辅助函数
    "calculate_ma",
    "calculate_ema",
    # 注册表
    "FACTORS",
    "FACTOR_MAP",
    "COMBINATIONS",
    "COMBINATION_MAP",
    "get_factor",
    "get_combination",
    "get_all_factors",
    "get_all_combinations",
    "get_required_factors",
]

