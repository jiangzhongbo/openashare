"""
回测 CLI 入口

用法:
    python -m pipeline.backtest --combination ma60_bounce_uptrend
    python -m pipeline.backtest --combination ma60_bounce_uptrend --start 2025-06-01 --end 2026-02-21
    python -m pipeline.backtest --combination ma60_bounce_uptrend --csv result.csv
"""

import argparse
import logging
import sys
import os
import time

from tqdm import tqdm

# 确保 pipeline 的父目录在路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pipeline.data.local_db import LocalDB
from pipeline.backtest.engine import BacktestEngine
from pipeline.backtest.report import print_report, export_csv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="A股组合回测")
    parser.add_argument(
        "--combination", "-c", required=True,
        help="组合 ID，如 ma60_bounce_uptrend",
    )
    parser.add_argument("--start", type=str, help="回测起始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="回测结束日期 (YYYY-MM-DD)")
    parser.add_argument(
        "--capital", type=float, default=1_000_000,
        help="初始资金（默认 1000000）",
    )
    parser.add_argument(
        "--entry-window", type=int, default=5,
        help="等待阴线入场的最大天数（默认 5）",
    )
    parser.add_argument(
        "--take-profit", type=float, default=10.0,
        help="止盈百分比（默认 10%%）",
    )
    parser.add_argument(
        "--stop-loss", type=float, default=0,
        help="止损百分比（默认 0 不设止损）",
    )
    parser.add_argument(
        "--max-hold", type=int, default=0,
        help="最大持仓天数（默认 0 不限制）",
    )
    parser.add_argument(
        "--board", type=str, default="all",
        help="板块过滤: all=全市场, main=主板+创业板, star=科创板 (默认 all)",
    )
    parser.add_argument("--csv", type=str, help="导出交易明细到 CSV 文件")
    parser.add_argument(
        "--db-path", type=str, default="pipeline/data/kline.db",
        help="本地数据库路径",
    )
    args = parser.parse_args()

    start_time = time.time()

    # 加载数据
    logger.info(f"加载本地数据库: {args.db_path}")
    db = LocalDB(args.db_path)
    info = db.get_database_info()
    logger.info(
        f"数据库: {info.get('stock_count', 0)} 只股票, "
        f"{info.get('record_count', 0)} 条记录, "
        f"最新日期: {info.get('latest_date', 'N/A')}"
    )

    logger.info("加载全市场 K 线数据...")
    all_data = db.get_all_stocks_data()
    stock_data = {
        code: group.reset_index(drop=True)
        for code, group in all_data.groupby("code")
    }
    # 板块过滤
    if args.board == "main":
        stock_data = {
            code: df for code, df in stock_data.items()
            if code.startswith(("000", "001", "002", "003", "600", "601", "603", "605", "300", "301"))
        }
        logger.info(f"过滤后（主板+创业板）: {len(stock_data)} 只股票")
    elif args.board == "star":
        stock_data = {
            code: df for code, df in stock_data.items()
            if code.startswith("688")
        }
        logger.info(f"过滤后（科创板）: {len(stock_data)} 只股票")
    else:
        logger.info(f"共 {len(stock_data)} 只股票")

    # 创建引擎
    logger.info(f"初始化回测引擎: 组合={args.combination}, 资金={args.capital:,.0f}")
    engine = BacktestEngine(
        combination_id=args.combination,
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital,
        entry_window=args.entry_window,
        take_profit_pct=args.take_profit,
        stop_loss_pct=args.stop_loss,
        max_hold_days=args.max_hold,
    )

    # 进度条
    pbar = None

    def progress_callback(current, total, phase):
        nonlocal pbar
        if pbar is None:
            pbar = tqdm(total=total, desc="检测信号")
        pbar.update(1)

    # 运行回测
    result = engine.run(stock_data, progress_callback=progress_callback)

    if pbar:
        pbar.close()

    duration = time.time() - start_time
    logger.info(f"回测完成，耗时 {duration:.1f} 秒")

    # 输出报告
    print_report(result)

    # 导出 CSV
    if args.csv:
        export_csv(result, args.csv)


if __name__ == "__main__":
    main()
