"""
信号特征分析

对比赢家/输家信号在各个维度上的差异，找出哪些特征能区分好坏信号。
"""

import argparse
import logging
import sys
import os
from typing import Dict, List, Tuple

import pandas as pd
import numpy as np
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pipeline.data.local_db import LocalDB
from pipeline.factors.base import calculate_ma
from pipeline.factors.registry import get_combination, get_factor
from pipeline.backtest.engine import BacktestEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def extract_signal_features(
    signals: Dict[str, List[Tuple[str, str]]],
    stock_data: Dict[str, pd.DataFrame],
    forward_days: int = 10,
):
    """
    提取每个信号的特征 + 前瞻收益，用于分析赢家 vs 输家

    特征维度：
    1. 信号日涨幅 (pct_chg)
    2. 成交量放大倍数 (volume_ratio)
    3. 收盘价 vs MA60 的距离 (price_vs_ma60)
    4. MA60 10天斜率 (ma60_slope)
    5. 跌破MA60的天数 (days_below_ma60)
    6. 信号日换手率 (turn)
    7. MA20 vs MA60 的距离 (ma20_vs_ma60)
    8. 前5日平均换手率 (avg_turn_5d)
    9. 收盘价距离前高的回撤幅度 (drawdown_from_high)
    10. 前20日波动率 (volatility_20d)
    """
    records = []

    for date, stocks in signals.items():
        for code, name in stocks:
            if code not in stock_data:
                continue
            df = stock_data[code]
            df = df.sort_values("date").reset_index(drop=True)
            dates_list = df["date"].tolist()
            if date not in dates_list:
                continue
            idx = dates_list.index(date)

            # 前瞻收益
            fwd_idx = idx + forward_days
            if fwd_idx >= len(df):
                continue

            fwd_return = (df.iloc[fwd_idx]["close"] - df.iloc[idx]["close"]) / df.iloc[idx]["close"] * 100

            # 需要足够历史数据
            if idx < 60:
                continue

            row = df.iloc[idx]
            yesterday = df.iloc[idx - 1]

            # 计算 MA
            ma60 = df["close"].iloc[max(0, idx - 59):idx + 1].mean()
            ma20 = df["close"].iloc[max(0, idx - 19):idx + 1].mean()
            ma10 = df["close"].iloc[max(0, idx - 9):idx + 1].mean()

            # MA60 10天前的值
            if idx >= 10:
                ma60_10ago = df["close"].iloc[max(0, idx - 10 - 59):idx - 10 + 1].mean()
                ma60_slope = (ma60 - ma60_10ago) / ma60_10ago * 100
            else:
                ma60_slope = 0

            # 特征 1: 信号日涨幅
            pct_chg = float(row.get("pct_chg", 0) or 0)

            # 特征 2: 成交量放大倍数
            vol_today = float(row.get("volume", 0) or 0)
            vol_yesterday = float(yesterday.get("volume", 0) or 0)
            volume_ratio = vol_today / vol_yesterday if vol_yesterday > 0 else 0

            # 特征 3: 收盘价 vs MA60 距离
            close = float(row["close"])
            price_vs_ma60 = (close - ma60) / ma60 * 100 if ma60 > 0 else 0

            # 特征 4: 跌破 MA60 的天数
            days_below = 0
            for j in range(idx - 1, max(idx - 20, -1), -1):
                if df.iloc[j]["close"] < ma60:
                    days_below += 1
                else:
                    break

            # 特征 5: 换手率
            turn = float(row.get("turn", 0) or 0)

            # 特征 6: MA20 vs MA60
            ma20_vs_ma60 = (ma20 - ma60) / ma60 * 100 if ma60 > 0 else 0

            # 特征 7: 前 5 日平均换手率
            avg_turn_5d = df["turn"].iloc[max(0, idx - 4):idx + 1].mean()
            avg_turn_5d = float(avg_turn_5d) if pd.notna(avg_turn_5d) else 0

            # 特征 8: 距离前高回撤
            high_20d = df["close"].iloc[max(0, idx - 19):idx + 1].max()
            drawdown = (close - high_20d) / high_20d * 100 if high_20d > 0 else 0

            # 特征 9: 20日波动率
            if idx >= 20:
                returns_20d = df["pct_chg"].iloc[idx - 19:idx + 1]
                volatility = returns_20d.std()
                volatility = float(volatility) if pd.notna(volatility) else 0
            else:
                volatility = 0

            # 特征 10: 前5日平均成交量放大（相对20日均量）
            avg_vol_20d = df["volume"].iloc[max(0, idx - 19):idx + 1].mean()
            avg_vol_5d = df["volume"].iloc[max(0, idx - 4):idx + 1].mean()
            vol_5d_vs_20d = avg_vol_5d / avg_vol_20d if avg_vol_20d > 0 else 0

            records.append({
                "code": code,
                "date": date,
                "fwd_return": fwd_return,
                "winner": fwd_return > 0,
                "pct_chg": pct_chg,
                "volume_ratio": volume_ratio,
                "price_vs_ma60": price_vs_ma60,
                "ma60_slope": ma60_slope,
                "days_below_ma60": days_below,
                "turn": turn,
                "ma20_vs_ma60": ma20_vs_ma60,
                "avg_turn_5d": avg_turn_5d,
                "drawdown_from_high": drawdown,
                "volatility_20d": volatility,
                "vol_5d_vs_20d": vol_5d_vs_20d,
            })

    return pd.DataFrame(records)


def print_feature_comparison(features_df: pd.DataFrame):
    """对比赢家 vs 输家的特征分布"""

    print()
    print("=" * 70)
    print("  信号特征分析：赢家 vs 输家（10天前瞻收益 > 0 为赢家）")
    print("=" * 70)

    winners = features_df[features_df["winner"]]
    losers = features_df[~features_df["winner"]]

    print(f"\n  总信号: {len(features_df)}, 赢家: {len(winners)}, 输家: {len(losers)}")
    print(f"  赢家平均收益: +{winners['fwd_return'].mean():.2f}%")
    print(f"  输家平均收益: {losers['fwd_return'].mean():.2f}%")

    feature_labels = {
        "pct_chg": "信号日涨幅(%)",
        "volume_ratio": "量比(vs昨日)",
        "price_vs_ma60": "价格vs MA60(%)",
        "ma60_slope": "MA60 10日斜率(%)",
        "days_below_ma60": "跌破MA60天数",
        "turn": "信号日换手率(%)",
        "ma20_vs_ma60": "MA20 vs MA60(%)",
        "avg_turn_5d": "5日平均换手率(%)",
        "drawdown_from_high": "距20日高点回撤(%)",
        "volatility_20d": "20日波动率",
        "vol_5d_vs_20d": "5日均量/20日均量",
    }

    print(f"\n  {'特征':<20}  {'赢家中位':>10}  {'输家中位':>10}  {'差异':>10}  {'方向':>6}")
    print(f"  {'-' * 20}  {'-' * 10}  {'-' * 10}  {'-' * 10}  {'-' * 6}")

    for feat, label in feature_labels.items():
        w_med = winners[feat].median()
        l_med = losers[feat].median()
        diff = w_med - l_med
        direction = "赢家高" if diff > 0 else "输家高"
        sign = "+" if diff > 0 else ""
        print(f"  {label:<20}  {w_med:>10.2f}  {l_med:>10.2f}  {sign}{diff:>9.2f}  {direction:>6}")

    # 分位数分析：哪些特征最能区分好坏
    print()
    print("=" * 70)
    print("  分层分析：按特征分组后看胜率和收益")
    print("=" * 70)

    key_features = [
        ("pct_chg", "信号日涨幅(%)"),
        ("volume_ratio", "量比"),
        ("ma60_slope", "MA60斜率(%)"),
        ("days_below_ma60", "跌破MA60天数"),
        ("turn", "换手率(%)"),
        ("volatility_20d", "20日波动率"),
        ("price_vs_ma60", "价格vs MA60(%)"),
    ]

    for feat, label in key_features:
        print(f"\n  --- {label} ---")
        try:
            features_df["_bin"] = pd.qcut(features_df[feat], q=3, labels=["低", "中", "高"], duplicates="drop")
        except ValueError:
            continue

        print(f"  {'分组':<6}  {'范围':<20}  {'样本':>5}  {'胜率':>7}  {'平均收益':>8}  {'中位收益':>8}")
        for group_name in ["低", "中", "高"]:
            group = features_df[features_df["_bin"] == group_name]
            if len(group) == 0:
                continue
            wr = group["winner"].mean() * 100
            mean_r = group["fwd_return"].mean()
            med_r = group["fwd_return"].median()
            lo = group[feat].min()
            hi = group[feat].max()
            sign_m = "+" if mean_r >= 0 else ""
            sign_md = "+" if med_r >= 0 else ""
            print(
                f"  {group_name:<6}  {lo:>8.2f} ~ {hi:<8.2f}  {len(group):>5}  "
                f"{wr:>6.1f}%  {sign_m}{mean_r:>7.2f}%  {sign_md}{med_r:>7.2f}%"
            )

        features_df.drop("_bin", axis=1, inplace=True)


def main():
    parser = argparse.ArgumentParser(description="信号特征分析")
    parser.add_argument("--combination", "-c", required=True)
    parser.add_argument("--db-path", type=str, default="data/kline.db")
    parser.add_argument("--forward-days", type=int, default=10)
    args = parser.parse_args()

    db = LocalDB(args.db_path)
    all_data = db.get_all_stocks_data()
    stock_data = {
        code: group.reset_index(drop=True)
        for code, group in all_data.groupby("code")
    }
    logger.info(f"共 {len(stock_data)} 只股票")

    combination = get_combination(args.combination)
    factors = [get_factor(fid) for fid in combination.factors]
    engine = BacktestEngine(combination=combination, factors=factors)

    logger.info("检测信号...")
    pbar = None
    def progress_callback(current, total, phase):
        nonlocal pbar
        if pbar is None:
            pbar = tqdm(total=total, desc="检测信号")
        pbar.update(1)

    signals = engine._detect_all_signals(stock_data, {}, progress_callback)
    if pbar:
        pbar.close()

    logger.info("提取信号特征...")
    features_df = extract_signal_features(signals, stock_data, args.forward_days)
    logger.info(f"有效信号: {len(features_df)}")

    print_feature_comparison(features_df)


if __name__ == "__main__":
    main()
