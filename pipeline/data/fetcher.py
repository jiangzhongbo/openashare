"""
数据获取模块 - 使用 BaoStock（免费、稳定）
- 获取 A 股股票列表
- 获取历史 K 线数据（含 turn/pct_chg）
"""

import time
import baostock as bs
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Callable
import logging

logger = logging.getLogger(__name__)


class BaoStockFetcher:
    """BaoStock 数据获取器"""

    # 请求间隔（秒），避免被限速
    REQUEST_INTERVAL = 0.1
    # 最大重试次数
    MAX_RETRIES = 3
    # 重试等待时间（秒）
    RETRY_WAIT = 2

    def __init__(self):
        self.logged_in = False
        self._login()

    def _login(self):
        """登录 BaoStock"""
        try:
            lg = bs.login()
            if lg.error_code == "0":
                self.logged_in = True
                logger.info("BaoStock 登录成功")
            else:
                logger.error(f"BaoStock 登录失败: {lg.error_msg}")
        except Exception as e:
            logger.error(f"BaoStock 登录异常: {e}")

    def logout(self):
        """主动登出 BaoStock（仅在程序结束时手动调用）"""
        if self.logged_in:
            try:
                bs.logout()
                self.logged_in = False
            except Exception:
                pass

    def _ensure_login(self):
        """确保已登录"""
        if not self.logged_in:
            self._login()

    def get_stock_list(self) -> pd.DataFrame:
        """
        获取 A 股股票列表

        Returns:
            股票列表 DataFrame，包含 code, name, bs_code 列
        """
        self._ensure_login()

        try:
            logger.info("正在获取股票列表...")
            rs = bs.query_stock_basic()
            data_list = []

            while rs.error_code == "0" and rs.next():
                try:
                    data_list.append(rs.get_row_data())
                except Exception:
                    continue

            if not data_list:
                logger.error("未获取到任何股票数据")
                return pd.DataFrame()

            df = pd.DataFrame(data_list, columns=rs.fields)

            # 只保留 A 股（type=1 表示股票）
            df = df[df["type"] == "1"]

            # 标准化列名
            df["code"] = df["code"].str.replace("sh.", "", regex=False).str.replace("sz.", "", regex=False)
            df["name"] = df["code_name"]
            df["bs_code"] = df.apply(
                lambda row: f"sh.{row['code']}" if row["code"].startswith("6") else f"sz.{row['code']}",
                axis=1,
            )

            total_before = len(df)

            # 过滤退市股（status=0）
            if "status" in df.columns:
                delisted = df[df["status"] == "0"]
                if len(delisted) > 0:
                    logger.info(f"过滤退市股: {len(delisted)} 只")
                df = df[df["status"] == "1"]

            # 过滤北交所（代码以 4/8 开头，BaoStock 不支持）
            bj_mask = df["code"].str.startswith("4") | df["code"].str.startswith("8")
            bj_count = bj_mask.sum()
            if bj_count > 0:
                logger.info(f"过滤北交所: {bj_count} 只（BaoStock 不支持）")
            df = df[~bj_mask]

            logger.info(f"成功获取股票列表，共 {len(df)} 只（原始 {total_before}，过滤 {total_before - len(df)}）")
            return df[["code", "name", "bs_code"]]

        except Exception as e:
            logger.error(f"获取股票列表失败: {e}")
            return pd.DataFrame()

    def get_stock_history(
        self,
        code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adjust: str = "2",
    ) -> pd.DataFrame:
        """
        获取股票历史 K 线数据

        Args:
            code: 股票代码（如 "000001" 或 "sh.600000"）
            start_date: 开始日期 (格式: "2024-01-01")
            end_date: 结束日期 (格式: "2024-02-01")
            adjust: 复权类型 ("1"-后复权, "2"-前复权, "3"-不复权)

        Returns:
            历史 K 线 DataFrame
        """
        self._ensure_login()

        # 处理股票代码格式
        if not code.startswith("sh.") and not code.startswith("sz."):
            bs_code = f"sh.{code}" if code.startswith("6") else f"sz.{code}"
        else:
            bs_code = code

        # 默认日期
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")

        for attempt in range(self.MAX_RETRIES):
            try:
                rs = bs.query_history_k_data_plus(
                    bs_code,
                    "date,open,high,low,close,volume,amount,turn,pctChg",
                    start_date=start_date,
                    end_date=end_date,
                    frequency="d",
                    adjustflag=adjust,
                )

                data_list = []
                while rs.error_code == "0" and rs.next():
                    data_list.append(rs.get_row_data())

                if not data_list:
                    logger.debug(f"股票 {code} 无历史数据")
                    return pd.DataFrame()

                df = pd.DataFrame(data_list, columns=rs.fields)
                df["code"] = code.replace("sh.", "").replace("sz.", "")

                # 数据类型转换
                df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
                for col in ["open", "high", "low", "close", "volume", "amount"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                # turn 和 pctChg 可能为空字符串
                df["turn"] = pd.to_numeric(df["turn"], errors="coerce")
                df["pct_chg"] = pd.to_numeric(df["pctChg"], errors="coerce")

                # 选择需要的列
                result_cols = ["code", "date", "open", "high", "low", "close", "volume", "amount", "turn", "pct_chg"]
                df = df[result_cols]

                time.sleep(self.REQUEST_INTERVAL)
                return df

            except Exception as e:
                logger.warning(f"获取 {code} 数据失败 (尝试 {attempt + 1}/{self.MAX_RETRIES}): {e}")
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_WAIT)
                else:
                    logger.error(f"获取 {code} 数据最终失败")
                    return pd.DataFrame()

        return pd.DataFrame()

    def fetch_all_stocks(
        self,
        stock_list: pd.DataFrame,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> pd.DataFrame:
        """
        批量获取所有股票数据

        Args:
            stock_list: 股票列表 DataFrame（需含 code 列）
            start_date: 开始日期
            end_date: 结束日期
            progress_callback: 进度回调函数 (current, total, code)

        Returns:
            所有股票 K 线数据 DataFrame
        """
        all_data = []
        total = len(stock_list)

        for idx, row in stock_list.iterrows():
            code = row["code"]

            if progress_callback:
                progress_callback(idx + 1, total, code)

            df = self.get_stock_history(code, start_date, end_date)
            if not df.empty:
                all_data.append(df)

        if not all_data:
            return pd.DataFrame()

        return pd.concat(all_data, ignore_index=True)

