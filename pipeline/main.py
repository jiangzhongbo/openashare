#!/usr/bin/env python3
"""
A股选股工具 - 主入口脚本

功能：
1. 获取全市场股票列表
2. 下载/更新 K 线数据到本地 SQLite
3. 运行因子筛选
4. 上传结果到 CF Worker

用法：
    python main.py                    # 正常运行
    python main.py --dry-run          # 只筛选，不上传
    python main.py --date 2026-02-23  # 指定日期
"""

import argparse
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta
from tqdm import tqdm

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.data.fetcher import BaoStockFetcher
from pipeline.data.local_db import LocalDB
from pipeline.factors.registry import get_all_factors, get_all_combinations
from pipeline.screening.screener import Screener
from pipeline.sync.worker_client import WorkerClient

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_trading_date() -> str:
    """获取当前交易日期（简单版本：使用当天日期）"""
    return date.today().strftime("%Y-%m-%d")


def main():
    parser = argparse.ArgumentParser(description="A股选股工具")
    parser.add_argument("--dry-run", action="store_true", help="只筛选不上传")
    parser.add_argument("--date", type=str, help="指定运行日期 (YYYY-MM-DD)")
    parser.add_argument("--db-path", type=str, default="data/kline.db", help="本地数据库路径")
    args = parser.parse_args()

    run_date = args.date or get_trading_date()
    logger.info(f"开始运行，日期: {run_date}")

    start_time = time.time()

    try:
        # 1. 初始化组件
        logger.info("初始化组件...")
        db = LocalDB(args.db_path)
        fetcher = BaoStockFetcher()
        factors = get_all_factors()
        combinations = get_all_combinations()
        screener = Screener(factors=factors, combinations=combinations)

        # 2. 获取股票列表
        logger.info("获取股票列表...")
        stocks = fetcher.get_stock_list()
        logger.info(f"共 {len(stocks)} 只股票")

        # 3. 下载/更新 K 线数据（增量）
        logger.info("下载 K 线数据（增量更新）...")

        # 3a. 用 000001 探测数据源实际最新日期（避免当天数据未出来）
        logger.info("检测数据源最新日期（基准：000001 平安银行）...")
        probe_df = fetcher.get_stock_history(
            "000001",
            start_date=(datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
        )
        if probe_df is not None and not probe_df.empty:
            target_date = probe_df["date"].max()
            logger.info(f"数据源最新日期: {target_date}")
        else:
            target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            logger.warning(f"无法探测数据源日期，使用昨天: {target_date}")

        # 3b. 查询 DB 中每只股票已有的最新日期（一次查询）
        latest_dates = db.get_all_stocks_latest_date()

        # 3b-2. 检查有多少股票已经是最新日期
        up_to_date_count = sum(1 for date in latest_dates.values() if date >= target_date)
        total_in_db = len(latest_dates)
        logger.info(f"本地数据库状态: {up_to_date_count}/{total_in_db} 只股票已是最新 ({target_date})")

        # 如果超过 95% 的股票都是最新的，跳过下载
        if total_in_db > 0 and up_to_date_count / total_in_db > 0.95:
            logger.info(f"本地数据已基本最新（{up_to_date_count}/{total_in_db} = {up_to_date_count/total_in_db*100:.1f}%），跳过下载步骤")
            stats = {"skipped": len(stocks), "incremental": 0, "full": 0, "failed": 0}
            logger.info(
                f"下载完成 — 跳过: {stats['skipped']}  增量: {stats['incremental']}  "
                f"全量: {stats['full']}  失败: {stats['failed']}"
            )
        else:
            # 需要下载
            full_start_date = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
            stats = {"skipped": 0, "incremental": 0, "full": 0, "failed": 0}

            # 3c. 遍历所有股票，带 tqdm 进度条
            for row in tqdm(stocks.itertuples(index=False), total=len(stocks), desc="下载K线"):
                code = row.code
                latest = latest_dates.get(code)

                if latest is not None and latest >= target_date:
                    # 已是最新，跳过
                    stats["skipped"] += 1
                    continue
                elif latest is not None:
                    # 有数据但不是最新，只补缺口
                    start = (
                        datetime.strptime(latest, "%Y-%m-%d") + timedelta(days=1)
                    ).strftime("%Y-%m-%d")
                    stats["incremental"] += 1
                else:
                    # 完全没有数据，全量下载
                    start = full_start_date
                    stats["full"] += 1

                try:
                    df = fetcher.get_stock_history(code, start_date=start, end_date=target_date)
                    if df is not None and not df.empty:
                        db.upsert_kline_batch(df)
                    else:
                        stats["failed"] += 1
                except Exception as e:
                    logger.warning(f"下载失败 {code}: {e}")
                    stats["failed"] += 1

            logger.info(
                f"下载完成 — 跳过: {stats['skipped']}  增量: {stats['incremental']}  "
                f"全量: {stats['full']}  失败: {stats['failed']}"
            )

        # 4. 清理旧数据
        logger.info("清理旧数据（保留 250 天）...")
        deleted = db.cleanup_old_data(keep_days=250)
        logger.info(f"删除 {deleted} 条旧数据")

        # 5. 加载数据并运行筛选
        logger.info("加载数据并运行筛选...")
        stock_data_df = db.get_all_stocks_data()
        stock_data = {
            code: group.reset_index(drop=True)
            for code, group in stock_data_df.groupby("code")
        }
        logger.info(f"加载 {len(stock_data)} 只股票的历史数据")

        # 创建股票代码到名称的映射
        stock_names = {row['code']: row['name'] for _, row in stocks.iterrows()}

        def progress_callback(current, total, code):
            if current % 1000 == 0:
                logger.info(f"筛选进度: {current}/{total}")

        report = screener.screen_all(
            stock_data,
            run_date=run_date,
            stock_names=stock_names,
            progress_callback=progress_callback
        )

        logger.info(f"筛选完成: 共 {report.total_stocks} 只，通过 {len(report.results)} 只")
        for combo_id, count in report.combination_counts.items():
            logger.info(f"  - {combo_id}: {count} 只")

        # 6. 上传结果
        if args.dry_run:
            logger.info("Dry run 模式，跳过上传")
            # 打印详细结果
            if report.results:
                logger.info(f"\n{'='*60}")
                logger.info("筛选结果详情:")
                logger.info(f"{'='*60}")
                from pipeline.factors.registry import FACTOR_MAP
                for r in report.results:
                    logger.info(f"\n股票: {r.code} | 组合: {r.combination}")
                    for fid, value in r.factor_values.items():
                        factor_label = FACTOR_MAP.get(fid, {}).get("label", fid)
                        logger.info(f"  - {factor_label}: {value}")
                logger.info(f"\n{'='*60}")
            else:
                logger.info("无股票通过筛选")
        else:
            logger.info("上传结果到 Worker...")
            client = WorkerClient()

            if not client.health_check():
                logger.error("Worker 不可用，跳过上传")
            else:
                result = client.ingest(report)
                if result.success:
                    logger.info(f"上传成功: 插入 {result.data.get('inserted', 0)} 条记录")
                else:
                    logger.error(f"上传失败: {result.message}")

        # 7. 完成
        duration = time.time() - start_time
        logger.info(f"运行完成，耗时 {duration:.1f} 秒")

    except Exception as e:
        logger.exception(f"运行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

