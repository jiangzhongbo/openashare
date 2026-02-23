"""
Layer 1 单元测试 - 筛选引擎
测试筛选逻辑：通过 watch 不通过 buy / 两个都通过 / 都不通过
"""

import pytest
import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Any

from pipeline.screening.screener import Screener, ScreeningResult, ScreeningReport
from pipeline.factors.base import Factor, FactorResult
from pipeline.factors.combination import Combination


@dataclass
class MockFactorPass(Factor):
    """总是通过的因子"""
    id: str = "mock_pass"
    label: str = "Mock Pass"
    params: Dict[str, Any] = field(default_factory=dict)

    def compute(self, df: pd.DataFrame) -> FactorResult:
        return FactorResult(passed=True, value=1.0, detail="Always pass")


@dataclass
class MockFactorFail(Factor):
    """总是失败的因子"""
    id: str = "mock_fail"
    label: str = "Mock Fail"
    params: Dict[str, Any] = field(default_factory=dict)

    def compute(self, df: pd.DataFrame) -> FactorResult:
        return FactorResult(passed=False, value=0.0, detail="Always fail")


@dataclass
class MockFactorConditional(Factor):
    """根据数据条件决定是否通过"""
    id: str = "mock_conditional"
    label: str = "Mock Conditional"
    params: Dict[str, Any] = field(default_factory=dict)

    def compute(self, df: pd.DataFrame) -> FactorResult:
        # 如果最后收盘价 > 15，则通过
        last_close = df["close"].iloc[-1]
        passed = last_close > 15
        return FactorResult(passed=passed, value=float(last_close), detail=f"Close: {last_close}")


def create_test_data(days: int = 100, last_close: float = 10.0) -> pd.DataFrame:
    """创建测试数据"""
    dates = pd.date_range(end="2026-02-23", periods=days).strftime("%Y-%m-%d").tolist()
    prices = [10.0] * (days - 1) + [last_close]
    return pd.DataFrame({
        "date": dates,
        "close": prices,
        "turn": [2.0] * days,
    })


class TestScreenerSingleStock:
    """测试单只股票筛选"""

    def test_pass_both_combinations(self):
        """通过两个组合"""
        factors = [MockFactorPass()]
        combinations = [
            Combination(id="watch", label="Watch", factors=["mock_pass"]),
            Combination(id="buy", label="Buy", factors=["mock_pass"]),
        ]
        
        screener = Screener(factors=factors, combinations=combinations)
        df = create_test_data()
        results = screener.screen_single_stock(df, "000001", "2026-02-23")
        
        assert len(results) == 2
        assert {r.combination for r in results} == {"watch", "buy"}

    def test_pass_watch_fail_buy(self):
        """通过 watch 但不通过 buy"""
        factors = [MockFactorPass(), MockFactorFail()]
        combinations = [
            Combination(id="watch", label="Watch", factors=["mock_pass"]),
            Combination(id="buy", label="Buy", factors=["mock_pass", "mock_fail"]),
        ]
        
        screener = Screener(factors=factors, combinations=combinations)
        df = create_test_data()
        results = screener.screen_single_stock(df, "000001", "2026-02-23")
        
        assert len(results) == 1
        assert results[0].combination == "watch"

    def test_fail_both_combinations(self):
        """两个组合都不通过"""
        factors = [MockFactorFail()]
        combinations = [
            Combination(id="watch", label="Watch", factors=["mock_fail"]),
            Combination(id="buy", label="Buy", factors=["mock_fail"]),
        ]
        
        screener = Screener(factors=factors, combinations=combinations)
        df = create_test_data()
        results = screener.screen_single_stock(df, "000001", "2026-02-23")
        
        assert len(results) == 0


class TestScreenerAll:
    """测试全市场筛选"""

    def test_screen_multiple_stocks(self):
        """筛选多只股票"""
        factors = [MockFactorConditional()]
        combinations = [
            Combination(id="watch", label="Watch", factors=["mock_conditional"]),
        ]
        
        screener = Screener(factors=factors, combinations=combinations)
        
        # 股票1 通过，股票2 不通过
        stock_data = {
            "000001": create_test_data(last_close=20.0),  # 通过
            "000002": create_test_data(last_close=10.0),  # 不通过
            "000003": create_test_data(last_close=18.0),  # 通过
        }
        
        report = screener.screen_all(stock_data, run_date="2026-02-23")
        
        assert report.total_stocks == 3
        assert len(report.results) == 2
        assert report.combination_counts["watch"] == 2
        
        codes = {r.code for r in report.results}
        assert codes == {"000001", "000003"}

    def test_report_to_ingest_payload(self):
        """测试转换为 ingest payload"""
        factors = [MockFactorPass()]
        combinations = [
            Combination(id="watch", label="Watch", factors=["mock_pass"]),
        ]
        
        screener = Screener(factors=factors, combinations=combinations)
        stock_data = {"000001": create_test_data()}
        
        report = screener.screen_all(stock_data, run_date="2026-02-23")
        payload = report.to_ingest_payload()
        
        assert payload["run_date"] == "2026-02-23"
        assert len(payload["results"]) == 1
        assert payload["results"][0]["code"] == "000001"
        assert payload["results"][0]["combination"] == "watch"
        assert payload["run_log"]["total_stocks"] == 1
        assert payload["run_log"]["passed_stocks"] == 1
        assert payload["run_log"]["status"] == "success"

    def test_progress_callback(self):
        """测试进度回调"""
        factors = [MockFactorPass()]
        combinations = [
            Combination(id="watch", label="Watch", factors=["mock_pass"]),
        ]
        
        screener = Screener(factors=factors, combinations=combinations)
        stock_data = {
            "000001": create_test_data(),
            "000002": create_test_data(),
        }
        
        progress_log = []
        def callback(current, total, code):
            progress_log.append((current, total, code))
        
        report = screener.screen_all(stock_data, progress_callback=callback)
        
        assert len(progress_log) == 2
        assert progress_log[0][1] == 2  # total
        assert progress_log[1][0] == 2  # current

