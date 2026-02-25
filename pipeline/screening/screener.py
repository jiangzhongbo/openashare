"""
筛选引擎

一次遍历全市场，对每只股票计算所有因子，再按组合评估。
"""

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from datetime import date
import pandas as pd

import sys
import os
# 支持从 pipeline 目录直接运行
if __name__ != "__main__" and "pipeline" not in sys.modules:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from pipeline.factors.base import Factor, FactorResult
    from pipeline.factors.registry import (
        get_all_factors,
        get_all_combinations,
        FACTOR_MAP,
    )
    from pipeline.factors.combination import Combination
except ModuleNotFoundError:
    from factors.base import Factor, FactorResult
    from factors.registry import (
        get_all_factors,
        get_all_combinations,
        FACTOR_MAP,
    )
    from factors.combination import Combination


@dataclass
class ScreeningResult:
    """单只股票的筛选结果"""
    code: str
    name: str = ""    # 股票名称
    combination: str = ""  # 组合 ID
    run_date: str = ""     # 运行日期 YYYY-MM-DD
    latest_price: Optional[float] = None  # 最新价格
    factor_values: Dict[str, Optional[float]] = field(default_factory=dict)
    factor_details: Dict[str, str] = field(default_factory=dict)


@dataclass
class ScreeningReport:
    """筛选报告"""
    run_date: str
    total_stocks: int
    results: List[ScreeningResult]
    duration_seconds: float

    # 按组合统计通过数
    combination_counts: Dict[str, int] = field(default_factory=dict)
    # 组合元数据（用于同步到 Worker）
    combinations: List[Combination] = field(default_factory=list)

    def to_ingest_payload(self) -> Dict[str, Any]:
        """转换为 Worker /api/ingest 的 payload 格式"""
        payload: Dict[str, Any] = {
            "run_date": self.run_date,
            "results": [
                {
                    "code": r.code,
                    "name": r.name,
                    "combination": r.combination,
                    "latest_price": r.latest_price,
                    **{f"factor_{k}": v for k, v in r.factor_values.items()},
                }
                for r in self.results
            ],
            "run_log": {
                "run_date": self.run_date,
                "total_stocks": self.total_stocks,
                "passed_stocks": len(self.results),
                "duration_seconds": self.duration_seconds,
                "status": "success",
            },
        }
        if self.combinations:
            payload["combinations"] = [c.to_dict() for c in self.combinations]
        return payload


class Screener:
    """筛选引擎"""
    
    def __init__(
        self,
        factors: Optional[List[Factor]] = None,
        combinations: Optional[List[Combination]] = None,
    ):
        """
        初始化筛选引擎
        
        Args:
            factors: 因子列表，默认使用注册表中的所有因子
            combinations: 组合列表，默认使用注册表中的所有组合
        """
        self.factors = factors or get_all_factors()
        self.combinations = combinations or get_all_combinations()
        
        # 构建因子 ID -> 因子实例映射
        self.factor_map = {f.id: f for f in self.factors}
    
    def screen_single_stock(
        self,
        df: pd.DataFrame,
        code: str,
        run_date: str,
        stock_name: str = "",
    ) -> List[ScreeningResult]:
        """
        筛选单只股票

        Args:
            df: 股票历史数据（按日期升序）
            code: 股票代码
            run_date: 运行日期
            stock_name: 股票名称

        Returns:
            通过的组合结果列表（可能为空）
        """
        # 1. 计算所有因子
        factor_results: Dict[str, FactorResult] = {}
        for factor in self.factors:
            result = factor.compute(df)
            factor_results[factor.id] = result

        # 2. 获取股票基本信息
        latest_row = df.iloc[-1] if len(df) > 0 else None
        latest_price = None

        if latest_row is not None:
            # 从最新一行获取价格
            latest_price = float(latest_row.get("close", 0))

        # 3. 评估每个组合
        results: List[ScreeningResult] = []
        for combination in self.combinations:
            if combination.evaluate(factor_results):
                # 组合通过，生成结果
                result = ScreeningResult(
                    code=code,
                    name=stock_name,
                    combination=combination.id,
                    run_date=run_date,
                    latest_price=latest_price,
                    factor_values={
                        fid: factor_results[fid].value
                        for fid in combination.factors
                        if fid in factor_results
                    },
                    factor_details={
                        fid: factor_results[fid].detail or ""
                        for fid in combination.factors
                        if fid in factor_results
                    },
                )
                results.append(result)
        
        return results
    
    def screen_all(
        self,
        stock_data: Dict[str, pd.DataFrame],
        run_date: Optional[str] = None,
        stock_names: Optional[Dict[str, str]] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> ScreeningReport:
        """
        筛选全市场

        Args:
            stock_data: 股票代码 -> 历史数据 DataFrame 的映射
            run_date: 运行日期，默认为今天
            stock_names: 股票代码 -> 股票名称的映射
            progress_callback: 进度回调 (当前, 总数, 股票代码)

        Returns:
            ScreeningReport
        """
        if run_date is None:
            run_date = date.today().strftime("%Y-%m-%d")

        if stock_names is None:
            stock_names = {}

        start_time = time.time()
        all_results: List[ScreeningResult] = []
        total = len(stock_data)

        for i, (code, df) in enumerate(stock_data.items(), 1):
            if progress_callback:
                progress_callback(i, total, code)

            # 确保数据按日期排序
            df = df.sort_values("date")

            # 获取股票名称
            stock_name = stock_names.get(code, "")

            # 筛选单只股票
            results = self.screen_single_stock(df, code, run_date, stock_name)
            all_results.extend(results)
        
        duration = time.time() - start_time
        
        # 按组合统计
        combination_counts: Dict[str, int] = {}
        for r in all_results:
            combination_counts[r.combination] = combination_counts.get(r.combination, 0) + 1
        
        return ScreeningReport(
            run_date=run_date,
            total_stocks=total,
            results=all_results,
            duration_seconds=round(duration, 2),
            combination_counts=combination_counts,
            combinations=self.combinations,
        )

