"""参数网格搜索 — 主板"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pipeline.data.local_db import LocalDB
from pipeline.backtest.engine import BacktestEngine
from pipeline.factors.ma60_bounce_with_volume import MA60BounceWithVolumeFactor
from pipeline.factors.ma60_recent_uptrend import MA60RecentUptrendFactor
from pipeline.factors.signal_quality_filter import SignalQualityFilterFactor
from pipeline.factors.combination import Combination

print("加载数据...", flush=True)
db = LocalDB("pipeline/data/kline.db")
all_data = db.get_all_stocks_data()
stock_data = {
    code: group.reset_index(drop=True)
    for code, group in all_data.groupby("code")
    if code.startswith(("000", "001", "002", "003", "600", "601", "603", "605"))
}
print(f"主板: {len(stock_data)} 只\n", flush=True)

combo = Combination(
    id="grid_test", label="网格测试",
    factors=["ma60_bounce_volume", "ma60_recent_uptrend", "signal_quality_filter"],
)

configs = [
    (3, 2.0, 5, 12),
    (5, 2.0, 5, 12),
    (7, 2.0, 5, 12),
    (5, 1.5, 5, 12),
    (5, 2.5, 5, 12),
    (5, 2.0, 3, 12),
    (5, 2.0, 5, 10),
    (5, 2.0, 5, 15),
    (5, 2.0, 5, 20),
    (3, 2.0, 5, 10),
    (3, 2.5, 5, 12),
    (3, 1.5, 5, 15),
    (5, 1.5, 3, 15),
    (5, 2.0, 3, 10),
    (7, 2.0, 3, 15),
    (3, 2.0, 3, 12),
    (5, 2.5, 5, 10),
    (7, 1.5, 5, 12),
]

print(f"共 {len(configs)} 组\n", flush=True)
print(f"{'#':>3} {'跌破':>5} {'量比':>5} {'换手':>8} | {'收益率':>8} {'盈亏比':>6} {'回撤':>7}", flush=True)
print("-" * 55, flush=True)

results = []
for i, (days, vol_r, t_min, t_max) in enumerate(configs):
    factors = [
        MA60BounceWithVolumeFactor(),
        MA60RecentUptrendFactor(),
        SignalQualityFilterFactor(
            max_days_below=days, min_vol_ratio_5d=vol_r,
            min_turn=t_min, max_turn=t_max,
        ),
    ]
    engine = BacktestEngine(
        combination=combo, factors=factors,
        take_profit_pct=10.0, max_hold_days=15, entry_window=5,
    )
    result = engine.run(stock_data)
    m = result.metrics
    ret = m.get("total_return_pct", 0)
    plr = m.get("profit_loss_ratio", 0)
    mdd = m.get("max_drawdown_pct", 0)
    tc = len(result.trades)
    wins = sum(1 for t in result.trades if t.return_pct > 0)
    wr = wins / tc * 100 if tc > 0 else 0

    print(f"{i+1:>3} {days:>4}天 {vol_r:>4}x {t_min:>2}~{t_max:>2}% | {ret:>+7.1f}% {plr:>6.2f} {mdd:>6.1f}%  ({tc}笔 {wr:.0f}%胜)", flush=True)
    results.append({"days": days, "vol_r": vol_r, "t_min": t_min, "t_max": t_max,
                     "ret": ret, "wr": wr, "tc": tc, "plr": plr, "mdd": mdd})

print("\n===== 按收益率排序 TOP 10 =====", flush=True)
results.sort(key=lambda x: x["ret"], reverse=True)
print(f"{'跌破':>5} {'量比':>5} {'换手':>8} | {'收益率':>8} {'盈亏比':>6} {'回撤':>7} {'笔数':>5} {'胜率':>5}", flush=True)
print("-" * 60, flush=True)
for r in results[:10]:
    print(f"{r['days']:>4}天 {r['vol_r']:>4}x {r['t_min']:>2}~{r['t_max']:>2}% | {r['ret']:>+7.1f}% {r['plr']:>6.2f} {r['mdd']:>6.1f}% {r['tc']:>5} {r['wr']:>4.0f}%", flush=True)
