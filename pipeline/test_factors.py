#!/usr/bin/env python3
"""
因子测试脚本

用法示例：
  # 测试单个因子
  python3 test_factors.py --factor turnover

  # 测试多个因子（AND 逻辑）
  python3 test_factors.py --factor turnover --factor rsi

  # 测试现有组合
  python3 test_factors.py --combination watch

  # 指定股票代码测试
  python3 test_factors.py --factor turnover --stock 000001

  # 显示所有可用因子
  python3 test_factors.py --list
"""

import argparse
import sys
import os
from datetime import datetime
from typing import List, Optional

# 添加当前目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data.local_db import LocalDB
from factors.registry import FACTOR_MAP, COMBINATION_MAP, get_all_factors
from factors.combination import Combination
from screening.screener import Screener


def list_available():
    """列出所有可用的因子和组合"""
    print("\n可用因子:")
    print("=" * 60)
    for fid, factor in FACTOR_MAP.items():
        print(f"  {fid:<20} - {factor.label}")
    
    print("\n可用组合:")
    print("=" * 60)
    for cid, combo in COMBINATION_MAP.items():
        print(f"  {cid:<20} - {combo.label}")
        print(f"    因子: {', '.join(combo.factors)}")
    print()


def test_factors(
    factor_ids: Optional[List[str]] = None,
    combination_id: Optional[str] = None,
    stock_code: Optional[str] = None,
    db_path: str = "data/kline.db",
):
    """测试因子或组合"""
    
    # 1. 确定要测试的组合
    if combination_id:
        if combination_id not in COMBINATION_MAP:
            print(f"错误: 组合 '{combination_id}' 不存在")
            list_available()
            sys.exit(1)
        combinations = [COMBINATION_MAP[combination_id]]
        print(f"\n测试组合: {combinations[0].label} ({combination_id})")
        print(f"包含因子: {', '.join(combinations[0].factors)}\n")
    elif factor_ids:
        # 验证因子存在
        for fid in factor_ids:
            if fid not in FACTOR_MAP:
                print(f"错误: 因子 '{fid}' 不存在")
                list_available()
                sys.exit(1)
        combinations = [
            Combination(
                id="test",
                label="临时测试组合",
                factors=factor_ids,
            )
        ]
        print(f"\n测试因子: {', '.join(factor_ids)}\n")
    else:
        print("错误: 必须指定 --factor 或 --combination")
        sys.exit(1)
    
    # 2. 加载数据
    db = LocalDB(db_path)
    
    if stock_code:
        # 测试单只股票
        print(f"加载股票 {stock_code} 的数据...")
        df = db.get_stock_history(stock_code, days=300)
        if df is None or df.empty:
            print(f"错误: 股票 {stock_code} 无数据")
            sys.exit(1)
        stock_data = {stock_code: df}
    else:
        # 测试全市场
        print("加载全市场数据...")
        stock_data_df = db.get_all_stocks_data()
        stock_data = {
            code: group.reset_index(drop=True)
            for code, group in stock_data_df.groupby("code")
        }
        print(f"加载 {len(stock_data)} 只股票\n")
    
    # 3. 运行筛选
    screener = Screener(
        factors=get_all_factors(),
        combinations=combinations,
    )
    
    run_date = datetime.now().strftime("%Y-%m-%d")
    report = screener.screen_all(stock_data, run_date=run_date)
    
    # 4. 打印结果
    print("=" * 60)
    print(f"筛选完成: 共 {report.total_stocks} 只，通过 {len(report.results)} 只")
    print("=" * 60)
    
    if report.results:
        for r in report.results:
            print(f"\n股票: {r.code} | 组合: {r.combination}")
            for fid, value in r.factor_values.items():
                factor_label = FACTOR_MAP.get(fid).label
                print(f"  - {factor_label} ({fid}): {value}")
            if r.factor_details:
                print("  详情:")
                for fid, detail in r.factor_details.items():
                    if detail:
                        print(f"    {fid}: {detail}")
    else:
        print("\n无股票通过筛选")
    
    print("\n" + "=" * 60)


def main():
    parser = argparse.ArgumentParser(description="因子测试工具")
    parser.add_argument(
        "--factor",
        action="append",
        help="要测试的因子 ID（可多次指定，AND 逻辑）",
    )
    parser.add_argument(
        "--combination",
        help="要测试的组合 ID",
    )
    parser.add_argument(
        "--stock",
        help="指定股票代码（不指定则测试全市场）",
    )
    parser.add_argument(
        "--db-path",
        default="data/kline.db",
        help="本地数据库路径",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有可用的因子和组合",
    )
    
    args = parser.parse_args()
    
    if args.list:
        list_available()
        sys.exit(0)
    
    test_factors(
        factor_ids=args.factor,
        combination_id=args.combination,
        stock_code=args.stock,
        db_path=args.db_path,
    )


if __name__ == "__main__":
    main()

