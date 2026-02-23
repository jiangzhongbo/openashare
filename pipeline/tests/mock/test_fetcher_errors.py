"""
Layer 2 Mock 测试 - BaoStockFetcher
测试 BaoStock 失败重试逻辑
"""

import pytest
from unittest.mock import patch, MagicMock
import pandas as pd

from pipeline.data.fetcher import BaoStockFetcher


class MockResultSet:
    """模拟 BaoStock 返回的结果集"""
    
    def __init__(self, error_code="0", error_msg="", data=None, fields=None):
        self.error_code = error_code
        self.error_msg = error_msg
        self._data = data or []
        self.fields = fields or []
        self._index = 0
    
    def next(self):
        if self._index < len(self._data):
            return True
        return False
    
    def get_row_data(self):
        row = self._data[self._index]
        self._index += 1
        return row


class TestBaoStockFetcherLogin:
    """测试登录逻辑"""

    @patch("pipeline.data.fetcher.bs")
    def test_login_success(self, mock_bs):
        """登录成功"""
        mock_bs.login.return_value = MagicMock(error_code="0")
        fetcher = BaoStockFetcher()
        assert fetcher.logged_in is True

    @patch("pipeline.data.fetcher.bs")
    def test_login_failure(self, mock_bs):
        """登录失败"""
        mock_bs.login.return_value = MagicMock(error_code="1", error_msg="Login failed")
        fetcher = BaoStockFetcher()
        assert fetcher.logged_in is False

    @patch("pipeline.data.fetcher.bs")
    def test_login_exception(self, mock_bs):
        """登录异常"""
        mock_bs.login.side_effect = Exception("Network error")
        fetcher = BaoStockFetcher()
        assert fetcher.logged_in is False


class TestGetStockHistory:
    """测试获取股票历史数据"""

    @patch("pipeline.data.fetcher.bs")
    @patch("pipeline.data.fetcher.time.sleep")
    def test_get_stock_history_success(self, mock_sleep, mock_bs):
        """正常获取数据"""
        mock_bs.login.return_value = MagicMock(error_code="0")
        
        # 模拟返回数据
        fields = ["date", "open", "high", "low", "close", "volume", "amount", "turn", "pctChg"]
        data = [
            ["2026-02-22", "10.0", "10.5", "9.5", "10.2", "1000000", "10000000", "1.5", "2.0"],
            ["2026-02-23", "10.2", "10.8", "10.0", "10.5", "1100000", "11000000", "1.6", "2.94"],
        ]
        mock_rs = MockResultSet(error_code="0", data=data, fields=fields)
        mock_bs.query_history_k_data_plus.return_value = mock_rs
        
        fetcher = BaoStockFetcher()
        df = fetcher.get_stock_history("000001", "2026-02-20", "2026-02-23")
        
        assert len(df) == 2
        assert "code" in df.columns
        assert df["code"].iloc[0] == "000001"
        assert df["close"].iloc[0] == 10.2

    @patch("pipeline.data.fetcher.bs")
    @patch("pipeline.data.fetcher.time.sleep")
    def test_get_stock_history_empty(self, mock_sleep, mock_bs):
        """无数据返回空 DataFrame"""
        mock_bs.login.return_value = MagicMock(error_code="0")
        mock_rs = MockResultSet(error_code="0", data=[], fields=[])
        mock_bs.query_history_k_data_plus.return_value = mock_rs
        
        fetcher = BaoStockFetcher()
        df = fetcher.get_stock_history("000001")
        
        assert df.empty

    @patch("pipeline.data.fetcher.bs")
    @patch("pipeline.data.fetcher.time.sleep")
    def test_get_stock_history_retry_on_exception(self, mock_sleep, mock_bs):
        """异常时重试"""
        mock_bs.login.return_value = MagicMock(error_code="0")
        
        # 前两次抛异常，第三次成功
        fields = ["date", "open", "high", "low", "close", "volume", "amount", "turn", "pctChg"]
        data = [["2026-02-22", "10.0", "10.5", "9.5", "10.2", "1000000", "10000000", "1.5", "2.0"]]
        mock_rs = MockResultSet(error_code="0", data=data, fields=fields)
        
        mock_bs.query_history_k_data_plus.side_effect = [
            Exception("Network error"),
            Exception("Timeout"),
            mock_rs,
        ]
        
        fetcher = BaoStockFetcher()
        df = fetcher.get_stock_history("000001")
        
        # 应该成功返回
        assert len(df) == 1
        # 应该等待了 2 次
        assert mock_sleep.call_count == 3  # 2 次重试等待 + 1 次请求间隔

    @patch("pipeline.data.fetcher.bs")
    @patch("pipeline.data.fetcher.time.sleep")
    def test_get_stock_history_max_retries_exceeded(self, mock_sleep, mock_bs):
        """超过最大重试次数返回空"""
        mock_bs.login.return_value = MagicMock(error_code="0")
        mock_bs.query_history_k_data_plus.side_effect = Exception("Persistent error")
        
        fetcher = BaoStockFetcher()
        df = fetcher.get_stock_history("000001")
        
        assert df.empty
        # 应该尝试了 3 次
        assert mock_bs.query_history_k_data_plus.call_count == 3


class TestCodeConversion:
    """测试股票代码转换"""

    @patch("pipeline.data.fetcher.bs")
    @patch("pipeline.data.fetcher.time.sleep")
    def test_sh_code_conversion(self, mock_sleep, mock_bs):
        """沪市股票代码转换"""
        mock_bs.login.return_value = MagicMock(error_code="0")
        mock_rs = MockResultSet(error_code="0", data=[], fields=[])
        mock_bs.query_history_k_data_plus.return_value = mock_rs
        
        fetcher = BaoStockFetcher()
        fetcher.get_stock_history("600000")
        
        # 应该转换为 sh.600000
        call_args = mock_bs.query_history_k_data_plus.call_args
        assert call_args[0][0] == "sh.600000"

    @patch("pipeline.data.fetcher.bs")
    @patch("pipeline.data.fetcher.time.sleep")
    def test_sz_code_conversion(self, mock_sleep, mock_bs):
        """深市股票代码转换"""
        mock_bs.login.return_value = MagicMock(error_code="0")
        mock_rs = MockResultSet(error_code="0", data=[], fields=[])
        mock_bs.query_history_k_data_plus.return_value = mock_rs
        
        fetcher = BaoStockFetcher()
        fetcher.get_stock_history("000001")
        
        # 应该转换为 sz.000001
        call_args = mock_bs.query_history_k_data_plus.call_args
        assert call_args[0][0] == "sz.000001"

