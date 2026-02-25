"""
成交量 & 换手率深度分析

从多个角度拆解量的质量：
1. 量比（vs 昨日）的分层
2. 量比（vs 5日/20日均量）
3. 换手率绝对值分层
4. 量比 × 换手率 交叉分析
5. 前几日缩量程度（跌破期间是否缩量）
6. 信号日成交量占近期总量的集中度
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


def extract_volume_features(
    signals: Dict[str, List[Tuple[str, str]]],
    stock_data: Dict[str, pd.DataFrame],
    forward_days: int = 10,
) -> pd.DataFrame:
    """提取成交量/换手率相关的细化特征"""
    records = []

    for date, stocks in signals.items():
        for code, name in stocks:
            if code not in stock_data:
                continue
            df = stock_data[code].sort_values("date").reset_index(drop=True)
            dates_list = df["date"].tolist()
            if date not in dates_list:
                continue
            idx = dates_list.index(date)

            if idx < 60 or idx + forward_days >= len(df):
                continue

            row = df.iloc[idx]
            fwd_return = (df.iloc[idx + forward_days]["close"] - row["close"]) / row["close"] * 100

            vol = float(row.get("volume", 0) or 0)
            turn = float(row.get("turn", 0) or 0)
            pct_chg = float(row.get("pct_chg", 0) or 0)

            # 昨日量
            vol_1d = float(df.iloc[idx - 1].get("volume", 0) or 0)
            vol_ratio_1d = vol / vol_1d if vol_1d > 0 else 0

            # vs 5日均量
            vol_5d = df["volume"].iloc[max(0, idx - 5):idx].mean()
            vol_ratio_5d = vol / vol_5d if vol_5d > 0 else 0

            # vs 20日均量
            vol_20d = df["volume"].iloc[max(0, idx - 20):idx].mean()
            vol_ratio_20d = vol / vol_20d if vol_20d > 0 else 0

            # 跌破期间的缩量程度：跌破MA60那几天的平均量 vs 20日均量
            ma60_series = df["close"].rolling(60).mean()
            days_below = 0
            vol_below_sum = 0
            for j in range(idx - 1, max(idx - 20, -1), -1):
                if j < 60:
                    break
                if df.iloc[j]["close"] < ma60_series.iloc[j]:
                    days_below += 1
                    vol_below_sum += float(df.iloc[j].get("volume", 0) or 0)
                else:
                    break

            vol_below_avg = vol_below_sum / days_below if days_below > 0 else vol_20d
            shrink_ratio = vol_below_avg / vol_20d if vol_20d > 0 else 1.0  # 跌破期间量 / 正常量

            # 信号日量占近5日总量的集中度
            vol_5d_total = df["volume"].iloc[max(0, idx - 4):idx + 1].sum()
            vol_concentration = vol / vol_5d_total if vol_5d_total > 0 else 0

            # 前5日平均换手率
            turn_5d = df["turn"].iloc[max(0, idx - 5):idx].mean()
            turn_5d = float(turn_5d) if pd.notna(turn_5d) else 0

            # 换手率放大倍数：信号日换手 / 前5日平均换手
            turn_ratio = turn / turn_5d if turn_5d > 0 else 0

            # 20日波动率（用于交叉分析）
            if idx >= 20:
                vol_20d_std = df["pct_chg"].iloc[idx - 19:idx + 1].std()
                volatility = float(vol_20d_std) if pd.notna(vol_20d_std) else 0
            else:
                volatility = 0

            records.append({
                "code": code,
                "date": date,
                "fwd_return": fwd_return,
                "winner": fwd_return > 0,
                "pct_chg": pct_chg,
                "turn": turn,
                "turn_5d_avg": turn_5d,
                "turn_ratio": turn_ratio,
                "vol_ratio_1d": vol_ratio_1d,
                "vol_ratio_5d": vol_ratio_5d,
                "vol_ratio_20d": vol_ratio_20d,
                "shrink_ratio": shrink_ratio,
                "vol_concentration": vol_concentration,
                "days_below": days_below,
                "volatility": volatility,
            })

    return pd.DataFrame(records)


def print_layer_analysis(df: pd.DataFrame, feature: str, label: str, bins=None, q=3):
    """按特征分层分析"""
    print(f"\n  --- {label} ---")
    try:
        if bins is not None:
            df["_bin"] = pd.cut(df[feature], bins=bins, duplicates="drop")
        else:
            df["_bin"] = pd.qcut(df[feature], q=q, duplicates="drop")
    except ValueError:
        print("  (数据不足，无法分层)")
        return

    groups = df.groupby("_bin", observed=True)
    print(f"  {'分组':<22}  {'样本':>5}  {'胜率':>7}  {'平均收益':>8}  {'中位收益':>8}")
    for name, group in groups:
        if len(group) < 5:
            continue
        wr = group["winner"].mean() * 100
        mean_r = group["fwd_return"].mean()
        med_r = group["fwd_return"].median()
        sign_m = "+" if mean_r >= 0 else ""
        sign_md = "+" if med_r >= 0 else ""
        print(
            f"  {str(name):<22}  {len(group):>5}  "
            f"{wr:>6.1f}%  {sign_m}{mean_r:>7.2f}%  {sign_md}{med_r:>7.2f}%"
        )
    df.drop("_bin", axis=1, inplace=True)


def print_cross_analysis(df: pd.DataFrame, feat_a: str, label_a: str, feat_b: str, label_b: str, q=2):
    """两个特征交叉分析"""
    print(f"\n  === {label_a} × {label_b} 交叉分析 ===")
    try:
        df["_a"] = pd.qcut(df[feat_a], q=q, labels=[f"{label_a}低", f"{label_a}高"], duplicates="drop")
        df["_b"] = pd.qcut(df[feat_b], q=q, labels=[f"{label_b}低", f"{label_b}高"], duplicates="drop")
    except ValueError:
        print("  (数据不足)")
        return

    print(f"  {'组合':<26}  {'样本':>5}  {'胜率':>7}  {'平均收益':>8}  {'中位收益':>8}")
    for a_val in df["_a"].cat.categories:
        for b_val in df["_b"].cat.categories:
            group = df[(df["_a"] == a_val) & (df["_b"] == b_val)]
            if len(group) < 10:
                continue
            wr = group["winner"].mean() * 100
            mean_r = group["fwd_return"].mean()
            med_r = group["fwd_return"].median()
            sign_m = "+" if mean_r >= 0 else ""
            sign_md = "+" if med_r >= 0 else ""
            combo = f"{a_val} + {b_val}"
            print(
                f"  {combo:<26}  {len(group):>5}  "
                f"{wr:>6.1f}%  {sign_m}{mean_r:>7.2f}%  {sign_md}{med_r:>7.2f}%"
            )
    df.drop(["_a", "_b"], axis=1, inplace=True)


def main():
    parser = argparse.ArgumentParser(description="成交量深度分析")
    parser.add_argument("--combination", "-c", required=True)
    parser.add_argument("--db-path", type=str, default="pipeline/data/kline.db")
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

    logger.info("提取量价特征...")
    vdf = extract_volume_features(signals, stock_data, args.forward_days)
    logger.info(f"有效信号: {len(vdf)}")

    # ============================================================
    print()
    print("=" * 70)
    print("  Part 1：量比的不同衡量方式，哪个更有区分度？")
    print("=" * 70)

    print_layer_analysis(vdf, "vol_ratio_1d", "量比 vs 昨日", q=4)
    print_layer_analysis(vdf, "vol_ratio_5d", "量比 vs 5日均量", q=4)
    print_layer_analysis(vdf, "vol_ratio_20d", "量比 vs 20日均量", q=4)

    # ============================================================
    print()
    print("=" * 70)
    print("  Part 2：换手率分层")
    print("=" * 70)

    print_layer_analysis(vdf, "turn", "信号日换手率(%)",
                         bins=[0, 3, 5, 8, 12, 100])
    print_layer_analysis(vdf, "turn_ratio", "换手率放大倍数(vs前5日)", q=4)

    # ============================================================
    print()
    print("=" * 70)
    print("  Part 3：跌破期间缩量程度")
    print("=" * 70)

    print_layer_analysis(vdf, "shrink_ratio", "跌破期缩量比(跌破期量/20日均量)", q=3)

    # ============================================================
    print()
    print("=" * 70)
    print("  Part 4：量的集中度（信号日量占近5日总量的比例）")
    print("=" * 70)

    print_layer_analysis(vdf, "vol_concentration", "量集中度", q=3)

    # ============================================================
    print()
    print("=" * 70)
    print("  Part 5：交叉分析 — 找最佳组合")
    print("=" * 70)

    print_cross_analysis(vdf, "vol_ratio_5d", "量比5d", "turn", "换手率")
    print_cross_analysis(vdf, "vol_ratio_5d", "量比5d", "shrink_ratio", "缩量比")
    print_cross_analysis(vdf, "turn", "换手率", "shrink_ratio", "缩量比")
    print_cross_analysis(vdf, "vol_ratio_5d", "量比5d", "volatility", "波动率")
    print_cross_analysis(vdf, "turn_ratio", "换手放大", "days_below", "破位天数")

    # ============================================================
    print()
    print("=" * 70)
    print("  Part 6：综合筛选模拟")
    print("=" * 70)

    filters = [
        ("原始信号（无过滤）", vdf),
        ("跌破≤2天", vdf[vdf["days_below"] <= 2]),
        ("跌破≤2天 + 波动率≤3.5", vdf[(vdf["days_below"] <= 2) & (vdf["volatility"] <= 3.5)]),
        ("跌破≤2天 + 量比5d≥2.5", vdf[(vdf["days_below"] <= 2) & (vdf["vol_ratio_5d"] >= 2.5)]),
        ("跌破≤2天 + 换手率3~12%", vdf[(vdf["days_below"] <= 2) & (vdf["turn"] >= 3) & (vdf["turn"] <= 12)]),
        ("跌破≤2天 + 跌破期缩量<0.8", vdf[(vdf["days_below"] <= 2) & (vdf["shrink_ratio"] < 0.8)]),
        ("跌破≤2天 + 波动≤3.5 + 换手3~12", vdf[
            (vdf["days_below"] <= 2) & (vdf["volatility"] <= 3.5) &
            (vdf["turn"] >= 3) & (vdf["turn"] <= 12)
        ]),
        ("跌破≤2天 + 波动≤3.5 + 缩量<0.8", vdf[
            (vdf["days_below"] <= 2) & (vdf["volatility"] <= 3.5) &
            (vdf["shrink_ratio"] < 0.8)
        ]),
        ("跌破≤2天 + 波动≤3.5 + 量比5d≥2.5 + 换手3~12", vdf[
            (vdf["days_below"] <= 2) & (vdf["volatility"] <= 3.5) &
            (vdf["vol_ratio_5d"] >= 2.5) & (vdf["turn"] >= 3) & (vdf["turn"] <= 12)
        ]),
        ("跌破≤2天 + 缩量<0.8 + 量比5d≥2.5", vdf[
            (vdf["days_below"] <= 2) & (vdf["shrink_ratio"] < 0.8) &
            (vdf["vol_ratio_5d"] >= 2.5)
        ]),
        ("跌破≤2天 + 缩量<0.8 + 量比5d≥2.5 + 换手3~12", vdf[
            (vdf["days_below"] <= 2) & (vdf["shrink_ratio"] < 0.8) &
            (vdf["vol_ratio_5d"] >= 2.5) & (vdf["turn"] >= 3) & (vdf["turn"] <= 12)
        ]),
    ]

    print(f"\n  {'过滤条件':<42}  {'样本':>5}  {'胜率':>7}  {'平均收益':>8}  {'中位收益':>8}")
    print(f"  {'-' * 42}  {'-' * 5}  {'-' * 7}  {'-' * 8}  {'-' * 8}")
    for label, subset in filters:
        if len(subset) == 0:
            print(f"  {label:<42}  {0:>5}  {'N/A':>7}  {'N/A':>8}  {'N/A':>8}")
            continue
        wr = subset["winner"].mean() * 100
        mean_r = subset["fwd_return"].mean()
        med_r = subset["fwd_return"].median()
        sign_m = "+" if mean_r >= 0 else ""
        sign_md = "+" if med_r >= 0 else ""
        print(
            f"  {label:<42}  {len(subset):>5}  "
            f"{wr:>6.1f}%  {sign_m}{mean_r:>7.2f}%  {sign_md}{med_r:>7.2f}%"
        )

    print()


if __name__ == "__main__":
    main()
