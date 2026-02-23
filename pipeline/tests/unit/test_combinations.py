"""
Layer 1 单元测试 - 组合
测试组合评估逻辑
"""

import pytest

from pipeline.factors.base import FactorResult
from pipeline.factors.combination import Combination
from pipeline.factors.registry import (
    get_combination,
    get_all_combinations,
    get_required_factors,
    COMBINATIONS,
)


class TestCombinationEvaluate:
    """测试组合评估逻辑"""

    def test_all_pass(self):
        """所有因子通过应通过组合"""
        combination = Combination(
            id="test",
            label="测试",
            factors=["factor_a", "factor_b", "factor_c"],
        )

        factor_results = {
            "factor_a": FactorResult(passed=True, value=1.0),
            "factor_b": FactorResult(passed=True, value=2.0),
            "factor_c": FactorResult(passed=True, value=3.0),
        }

        assert combination.evaluate(factor_results) == True

    def test_partial_pass(self):
        """部分因子通过应不通过组合"""
        combination = Combination(
            id="test",
            label="测试",
            factors=["factor_a", "factor_b", "factor_c"],
        )

        factor_results = {
            "factor_a": FactorResult(passed=True, value=1.0),
            "factor_b": FactorResult(passed=False, value=2.0),
            "factor_c": FactorResult(passed=True, value=3.0),
        }

        assert combination.evaluate(factor_results) == False

    def test_all_fail(self):
        """所有因子不通过应不通过组合"""
        combination = Combination(
            id="test",
            label="测试",
            factors=["factor_a", "factor_b"],
        )

        factor_results = {
            "factor_a": FactorResult(passed=False),
            "factor_b": FactorResult(passed=False),
        }

        assert combination.evaluate(factor_results) == False

    def test_missing_factor_result(self):
        """缺少因子结果应不通过"""
        combination = Combination(
            id="test",
            label="测试",
            factors=["factor_a", "factor_b"],
        )

        factor_results = {
            "factor_a": FactorResult(passed=True),
            # factor_b 缺失
        }

        assert combination.evaluate(factor_results) == False

    def test_empty_factors(self):
        """空因子列表应通过"""
        combination = Combination(
            id="test",
            label="测试",
            factors=[],
        )

        factor_results = {}

        assert combination.evaluate(factor_results) == True


class TestCombinationHelpers:
    """测试组合辅助方法"""

    def test_get_passed_factors(self):
        """获取通过的因子列表"""
        combination = Combination(
            id="test",
            label="测试",
            factors=["factor_a", "factor_b", "factor_c"],
        )
        
        factor_results = {
            "factor_a": FactorResult(passed=True),
            "factor_b": FactorResult(passed=False),
            "factor_c": FactorResult(passed=True),
        }
        
        passed = combination.get_passed_factors(factor_results)
        assert passed == ["factor_a", "factor_c"]

    def test_get_failed_factors(self):
        """获取未通过的因子列表"""
        combination = Combination(
            id="test",
            label="测试",
            factors=["factor_a", "factor_b", "factor_c"],
        )
        
        factor_results = {
            "factor_a": FactorResult(passed=True),
            "factor_b": FactorResult(passed=False),
            "factor_c": FactorResult(passed=True),
        }
        
        failed = combination.get_failed_factors(factor_results)
        assert failed == ["factor_b"]


class TestRegistry:
    """测试注册表"""

    def test_get_combination_ma60_bounce_uptrend(self):
        """获取 ma60_bounce_uptrend 组合"""
        combination = get_combination("ma60_bounce_uptrend")
        assert combination.id == "ma60_bounce_uptrend"
        assert combination.label == "MA60支撑反弹+趋势向上"
        assert len(combination.factors) == 2
        assert "ma60_bounce_volume" in combination.factors
        assert "ma60_recent_uptrend" in combination.factors

    def test_get_unknown_combination(self):
        """获取未知组合应抛异常"""
        with pytest.raises(ValueError):
            get_combination("unknown")

    def test_all_combinations_exist(self):
        """所有组合都应存在"""
        combinations = get_all_combinations()
        assert len(combinations) >= 1
        ids = [c.id for c in combinations]
        assert "ma60_bounce_uptrend" in ids

    def test_required_factors(self):
        """获取所需因子列表"""
        required = get_required_factors()
        assert len(required) > 0
        # 包含 ma60_bounce_uptrend 组合的因子
        assert "ma60_bounce_volume" in required
        assert "ma60_recent_uptrend" in required

