"""回测报告：终端格式化 + CSV 导出"""

import csv
from .models import BacktestResult


def print_report(result: BacktestResult):
    """打印终端回测报告"""
    m = result.metrics

    print()
    print("=" * 50)
    print(f"  回测报告：{result.combination_label}")
    print(f"  组合 ID：{result.combination_id}")
    print(f"  回测区间：{result.start_date} ~ {result.end_date}")
    print(f"  初始资金：{result.initial_capital:,.0f}")
    print("=" * 50)

    print()
    print("【绩效概览】")
    total_ret = m.get("total_return_pct", 0)
    sign = "+" if total_ret >= 0 else ""
    print(f"  总收益率:      {sign}{total_ret:.2f}%")

    if "annualized_return_pct" in m:
        ann_ret = m["annualized_return_pct"]
        sign = "+" if ann_ret >= 0 else ""
        print(f"  年化收益率:    {sign}{ann_ret:.2f}%")

    print(f"  最大回撤:      -{m.get('max_drawdown_pct', 0):.2f}%")

    total_trades = m.get("total_trades", 0)
    if total_trades > 0:
        win_rate = m.get("win_rate_pct", 0)
        winners = round(total_trades * win_rate / 100)
        print(f"  胜率:          {win_rate:.1f}%  ({winners}/{total_trades})")
        print(f"  盈亏比:        {m.get('profit_loss_ratio', 0):.2f}")

    print()
    print("【交易统计】")
    print(f"  总交易笔数:    {total_trades}")

    if total_trades > 0:
        print(f"  平均持仓天数:  {m.get('avg_holding_days', 0):.1f}")

        best = max(result.trades, key=lambda t: t.return_pct)
        worst = min(result.trades, key=lambda t: t.return_pct)
        print(f"  单笔最大盈利:  +{best.return_pct:.2f}%  ({best.code} {best.name})")
        print(f"  单笔最大亏损:  {worst.return_pct:.2f}%  ({worst.code} {worst.name})")

    if result.trades:
        print()
        recent = result.trades[-10:]
        print(f"【交易明细】(最近 {len(recent)} 笔)")
        print(f"  {'买入日':>10}  {'代码':>6}  {'名称':<6}  {'买入价':>7}  {'卖出价':>7}  {'收益率':>7}  {'天数':>4}")
        for t in recent:
            sign = "+" if t.return_pct >= 0 else ""
            print(
                f"  {t.entry_date:>10}  {t.code:>6}  {t.name:<6}  "
                f"{t.entry_price:>7.2f}  {t.exit_price:>7.2f}  "
                f"{sign}{t.return_pct:>6.2f}%  {t.holding_days:>4}"
            )

    print()
    print(f"  期末净值: {result.final_nav:,.2f}")
    print("=" * 50)
    print()


def export_csv(result: BacktestResult, path: str):
    """导出交易明细到 CSV"""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "代码", "名称", "买入日期", "买入价格",
            "卖出日期", "卖出价格", "股数",
            "盈亏金额", "收益率(%)", "持仓天数",
        ])
        for t in result.trades:
            writer.writerow([
                t.code, t.name, t.entry_date, f"{t.entry_price:.2f}",
                t.exit_date, f"{t.exit_price:.2f}", t.shares,
                f"{t.pnl:.2f}", f"{t.return_pct:.2f}", t.holding_days,
            ])
    print(f"交易明细已导出: {path} ({len(result.trades)} 笔)")
