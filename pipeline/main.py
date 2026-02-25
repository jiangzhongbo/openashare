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
from pipeline.backtest.engine import BacktestEngine

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
        target_dt = datetime.strptime(target_date, "%Y-%m-%d")

        # 3b-2. 预分类：统计各类股票数量
        STALE_THRESHOLD = 30  # 超过 30 天未更新视为停牌/退市，跳过
        stock_codes = set(row.code for row in stocks.itertuples(index=False))
        up_to_date = []   # 已是最新
        need_update = []  # 正常增量（gap <= 30天）
        stale = []        # 停牌/退市（gap > 30天）
        not_in_db = []    # 不在 DB 中（新股/从未下载）

        for code in stock_codes:
            latest = latest_dates.get(code)
            if latest is None:
                not_in_db.append(code)
            elif latest >= target_date:
                up_to_date.append(code)
            else:
                gap = (target_dt - datetime.strptime(latest, "%Y-%m-%d")).days
                if gap > STALE_THRESHOLD:
                    stale.append((code, latest, gap))
                else:
                    need_update.append((code, latest, gap))

        # 打印数据库统计报告
        logger.info(f"{'='*60}")
        logger.info(f"数据库统计报告（目标日期: {target_date}）")
        logger.info(f"{'='*60}")
        logger.info(f"  股票列表总数:   {len(stock_codes)}")
        logger.info(f"  已是最新:       {len(up_to_date)} 只（无需下载）")
        logger.info(f"  正常增量:       {len(need_update)} 只（gap ≤ {STALE_THRESHOLD}天）")
        logger.info(f"  停牌/退市:      {len(stale)} 只（gap > {STALE_THRESHOLD}天，跳过）")
        logger.info(f"  不在DB中:       {len(not_in_db)} 只（全量下载）")
        logger.info(f"  需要下载:       {len(need_update) + len(not_in_db)} 只")
        logger.info(f"{'='*60}")

        # 如果没有需要下载的，直接跳过
        total_to_fetch = len(need_update) + len(not_in_db)
        if total_to_fetch == 0:
            logger.info("所有股票已是最新或为停牌股，跳过下载步骤")
            stats = {"skipped": len(up_to_date), "incremental": 0, "full": 0, "stale_skipped": len(stale), "failed": 0}
        else:
            # 构建下载任务列表（只包含需要下载的股票）
            full_start_date = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
            stats = {"skipped": len(up_to_date), "incremental": 0, "full": 0, "stale_skipped": len(stale), "failed": 0}

            # 构建任务：(code, start_date, label)
            tasks = []
            for code, latest, gap in need_update:
                start = (datetime.strptime(latest, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
                tasks.append((code, start, f"增量{gap}天"))
            for code in not_in_db:
                tasks.append((code, full_start_date, "全量"))

            # 3c. 遍历需要下载的股票，带 tqdm 进度条
            pbar = tqdm(tasks, total=len(tasks), desc="下载K线")
            for code, start, label in pbar:
                pbar.set_postfix_str(f"{code} {label}")

                if "增量" in label:
                    stats["incremental"] += 1
                else:
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
            f"下载完成 — 已最新: {stats['skipped']}  增量: {stats['incremental']}  "
            f"全量: {stats['full']}  停牌跳过: {stats['stale_skipped']}  失败: {stats['failed']}"
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

        # 5b. 回测各组合，附加绩效摘要
        logger.info("运行组合回测...")
        for combo in combinations:
            try:
                engine = BacktestEngine(
                    combination=combo,
                    factors=[screener.factor_map[fid] for fid in combo.factors],
                    initial_capital=1_000_000,
                    entry_window=5,
                    take_profit_pct=10.0,
                    max_hold_days=15,
                )
                bt_result = engine.run(stock_data, stock_names=stock_names)
                combo.backtest_summary = {
                    **bt_result.metrics,
                    "start_date": bt_result.start_date,
                    "end_date": bt_result.end_date,
                    "updated_at": run_date,
                }
                logger.info(
                    f"  回测 {combo.id}: 总收益={bt_result.metrics.get('total_return_pct', '-')}%  "
                    f"胜率={bt_result.metrics.get('win_rate_pct', '-')}%  "
                    f"交易={bt_result.metrics.get('total_trades', 0)}笔"
                )
            except Exception as e:
                logger.warning(f"  回测 {combo.id} 失败（不影响筛选）: {e}")

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
                        factor = FACTOR_MAP.get(fid)
                        factor_label = factor.label if factor else fid
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
    finally:
        fetcher.logout()


if __name__ == "__main__":
    main()

