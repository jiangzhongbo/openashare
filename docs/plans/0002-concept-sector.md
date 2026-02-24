# Plan 0002: 概念板块筛选

## 目标

**把概念板块当成股票**，用现有因子筛选，发现满足信号的板块加入观察名单。

## 核心思路

```
概念板块 K 线 = 成分股涨跌幅的等权平均

板块有了 K 线 → 就能算 MA60、MACD 等指标 → 复用现有因子筛选
```

## 数据流

```
1. 本地每周更新 concepts.json（板块 → 成分股映射）
2. GitHub Actions 每日运行：
   - 读取 concepts.json
   - 用成分股 K 线合成板块 K 线
   - 对板块运行因子筛选
   - 输出满足条件的板块
```

## 新增文件

```
pipeline/
├── data/
│   └── concepts.json          # 板块 → 成分股映射
└── sectors/
    ├── kline_builder.py       # 合成板块 K 线
    └── updater.py             # 从 AKShare 更新映射（本地运行）
```

## concepts.json 结构

```json
{
  "update_date": "2026-02-23",
  "concepts": {
    "人形机器人": ["300024", "002747", "300276"],
    "商业航天": ["600118", "000547", "002025"],
    "AI芯片": ["688256", "688041", "603501"]
  }
}
```

## 板块 K 线合成

```python
def build_sector_kline(sector_name: str, stock_klines: pd.DataFrame) -> pd.DataFrame:
    """
    用成分股 K 线合成板块 K 线

    返回: date, open, high, low, close, pct_chg
    """
    stocks = concepts[sector_name]
    df = stock_klines[stock_klines['code'].isin(stocks)]

    # 按日期分组，取平均
    sector_kline = df.groupby('date').agg({
        'pct_chg': 'mean',  # 涨跌幅取平均
    }).reset_index()

    # 用涨跌幅反推 close（假设起点=100）
    sector_kline['close'] = (1 + sector_kline['pct_chg']/100).cumprod() * 100

    return sector_kline
```

## 数据存储

### 板块 K 线：实时合成，不存储

```
kline.db（本地缓存）
└── daily_kline          # 股票 K 线（现有，板块 K 线由此实时合成）

D1（Cloudflare 云端）
├── screening_results    # 股票筛选结果（现有）
├── sector_screening     # 板块筛选结果（新增）
└── run_logs             # 运行日志（现有）
```

### D1 新增表：sector_screening

```sql
CREATE TABLE sector_screening (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL,
    combination TEXT NOT NULL,
    sector_name TEXT NOT NULL,
    stock_count INTEGER,
    latest_price REAL,           -- 板块指数（起点=100）
    pct_chg REAL,                -- 当日涨跌幅
    ma60_change_pct REAL,
    macd_days_ago INTEGER,
    passed_factors TEXT,         -- JSON
    created_at TEXT,
    UNIQUE(run_date, combination, sector_name)
);
```

## 实施步骤

1. [ ] 创建 `concepts.json`（30 个热门板块）
2. [ ] 创建 `kline_builder.py` 合成板块 K 线
3. [ ] 复用现有因子对板块筛选
4. [ ] D1 新增 `sector_screening` 表
5. [ ] 输出板块观察名单
