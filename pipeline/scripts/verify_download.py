"""
验证脚本：测试数据下载功能
- 连接 BaoStock
- 下载少量股票数据
- 写入本地 SQLite
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.local_db import LocalDB
from data.fetcher import BaoStockFetcher


def main():
    print("=" * 60)
    print("验证数据下载功能")
    print("=" * 60)
    
    # 1. 测试 BaoStock 连接
    print("\n[1/4] 测试 BaoStock 连接...")
    fetcher = BaoStockFetcher()
    if not fetcher.logged_in:
        print("❌ BaoStock 登录失败")
        return False
    print("✅ BaoStock 登录成功")
    
    # 2. 获取股票列表
    print("\n[2/4] 获取股票列表...")
    stock_list = fetcher.get_stock_list()
    if stock_list.empty:
        print("❌ 获取股票列表失败")
        return False
    print(f"✅ 获取股票列表成功，共 {len(stock_list)} 只股票")
    
    # 3. 下载少量股票数据（只取前 5 只）
    print("\n[3/4] 下载测试股票数据（前 5 只）...")
    test_stocks = stock_list.head(5)
    
    db = LocalDB("data/verify_test.db")
    total_records = 0
    
    for _, row in test_stocks.iterrows():
        code = row["code"]
        name = row["name"]
        print(f"  下载 {code} {name}...", end=" ")
        
        df = fetcher.get_stock_history(code)
        if not df.empty:
            db.upsert_kline_batch(df)
            total_records += len(df)
            print(f"✅ {len(df)} 条记录")
        else:
            print("⚠️ 无数据")
    
    print(f"\n  总计下载 {total_records} 条记录")
    
    # 4. 验证数据库
    print("\n[4/4] 验证数据库...")
    info = db.get_database_info()
    print(f"  数据库路径: {info['path']}")
    print(f"  数据库大小: {info['size_mb']} MB")
    print(f"  股票数量: {info['stock_count']}")
    print(f"  记录总数: {info['record_count']}")
    print(f"  最新日期: {info['latest_date']}")
    
    if info['record_count'] > 0:
        print("\n✅ 数据下载验证成功！")
        return True
    else:
        print("\n❌ 数据下载验证失败")
        return False


if __name__ == "__main__":
    success = main()
    print("\n" + "=" * 60)
    sys.exit(0 if success else 1)

