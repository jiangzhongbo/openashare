"""
Layer 3 集成测试 - 完整 Pipeline

需要先运行 wrangler dev：
  cd openashare/worker && npx wrangler dev --local --persist-to=.wrangler/state

运行测试：
  pytest tests/integration/test_pipeline.py -v -s

注意：集成测试需要手动运行，不会在 CI 中自动执行
"""

import pytest
import requests
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, Any

from pipeline.screening.screener import Screener, ScreeningReport
from pipeline.sync.worker_client import WorkerClient
from pipeline.factors.base import Factor, FactorResult
from pipeline.factors.combination import Combination


# 标记为集成测试，需要外部服务
pytestmark = pytest.mark.integration


WORKER_URL = "http://localhost:8787"
WORKER_TOKEN = "test-token-local"


def check_worker_available() -> bool:
    """检查 Worker 是否可用"""
    try:
        response = requests.get(f"{WORKER_URL}/api/screening/latest", timeout=2)
        return response.status_code == 200
    except Exception:
        return False


@dataclass
class MockFactorAlwaysPass(Factor):
    """总是通过的因子"""
    id: str = "mock_pass"
    label: str = "Mock Pass"
    params: Dict[str, Any] = field(default_factory=dict)
    
    def compute(self, df: pd.DataFrame) -> FactorResult:
        return FactorResult(passed=True, value=1.5, detail="Always pass")


@dataclass
class MockFactorAlwaysFail(Factor):
    """总是失败的因子"""
    id: str = "mock_fail"
    label: str = "Mock Fail"
    params: Dict[str, Any] = field(default_factory=dict)
    
    def compute(self, df: pd.DataFrame) -> FactorResult:
        return FactorResult(passed=False, value=0.0, detail="Always fail")


def create_test_data(days: int = 100) -> pd.DataFrame:
    """创建测试数据"""
    dates = pd.date_range(end="2026-02-23", periods=days).strftime("%Y-%m-%d").tolist()
    return pd.DataFrame({
        "date": dates,
        "close": [10.0 + i * 0.1 for i in range(days)],
        "turn": [2.0] * days,
    })


@pytest.fixture
def worker_client():
    """Worker 客户端"""
    if not check_worker_available():
        pytest.skip("Worker not available. Run: cd openashare/worker && npx wrangler dev")
    return WorkerClient(base_url=WORKER_URL, token=WORKER_TOKEN)


class TestPipelineIntegration:
    """完整 Pipeline 集成测试"""

    def test_screen_and_ingest_watch_combination(self, worker_client):
        """筛选并写入 watch 组合"""
        # 1. 设置因子和组合
        factors = [MockFactorAlwaysPass()]
        combinations = [
            Combination(id="watch", label="值得关注", factors=["mock_pass"]),
        ]
        
        # 2. 准备测试数据
        stock_data = {
            "sh.600001": create_test_data(),
            "sh.600002": create_test_data(),
        }
        
        # 3. 执行筛选
        screener = Screener(factors=factors, combinations=combinations)
        report = screener.screen_all(stock_data, run_date="2026-02-23")
        
        assert len(report.results) == 2
        assert report.combination_counts["watch"] == 2
        
        # 4. 写入 Worker
        result = worker_client.ingest(report)
        
        assert result.success == True
        assert result.status_code == 200

    def test_screen_and_ingest_both_combinations(self, worker_client):
        """筛选并写入 watch 和 buy 组合"""
        # 1. 设置因子和组合
        factors = [MockFactorAlwaysPass(), MockFactorAlwaysFail()]
        combinations = [
            Combination(id="watch", label="值得关注", factors=["mock_pass"]),
            Combination(id="buy", label="推荐购买", factors=["mock_pass", "mock_fail"]),
        ]
        
        # 2. 准备测试数据（只有一只通过 watch，没有通过 buy）
        stock_data = {
            "sh.600003": create_test_data(),
        }
        
        # 3. 执行筛选
        screener = Screener(factors=factors, combinations=combinations)
        report = screener.screen_all(stock_data, run_date="2026-02-23")
        
        # 只有 watch 通过，buy 不通过
        assert len(report.results) == 1
        assert report.results[0].combination == "watch"
        
        # 4. 写入 Worker
        result = worker_client.ingest(report)
        
        assert result.success == True

    def test_verify_data_in_worker(self, worker_client):
        """验证数据已写入 Worker"""
        # 先写入数据
        factors = [MockFactorAlwaysPass()]
        combinations = [
            Combination(id="watch", label="值得关注", factors=["mock_pass"]),
        ]
        
        stock_data = {"sh.600099": create_test_data()}
        screener = Screener(factors=factors, combinations=combinations)
        report = screener.screen_all(stock_data, run_date="2026-02-23")
        
        worker_client.ingest(report)
        
        # 验证数据可读取
        response = requests.get(
            f"{WORKER_URL}/api/screening/latest?combination=watch",
            timeout=5,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "results" in data

