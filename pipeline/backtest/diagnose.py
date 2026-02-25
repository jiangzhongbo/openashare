"""
回测诊断工具

分离分析信号质量 vs 入场/出场策略的影响。
"""

import argparse
import logging
import sys
import os
import time
from typing import Dict, List, Tuple
from collections import defaultdict

import pandas as pd
import numpy as np
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pipeline.data.local_db import LocalDB
from pipeline.factors.base import Factor, FactorResult, calculate_ma
from pipeline.factors.registry import get_combination, get_factor
from pipeline.backtest.engine import BacktestEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def analyze_signal_quality(
    signals: Dict[str, List[Tuple[str, str]]],
    stock_data: Dict[str, pd.DataFrame],
    forward_days: List[int] = [1, 3, 5, 10, 20],
):
    """
    分析信号前瞻收益：信号触发后 N 天的股价变化

    回答问题：信号选出的股票，后续到底涨不涨？
    """
    print()
    print("=" * 60)
    print("  诊断 1：信号前瞻收益（信号本身好不好？）")
    print("=" * 60)

    # 构建 date-indexed 数据
    indexed: Dict[str, pd.DataFrame] = {}
    for code, df in stock_data.items():
        df = df.sort_values("date").reset_index(drop=True)
        indexed[code] = df

    # 统计每个前瞻期的收益
    results = {d: [] for d in forward_days}
    total_signals = 0

    for date, stocks in signals.items():
        for code, name in stocks:
            if code not in indexed:
                continue
            df = indexed[code]
            dates_list = df["date"].tolist()
            if date not in dates_list:
                continue
            idx = dates_list.index(date)
            signal_close = df.iloc[idx]["close"]

            for d in forward_days:
                future_idx = idx + d
                if future_idx < len(df):
                    future_close = df.iloc[future_idx]["close"]
                    ret = (future_close - signal_close) / signal_close * 100
                    results[d].append(ret)

            total_signals += 1

    print(f"\n  信号总数: {total_signals}")
    print()
    print(f"  {'持有天数':>8}  {'平均收益':>8}  {'中位收益':>8}  {'胜率':>8}  {'样本数':>6}")
    print(f"  {'-' * 8}  {'-' * 8}  {'-' * 8}  {'-' * 8}  {'-' * 6}")

    for d in forward_days:
        if not results[d]:
            continue
        arr = np.array(results[d])
        mean_ret = np.mean(arr)
        median_ret = np.median(arr)
        win_rate = np.sum(arr > 0) / len(arr) * 100
        sign = "+" if mean_ret >= 0 else ""
        sign_m = "+" if median_ret >= 0 else ""
        print(
            f"  {d:>6}天  {sign}{mean_ret:>7.2f}%  {sign_m}{median_ret:>7.2f}%  "
            f"{win_rate:>7.1f}%  {len(arr):>6}"
        )

    print()
    if results[5]:
        arr5 = np.array(results[5])
        print(f"  5天收益分布:")
        for pct in [10, 25, 50, 75, 90]:
            val = np.percentile(arr5, pct)
            sign = "+" if val >= 0 else ""
            print(f"    P{pct:>2}: {sign}{val:.2f}%")

    print()


def analyze_entry_strategy(
    signals: Dict[str, List[Tuple[str, str]]],
    stock_data: Dict[str, pd.DataFrame],
):
    """
    分析入场策略影响：阴线入场 vs 信号次日直接买入

    回答问题：等阴线是帮了忙还是帮了倒忙？
    """
    print()
    print("=" * 60)
    print("  诊断 2：入场策略对比（阴线入场 vs 次日直接买入）")
    print("=" * 60)

    indexed: Dict[str, pd.DataFrame] = {}
    for code, df in stock_data.items():
        indexed[code] = df.sort_values("date").reset_index(drop=True)

    hold_days = 10  # 统一用 10 天持有来对比入场方式

    # 策略 A：次日开盘直接买入
    strategy_a_returns = []
    # 策略 B：等阴线入场（5天窗口）
    strategy_b_returns = []
    # 策略 C：信号当日收盘买入
    strategy_c_returns = []

    for date, stocks in signals.items():
        for code, name in stocks:
            if code not in indexed:
                continue
            df = indexed[code]
            dates_list = df["date"].tolist()
            if date not in dates_list:
                continue
            idx = dates_list.index(date)

            # 策略 A：次日开盘买入，持有 hold_days 天
            if idx + 1 < len(df) and idx + 1 + hold_days < len(df):
                buy_price = df.iloc[idx + 1]["open"]
                sell_price = df.iloc[idx + 1 + hold_days]["close"]
                if buy_price > 0:
                    strategy_a_returns.append(
                        (sell_price - buy_price) / buy_price * 100
                    )

            # 策略 B：5天内等阴线，阴线收盘买入
            for offset in range(1, 6):
                entry_idx = idx + offset
                if entry_idx >= len(df):
                    break
                row = df.iloc[entry_idx]
                if row["close"] < row["open"]:  # 阴线
                    buy_price = row["close"]
                    sell_idx = entry_idx + hold_days
                    if sell_idx < len(df) and buy_price > 0:
                        sell_price = df.iloc[sell_idx]["close"]
                        strategy_b_returns.append(
                            (sell_price - buy_price) / buy_price * 100
                        )
                    break

            # 策略 C：信号当日收盘买入
            if idx + hold_days < len(df):
                buy_price = df.iloc[idx]["close"]
                sell_price = df.iloc[idx + hold_days]["close"]
                if buy_price > 0:
                    strategy_c_returns.append(
                        (sell_price - buy_price) / buy_price * 100
                    )

    print(f"\n  统一持有 {hold_days} 天，对比不同入场方式:\n")
    print(f"  {'入场方式':<20}  {'平均收益':>8}  {'中位收益':>8}  {'胜率':>8}  {'样本':>5}")
    print(f"  {'-' * 20}  {'-' * 8}  {'-' * 8}  {'-' * 8}  {'-' * 5}")

    for label, rets in [
        ("信号当日收盘买入", strategy_c_returns),
        ("信号次日开盘买入", strategy_a_returns),
        ("等阴线收盘买入", strategy_b_returns),
    ]:
        if not rets:
            print(f"  {label:<20}  {'N/A':>8}  {'N/A':>8}  {'N/A':>8}  {0:>5}")
            continue
        arr = np.array(rets)
        mean_r = np.mean(arr)
        median_r = np.median(arr)
        wr = np.sum(arr > 0) / len(arr) * 100
        sign = "+" if mean_r >= 0 else ""
        sign_m = "+" if median_r >= 0 else ""
        print(
            f"  {label:<20}  {sign}{mean_r:>7.2f}%  {sign_m}{median_r:>7.2f}%  "
            f"{wr:>7.1f}%  {len(arr):>5}"
        )

    print()


def analyze_exit_strategy(
    signals: Dict[str, List[Tuple[str, str]]],
    stock_data: Dict[str, pd.DataFrame],
):
    """
    分析出场策略影响：MA10 出场 vs 固定持有天数

    回答问题：MA10 出场是太早了还是太晚了？
    """
    print()
    print("=" * 60)
    print("  诊断 3：出场策略对比（MA10 vs 固定持有天数）")
    print("=" * 60)

    indexed: Dict[str, pd.DataFrame] = {}
    for code, df in stock_data.items():
        df = df.sort_values("date").reset_index(drop=True)
        df["ma10"] = calculate_ma(df, 10)
        indexed[code] = df

    hold_periods = [3, 5, 10, 15, 20]

    # 收集所有入场点（统一用次日开盘买入）
    entries = []
    for date, stocks in signals.items():
        for code, name in stocks:
            if code not in indexed:
                continue
            df = indexed[code]
            dates_list = df["date"].tolist()
            if date not in dates_list:
                continue
            idx = dates_list.index(date)
            if idx + 1 < len(df):
                entry_idx = idx + 1
                entry_price = df.iloc[entry_idx]["open"]
                if entry_price > 0:
                    entries.append((code, entry_idx, entry_price))

    # 策略 A：固定持有
    fixed_results = {d: [] for d in hold_periods}
    for code, entry_idx, entry_price in entries:
        df = indexed[code]
        for d in hold_periods:
            exit_idx = entry_idx + d
            if exit_idx < len(df):
                exit_price = df.iloc[exit_idx]["close"]
                ret = (exit_price - entry_price) / entry_price * 100
                fixed_results[d].append(ret)

    # 策略 B：MA10 出场（最多持有 30 天）
    ma10_returns = []
    ma10_hold_days = []
    for code, entry_idx, entry_price in entries:
        df = indexed[code]
        for offset in range(1, 31):
            exit_idx = entry_idx + offset
            if exit_idx >= len(df):
                break
            close = df.iloc[exit_idx]["close"]
            ma10 = df.iloc[exit_idx]["ma10"]
            if pd.notna(ma10) and close < ma10:
                ret = (close - entry_price) / entry_price * 100
                ma10_returns.append(ret)
                ma10_hold_days.append(offset)
                break
        else:
            # 30 天内未触发 MA10 出场，按最后一天卖出
            last_idx = min(entry_idx + 30, len(df) - 1)
            close = df.iloc[last_idx]["close"]
            ret = (close - entry_price) / entry_price * 100
            ma10_returns.append(ret)
            ma10_hold_days.append(last_idx - entry_idx)

    # 策略 C: MA20 出场
    ma20_returns = []
    ma20_hold_days = []
    for code, entry_idx, entry_price in entries:
        df = indexed[code]
        ma20 = calculate_ma(df, 20)
        for offset in range(1, 31):
            exit_idx = entry_idx + offset
            if exit_idx >= len(df):
                break
            close = df.iloc[exit_idx]["close"]
            ma20_val = ma20.iloc[exit_idx] if exit_idx < len(ma20) else None
            if ma20_val is not None and pd.notna(ma20_val) and close < ma20_val:
                ret = (close - entry_price) / entry_price * 100
                ma20_returns.append(ret)
                ma20_hold_days.append(offset)
                break
        else:
            last_idx = min(entry_idx + 30, len(df) - 1)
            close = df.iloc[last_idx]["close"]
            ret = (close - entry_price) / entry_price * 100
            ma20_returns.append(ret)
            ma20_hold_days.append(last_idx - entry_idx)

    print(f"\n  统一次日开盘买入，对比不同出场方式:\n")
    print(f"  {'出场方式':<20}  {'平均收益':>8}  {'中位收益':>8}  {'胜率':>8}  {'平均天数':>8}  {'样本':>5}")
    print(f"  {'-' * 20}  {'-' * 8}  {'-' * 8}  {'-' * 8}  {'-' * 8}  {'-' * 5}")

    for d in hold_periods:
        if not fixed_results[d]:
            continue
        arr = np.array(fixed_results[d])
        mean_r = np.mean(arr)
        median_r = np.median(arr)
        wr = np.sum(arr > 0) / len(arr) * 100
        sign = "+" if mean_r >= 0 else ""
        sign_m = "+" if median_r >= 0 else ""
        print(
            f"  固定持有{d:>2}天          {sign}{mean_r:>7.2f}%  {sign_m}{median_r:>7.2f}%  "
            f"{wr:>7.1f}%  {d:>6.1f}天  {len(arr):>5}"
        )

    if ma10_returns:
        arr = np.array(ma10_returns)
        mean_r = np.mean(arr)
        median_r = np.median(arr)
        wr = np.sum(arr > 0) / len(arr) * 100
        avg_days = np.mean(ma10_hold_days)
        sign = "+" if mean_r >= 0 else ""
        sign_m = "+" if median_r >= 0 else ""
        print(
            f"  跌破MA10出场          {sign}{mean_r:>7.2f}%  {sign_m}{median_r:>7.2f}%  "
            f"{wr:>7.1f}%  {avg_days:>6.1f}天  {len(arr):>5}"
        )

    if ma20_returns:
        arr = np.array(ma20_returns)
        mean_r = np.mean(arr)
        median_r = np.median(arr)
        wr = np.sum(arr > 0) / len(arr) * 100
        avg_days = np.mean(ma20_hold_days)
        sign = "+" if mean_r >= 0 else ""
        sign_m = "+" if median_r >= 0 else ""
        print(
            f"  跌破MA20出场          {sign}{mean_r:>7.2f}%  {sign_m}{median_r:>7.2f}%  "
            f"{wr:>7.1f}%  {avg_days:>6.1f}天  {len(arr):>5}"
        )

    print()


def analyze_signal_exits(
    signals: Dict[str, List[Tuple[str, str]]],
    stock_data: Dict[str, pd.DataFrame],
):
    """
    分析各种信号型退出策略

    对比：MA均线族、移动止损、缩量退出、首根阴线退出等
    """
    print()
    print("=" * 70)
    print("  诊断 4：信号型退出策略全面对比（持有至数据结束）")
    print("=" * 70)

    MAX_HOLD = 9999  # 不限持有天数，直到数据结束

    indexed: Dict[str, pd.DataFrame] = {}
    for code, df in stock_data.items():
        df = df.sort_values("date").reset_index(drop=True)
        df["ma5"] = calculate_ma(df, 5)
        df["ma10"] = calculate_ma(df, 10)
        df["ma20"] = calculate_ma(df, 20)
        df["ma60"] = calculate_ma(df, 60)
        # 5日均量
        df["vol_ma5"] = df["volume"].rolling(5).mean()
        indexed[code] = df

    # 收集入场点（阴线入场）
    entries = []
    for date, stocks in signals.items():
        for code, name in stocks:
            if code not in indexed:
                continue
            df = indexed[code]
            dates_list = df["date"].tolist()
            if date not in dates_list:
                continue
            idx = dates_list.index(date)
            # 5天窗口找阴线
            for offset in range(1, 6):
                entry_idx = idx + offset
                if entry_idx >= len(df):
                    break
                row = df.iloc[entry_idx]
                if row["close"] < row["open"]:
                    entry_price = float(row["close"])
                    if entry_price > 0:
                        entries.append((code, entry_idx, entry_price))
                    break

    def run_exit_strategy(name, exit_fn):
        """通用退出策略测试框架"""
        returns = []
        hold_days_list = []
        for code, entry_idx, entry_price in entries:
            df = indexed[code]
            peak = entry_price
            for offset in range(1, MAX_HOLD + 1):
                exit_idx = entry_idx + offset
                if exit_idx >= len(df):
                    break
                row = df.iloc[exit_idx]
                close = float(row["close"])
                peak = max(peak, close)
                if exit_fn(row, entry_price, peak, offset):
                    ret = (close - entry_price) / entry_price * 100
                    returns.append(ret)
                    hold_days_list.append(offset)
                    break
            else:
                last_idx = min(entry_idx + MAX_HOLD, len(df) - 1)
                close = float(df.iloc[last_idx]["close"])
                ret = (close - entry_price) / entry_price * 100
                returns.append(ret)
                hold_days_list.append(last_idx - entry_idx)
        return returns, hold_days_list

    strategies = {}

    # ---- MA 均线族 ----
    for ma_name, ma_col in [("MA5", "ma5"), ("MA10", "ma10"), ("MA20", "ma20")]:
        def make_ma_exit(col):
            def exit_fn(row, entry_price, peak, offset):
                ma_val = row.get(col)
                if ma_val is not None and pd.notna(ma_val):
                    return float(row["close"]) < float(ma_val)
                return False
            return exit_fn
        strategies[f"跌破{ma_name}"] = make_ma_exit(ma_col)

    # ---- 移动止损（从最高点回撤 X%）----
    for pct in [5, 8, 10, 15]:
        def make_trailing(p):
            def exit_fn(row, entry_price, peak, offset):
                close = float(row["close"])
                drawdown = (peak - close) / peak * 100 if peak > 0 else 0
                return drawdown >= p
            return exit_fn
        strategies[f"移动止损{pct}%"] = make_trailing(pct)

    # ---- 固定止盈 ----
    for pct in [10, 15, 20]:
        def make_tp(p):
            def exit_fn(row, entry_price, peak, offset):
                close = float(row["close"])
                ret = (close - entry_price) / entry_price * 100
                return ret >= p
            return exit_fn
        strategies[f"止盈{pct}%"] = make_tp(pct)

    # ---- 固定止损 ----
    for pct in [5, 8, 10]:
        def make_sl(p):
            def exit_fn(row, entry_price, peak, offset):
                close = float(row["close"])
                ret = (close - entry_price) / entry_price * 100
                return ret <= -p
            return exit_fn
        strategies[f"止损{pct}%"] = make_sl(pct)

    # ---- 跌破MA20 + 缩量确认 ----
    def exit_ma20_vol_shrink(row, entry_price, peak, offset):
        ma20 = row.get("ma20")
        vol_ma5 = row.get("vol_ma5")
        vol = float(row.get("volume", 0) or 0)
        if ma20 is not None and pd.notna(ma20) and float(row["close"]) < float(ma20):
            if vol_ma5 is not None and pd.notna(vol_ma5) and vol_ma5 > 0:
                if vol < float(vol_ma5) * 0.8:
                    return True
        return False
    strategies["跌破MA20+缩量"] = exit_ma20_vol_shrink

    # ---- 移动止损10% + 止盈20% 组合 ----
    def exit_trailing10_tp20(row, entry_price, peak, offset):
        close = float(row["close"])
        ret = (close - entry_price) / entry_price * 100
        if ret >= 20:
            return True
        drawdown = (peak - close) / peak * 100 if peak > 0 else 0
        if drawdown >= 10:
            return True
        return False
    strategies["移动止损10%+止盈20%"] = exit_trailing10_tp20

    # ---- 移动止损8% + 止盈15% 组合 ----
    def exit_trailing8_tp15(row, entry_price, peak, offset):
        close = float(row["close"])
        ret = (close - entry_price) / entry_price * 100
        if ret >= 15:
            return True
        drawdown = (peak - close) / peak * 100 if peak > 0 else 0
        if drawdown >= 8:
            return True
        return False
    strategies["移动止损8%+止盈15%"] = exit_trailing8_tp15

    # ---- 跌破MA20 或 移动止损10% ----
    def exit_ma20_or_trailing10(row, entry_price, peak, offset):
        close = float(row["close"])
        ma20 = row.get("ma20")
        if ma20 is not None and pd.notna(ma20) and close < float(ma20):
            return True
        drawdown = (peak - close) / peak * 100 if peak > 0 else 0
        if drawdown >= 10:
            return True
        return False
    strategies["跌破MA20或移动止损10%"] = exit_ma20_or_trailing10

    # 执行所有策略
    print(f"\n  阴线入场，持有至信号触发或数据结束:\n")
    print(f"  {'退出策略':<24}  {'平均收益':>8}  {'中位收益':>8}  {'胜率':>8}  {'平均天数':>8}  {'样本':>5}")
    print(f"  {'-' * 24}  {'-' * 8}  {'-' * 8}  {'-' * 8}  {'-' * 8}  {'-' * 5}")

    for name, exit_fn in strategies.items():
        rets, days = run_exit_strategy(name, exit_fn)
        if not rets:
            continue
        arr = np.array(rets)
        mean_r = np.mean(arr)
        median_r = np.median(arr)
        wr = np.sum(arr > 0) / len(arr) * 100
        avg_days = np.mean(days)
        sign = "+" if mean_r >= 0 else ""
        sign_m = "+" if median_r >= 0 else ""
        print(
            f"  {name:<24}  {sign}{mean_r:>7.2f}%  {sign_m}{median_r:>7.2f}%  "
            f"{wr:>7.1f}%  {avg_days:>6.1f}天  {len(arr):>5}"
        )

    print()



def main():
    parser = argparse.ArgumentParser(description="回测诊断：分离信号质量 vs 策略影响")
    parser.add_argument("--combination", "-c", required=True)
    parser.add_argument("--db-path", type=str, default="pipeline/data/kline.db")
    parser.add_argument("--start", type=str)
    parser.add_argument("--end", type=str)
    args = parser.parse_args()

    # 加载数据
    logger.info(f"加载数据库: {args.db_path}")
    db = LocalDB(args.db_path)
    all_data = db.get_all_stocks_data()
    stock_data = {
        code: group.reset_index(drop=True)
        for code, group in all_data.groupby("code")
    }
    logger.info(f"共 {len(stock_data)} 只股票")

    # 检测信号
    combination = get_combination(args.combination)
    factors = [get_factor(fid) for fid in combination.factors]

    engine = BacktestEngine(
        combination=combination,
        factors=factors,
        start_date=args.start,
        end_date=args.end,
    )

    logger.info("Phase 1: 检测信号...")
    pbar = None

    def progress_callback(current, total, phase):
        nonlocal pbar
        if pbar is None:
            pbar = tqdm(total=total, desc="检测信号")
        pbar.update(1)

    signals = engine._detect_all_signals(stock_data, {}, progress_callback)
    if pbar:
        pbar.close()

    total_signals = sum(len(v) for v in signals.values())
    signal_days = len(signals)
    logger.info(f"共 {total_signals} 个信号，分布在 {signal_days} 个交易日")

    # 运行诊断
    # analyze_signal_quality(signals, stock_data)
    # analyze_entry_strategy(signals, stock_data)
    # analyze_exit_strategy(signals, stock_data)
    analyze_signal_exits(signals, stock_data)


if __name__ == "__main__":
    main()
