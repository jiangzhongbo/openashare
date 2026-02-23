"""
组合定义

Combination 是因子 ID 的有序集合。
一只股票若该组合内所有因子全部通过，则出现在该组合的筛选结果里。
"""

from dataclasses import dataclass, field
from typing import List, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from .base import Factor, FactorResult


@dataclass
class Combination:
    """因子组合"""

    id: str  # 组合 ID，如 "ma60_bounce_uptrend"
    label: str  # 组合名称，如 "MA60支撑反弹+趋势向上"
    description: str = ""  # 组合描述，用于前端展示
    factors: List[str] = field(default_factory=list)  # 因子 ID 列表
    
    def evaluate(self, factor_results: Dict[str, "FactorResult"]) -> bool:
        """
        评估股票是否通过该组合
        
        所有因子必须全部通过（AND 逻辑）
        
        Args:
            factor_results: 该股票的所有因子计算结果 {factor_id: FactorResult}
        
        Returns:
            是否通过该组合
        """
        for factor_id in self.factors:
            result = factor_results.get(factor_id)
            if result is None or not result.passed:
                return False
        return True
    
    def get_passed_factors(self, factor_results: Dict[str, "FactorResult"]) -> List[str]:
        """
        获取通过的因子列表
        
        Args:
            factor_results: 该股票的所有因子计算结果
        
        Returns:
            通过的因子 ID 列表
        """
        passed = []
        for factor_id in self.factors:
            result = factor_results.get(factor_id)
            if result is not None and result.passed:
                passed.append(factor_id)
        return passed
    
    def get_failed_factors(self, factor_results: Dict[str, "FactorResult"]) -> List[str]:
        """
        获取未通过的因子列表
        
        Args:
            factor_results: 该股票的所有因子计算结果
        
        Returns:
            未通过的因子 ID 列表
        """
        failed = []
        for factor_id in self.factors:
            result = factor_results.get(factor_id)
            if result is None or not result.passed:
                failed.append(factor_id)
        return failed

