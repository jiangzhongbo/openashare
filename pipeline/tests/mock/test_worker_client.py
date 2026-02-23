"""
Layer 2 Mock 测试 - Worker 客户端
测试 HTTP 错误处理：500/403/超时/连接失败
"""

import pytest
from unittest.mock import patch, MagicMock

import requests

from pipeline.sync.worker_client import WorkerClient, WorkerResponse
from pipeline.screening.screener import ScreeningReport, ScreeningResult


def create_test_report() -> ScreeningReport:
    """创建测试报告"""
    return ScreeningReport(
        run_date="2026-02-23",
        total_stocks=100,
        results=[
            ScreeningResult(
                code="000001",
                combination="watch",
                run_date="2026-02-23",
                factor_values={"ma60_monotonic": 1.5},
            ),
        ],
        duration_seconds=10.5,
        combination_counts={"watch": 1},
    )


class TestWorkerClientIngest:
    """测试 ingest 方法"""

    @patch("pipeline.sync.worker_client.requests.post")
    def test_ingest_success(self, mock_post):
        """成功写入"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"inserted": 1}
        mock_post.return_value = mock_response
        
        client = WorkerClient(base_url="http://localhost:8787", token="test-token")
        report = create_test_report()
        result = client.ingest(report)
        
        assert result.success == True
        assert result.status_code == 200
        assert result.data["inserted"] == 1
        
        # 验证请求头
        call_args = mock_post.call_args
        assert call_args.kwargs["headers"]["Authorization"] == "Bearer test-token"

    @patch("pipeline.sync.worker_client.requests.post")
    def test_ingest_unauthorized_403(self, mock_post):
        """403 未授权"""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Unauthorized"
        mock_post.return_value = mock_response
        
        client = WorkerClient(base_url="http://localhost:8787", token="wrong-token")
        report = create_test_report()
        result = client.ingest(report)
        
        assert result.success == False
        assert result.status_code == 403
        assert "Unauthorized" in result.message

    @patch("pipeline.sync.worker_client.requests.post")
    def test_ingest_server_error_500(self, mock_post):
        """500 服务器错误"""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response
        
        client = WorkerClient(base_url="http://localhost:8787", token="test-token")
        report = create_test_report()
        result = client.ingest(report)
        
        assert result.success == False
        assert result.status_code == 500
        assert "Internal Server Error" in result.message

    @patch("pipeline.sync.worker_client.requests.post")
    def test_ingest_timeout(self, mock_post):
        """请求超时"""
        mock_post.side_effect = requests.exceptions.Timeout()
        
        client = WorkerClient(base_url="http://localhost:8787", token="test-token", timeout=5)
        report = create_test_report()
        result = client.ingest(report)
        
        assert result.success == False
        assert result.status_code == 0
        assert "Timeout" in result.message

    @patch("pipeline.sync.worker_client.requests.post")
    def test_ingest_connection_error(self, mock_post):
        """连接错误"""
        mock_post.side_effect = requests.exceptions.ConnectionError("Connection refused")
        
        client = WorkerClient(base_url="http://localhost:8787", token="test-token")
        report = create_test_report()
        result = client.ingest(report)
        
        assert result.success == False
        assert result.status_code == 0
        assert "Connection error" in result.message


class TestWorkerClientHealthCheck:
    """测试 health_check 方法"""

    @patch("pipeline.sync.worker_client.requests.get")
    def test_health_check_success(self, mock_get):
        """健康检查成功"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        client = WorkerClient(base_url="http://localhost:8787")
        result = client.health_check()
        
        assert result == True

    @patch("pipeline.sync.worker_client.requests.get")
    def test_health_check_failure(self, mock_get):
        """健康检查失败"""
        mock_get.side_effect = requests.exceptions.ConnectionError()
        
        client = WorkerClient(base_url="http://localhost:8787")
        result = client.health_check()
        
        assert result == False


class TestWorkerClientConfig:
    """测试配置"""

    @patch.dict("os.environ", {"WORKER_URL": "", "WORKER_WRITE_TOKEN": ""}, clear=False)
    def test_default_url(self):
        """默认 URL（清除环境变量后测试）"""
        # 需要清除环境变量才能测试默认值
        import os
        old_url = os.environ.pop("WORKER_URL", None)
        try:
            client = WorkerClient()
            assert client.base_url == "http://localhost:8787"
        finally:
            if old_url is not None:
                os.environ["WORKER_URL"] = old_url

    @patch.dict("os.environ", {"WORKER_URL": "https://worker.example.com"})
    def test_url_from_env(self):
        """从环境变量获取 URL"""
        client = WorkerClient()
        assert client.base_url == "https://worker.example.com"

    @patch.dict("os.environ", {"WORKER_WRITE_TOKEN": "env-token"})
    def test_token_from_env(self):
        """从环境变量获取 token"""
        client = WorkerClient()
        assert client.token == "env-token"

    def test_url_trailing_slash(self):
        """URL 末尾斜杠被移除"""
        client = WorkerClient(base_url="http://localhost:8787/")
        assert client.base_url == "http://localhost:8787"

