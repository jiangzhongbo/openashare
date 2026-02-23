"""
Layer 1 单元测试 - LocalDB
测试写入/清理/upsert 逻辑
"""

import pytest
import pandas as pd
import tempfile
import os
from pathlib import Path

from pipeline.data.local_db import LocalDB


@pytest.fixture
def temp_db():
    """创建临时数据库"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = LocalDB(db_path)
        yield db


@pytest.fixture
def sample_kline_df():
    """创建样本 K 线数据"""
    return pd.DataFrame({
        "code": ["000001", "000001", "000001", "000002", "000002"],
        "date": ["2026-02-20", "2026-02-21", "2026-02-22", "2026-02-21", "2026-02-22"],
        "open": [10.0, 10.5, 11.0, 20.0, 20.5],
        "high": [10.5, 11.0, 11.5, 20.5, 21.0],
        "low": [9.5, 10.0, 10.5, 19.5, 20.0],
        "close": [10.2, 10.8, 11.2, 20.3, 20.8],
        "volume": [1000000, 1100000, 1200000, 2000000, 2100000],
        "amount": [10000000, 11000000, 12000000, 40000000, 42000000],
        "turn": [1.5, 1.6, 1.7, 2.0, 2.1],
        "pct_chg": [1.0, 5.88, 3.7, 0.5, 2.46],
    })


class TestLocalDBInit:
    """测试初始化"""

    def test_init_creates_db_file(self, temp_db):
        """初始化后数据库文件应存在"""
        assert temp_db.db_path.exists()

    def test_init_creates_schema(self, temp_db):
        """初始化后表应存在"""
        with temp_db._get_conn() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='daily_kline'"
            )
            assert cursor.fetchone() is not None


class TestUpsertKline:
    """测试 upsert 操作"""

    def test_upsert_empty_df(self, temp_db):
        """空 DataFrame 应返回 0"""
        df = pd.DataFrame()
        assert temp_db.upsert_kline_batch(df) == 0

    def test_upsert_batch_inserts_data(self, temp_db, sample_kline_df):
        """批量插入应写入数据"""
        count = temp_db.upsert_kline_batch(sample_kline_df)
        assert count == 5
        assert temp_db.get_record_count() == 5

    def test_upsert_replaces_existing(self, temp_db, sample_kline_df):
        """重复插入应替换（不重复）"""
        temp_db.upsert_kline_batch(sample_kline_df)
        
        # 修改数据后再次插入
        df2 = sample_kline_df.copy()
        df2["close"] = df2["close"] + 1.0
        temp_db.upsert_kline_batch(df2)
        
        # 总数应不变
        assert temp_db.get_record_count() == 5
        
        # 检查数据已更新
        history = temp_db.get_stock_history("000001", days=10)
        assert history[history["date"] == "2026-02-22"]["close"].values[0] == 12.2

    def test_upsert_handles_missing_columns(self, temp_db):
        """缺少列应自动补 None"""
        df = pd.DataFrame({
            "code": ["000001"],
            "date": ["2026-02-20"],
            "close": [10.0],
        })
        count = temp_db.upsert_kline_batch(df)
        assert count == 1


class TestCleanupOldData:
    """测试数据清理"""

    def test_cleanup_removes_old_data(self, temp_db):
        """清理应删除旧数据"""
        # 插入跨越 10 天的数据
        dates = [f"2026-02-{i:02d}" for i in range(10, 22)]
        df = pd.DataFrame({
            "code": ["000001"] * len(dates),
            "date": dates,
            "close": [10.0] * len(dates),
        })
        temp_db.upsert_kline_batch(df)
        assert temp_db.get_record_count() == 12
        
        # 只保留最近 5 天
        deleted = temp_db.cleanup_old_data(keep_days=5)
        assert deleted == 7
        assert temp_db.get_record_count() == 5

    def test_cleanup_empty_db(self, temp_db):
        """空数据库清理应返回 0"""
        deleted = temp_db.cleanup_old_data()
        assert deleted == 0


class TestQueryMethods:
    """测试查询方法"""

    def test_get_latest_date(self, temp_db, sample_kline_df):
        """获取最新日期"""
        temp_db.upsert_kline_batch(sample_kline_df)
        assert temp_db.get_latest_date() == "2026-02-22"

    def test_get_latest_date_empty(self, temp_db):
        """空数据库返回 None"""
        assert temp_db.get_latest_date() is None

    def test_get_stock_latest_date(self, temp_db, sample_kline_df):
        """获取单股最新日期"""
        temp_db.upsert_kline_batch(sample_kline_df)
        assert temp_db.get_stock_latest_date("000001") == "2026-02-22"
        assert temp_db.get_stock_latest_date("000002") == "2026-02-22"
        assert temp_db.get_stock_latest_date("999999") is None

    def test_get_all_stocks_latest_date(self, temp_db, sample_kline_df):
        """获取所有股票最新日期"""
        temp_db.upsert_kline_batch(sample_kline_df)
        result = temp_db.get_all_stocks_latest_date()
        assert result == {"000001": "2026-02-22", "000002": "2026-02-22"}

    def test_get_stock_history(self, temp_db, sample_kline_df):
        """获取单股历史数据"""
        temp_db.upsert_kline_batch(sample_kline_df)
        history = temp_db.get_stock_history("000001", days=10)
        assert len(history) == 3
        # 应按日期升序
        assert history["date"].tolist() == ["2026-02-20", "2026-02-21", "2026-02-22"]

    def test_get_all_stocks_data(self, temp_db, sample_kline_df):
        """获取所有股票数据"""
        temp_db.upsert_kline_batch(sample_kline_df)
        df = temp_db.get_all_stocks_data()
        assert len(df) == 5
        assert set(df["code"].unique()) == {"000001", "000002"}

    def test_get_stock_count(self, temp_db, sample_kline_df):
        """获取股票数量"""
        temp_db.upsert_kline_batch(sample_kline_df)
        assert temp_db.get_stock_count() == 2

    def test_get_database_info(self, temp_db, sample_kline_df):
        """获取数据库信息"""
        temp_db.upsert_kline_batch(sample_kline_df)
        info = temp_db.get_database_info()
        assert info["exists"] is True
        assert info["stock_count"] == 2
        assert info["record_count"] == 5
        assert info["latest_date"] == "2026-02-22"

