"""
本地 SQLite 缓存层
- 存储原始 K 线数据（OHLCV + turn + pct_chg）
- 滚动保留最近 250 个交易日
- 支持 GitHub Actions Cache 断点续传
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict
import pandas as pd


class LocalDB:
    """本地 SQLite 数据库管理器"""

    # 默认保留天数（约 1 年交易日）
    RETENTION_DAYS = 250

    def __init__(self, db_path: str = "data/local_kline.db"):
        """
        初始化数据库

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接"""
        return sqlite3.connect(self.db_path)

    def _init_schema(self):
        """初始化数据库 Schema"""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_kline (
                    code    TEXT NOT NULL,
                    date    TEXT NOT NULL,
                    open    REAL,
                    high    REAL,
                    low     REAL,
                    close   REAL,
                    volume  REAL,
                    amount  REAL,
                    turn    REAL,
                    pct_chg REAL,
                    PRIMARY KEY (code, date)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kline_date ON daily_kline(date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kline_code ON daily_kline(code)")
            conn.commit()

    def upsert_kline(self, df: pd.DataFrame) -> int:
        """
        插入或更新 K 线数据（upsert）

        Args:
            df: K 线数据 DataFrame，需包含 code, date, open, high, low, close, volume, amount, turn, pct_chg

        Returns:
            插入/更新的行数
        """
        if df.empty:
            return 0

        required_cols = ["code", "date", "open", "high", "low", "close", "volume", "amount", "turn", "pct_chg"]
        for col in required_cols:
            if col not in df.columns:
                df[col] = None

        sql = """
            INSERT OR REPLACE INTO daily_kline
            (code, date, open, high, low, close, volume, amount, turn, pct_chg)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        rows = df[required_cols].values.tolist()
        with self._get_conn() as conn:
            conn.executemany(sql, rows)
            conn.commit()

        return len(df)

    def upsert_kline_batch(self, df: pd.DataFrame, batch_size: int = 500) -> int:
        """
        批量 upsert K 线数据

        Args:
            df: K 线数据 DataFrame
            batch_size: 批次大小

        Returns:
            插入/更新的行数
        """
        if df.empty:
            return 0

        required_cols = ["code", "date", "open", "high", "low", "close", "volume", "amount", "turn", "pct_chg"]
        for col in required_cols:
            if col not in df.columns:
                df[col] = None

        sql = """
            INSERT OR REPLACE INTO daily_kline 
            (code, date, open, high, low, close, volume, amount, turn, pct_chg)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        rows = df[required_cols].values.tolist()
        total = 0

        with self._get_conn() as conn:
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                conn.executemany(sql, batch)
                total += len(batch)
            conn.commit()

        return total

    def cleanup_old_data(self, keep_days: int = RETENTION_DAYS) -> int:
        """
        清理超过保留期的数据

        Args:
            keep_days: 保留最近多少个交易日

        Returns:
            删除的行数
        """
        with self._get_conn() as conn:
            # 找出最近 keep_days 个交易日的日期边界
            cursor = conn.execute("""
                SELECT DISTINCT date FROM daily_kline ORDER BY date DESC LIMIT ?
            """, (keep_days,))
            recent_dates = [row[0] for row in cursor.fetchall()]

            if not recent_dates:
                return 0

            cutoff_date = min(recent_dates)

            # 删除早于截止日期的数据
            cursor = conn.execute("""
                DELETE FROM daily_kline WHERE date < ?
            """, (cutoff_date,))
            deleted = cursor.rowcount
            conn.commit()

        return deleted

    def get_latest_date(self) -> Optional[str]:
        """获取数据库中最新的日期"""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT MAX(date) FROM daily_kline")
            result = cursor.fetchone()
            return result[0] if result and result[0] else None

    def get_stock_latest_date(self, code: str) -> Optional[str]:
        """获取单只股票的最新数据日期"""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT MAX(date) FROM daily_kline WHERE code = ?", (code,)
            )
            result = cursor.fetchone()
            return result[0] if result and result[0] else None

    def get_all_stocks_latest_date(self) -> Dict[str, str]:
        """获取所有股票的最新数据日期"""
        with self._get_conn() as conn:
            cursor = conn.execute("""
                SELECT code, MAX(date) as latest_date
                FROM daily_kline
                GROUP BY code
            """)
            return {row[0]: row[1] for row in cursor.fetchall()}

    def get_stock_history(self, code: str, days: int = 300) -> pd.DataFrame:
        """
        获取单只股票历史数据

        Args:
            code: 股票代码
            days: 获取最近多少天

        Returns:
            历史数据 DataFrame
        """
        with self._get_conn() as conn:
            df = pd.read_sql(
                """
                SELECT * FROM daily_kline
                WHERE code = ?
                ORDER BY date DESC
                LIMIT ?
                """,
                conn,
                params=(code, days),
            )
        return df.sort_values("date").reset_index(drop=True)

    def get_all_stocks_data(self, min_days: int = 60) -> pd.DataFrame:
        """
        获取所有股票的数据（用于筛选）

        Args:
            min_days: 最少需要多少天数据

        Returns:
            所有股票数据 DataFrame
        """
        with self._get_conn() as conn:
            df = pd.read_sql(
                "SELECT * FROM daily_kline ORDER BY code, date",
                conn,
            )
        return df

    def get_stock_count(self) -> int:
        """获取股票数量"""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT COUNT(DISTINCT code) FROM daily_kline")
            return cursor.fetchone()[0]

    def get_record_count(self) -> int:
        """获取记录总数"""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM daily_kline")
            return cursor.fetchone()[0]

    def get_database_info(self) -> dict:
        """获取数据库信息"""
        if not self.db_path.exists():
            return {"exists": False, "path": str(self.db_path)}

        return {
            "exists": True,
            "path": str(self.db_path),
            "size_mb": round(self.db_path.stat().st_size / 1024 / 1024, 2),
            "stock_count": self.get_stock_count(),
            "record_count": self.get_record_count(),
            "latest_date": self.get_latest_date(),
        }

