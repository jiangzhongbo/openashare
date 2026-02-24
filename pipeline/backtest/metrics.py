"""绩效指标计算"""

from typing import List, Tuple, Dict
from .models import Trade


def calc_metrics(
    trades: List[Trade],
    nav_history: List[Tuple[str, float]],
    initial_capital: float,
) -> Dict[str, float]:
    """
    计算回测绩效指标

    Args:
        trades: 已完成交易列表
        nav_history: 净值历史 [(date, nav), ...]
        initial_capital: 初始资金

    Returns:
        绩效指标字典
    """
    if not nav_history:
        return {}

    metrics: Dict[str, float] = {}

    # 总收益率
    final_nav = nav_history[-1][1]
    total_return = (final_nav - initial_capital) / initial_capital * 100
    metrics["total_return_pct"] = round(total_return, 2)

    # 年化收益率
    trading_days = len(nav_history)
    if trading_days > 1:
        annual_factor = 250 / trading_days
        annualized = ((final_nav / initial_capital) ** annual_factor - 1) * 100
        metrics["annualized_return_pct"] = round(annualized, 2)

    # 最大回撤
    peak = initial_capital
    max_dd = 0.0
    for _, nav in nav_history:
        if nav > peak:
            peak = nav
        dd = (peak - nav) / peak * 100
        if dd > max_dd:
            max_dd = dd
    metrics["max_drawdown_pct"] = round(max_dd, 2)

    # 交易统计
    metrics["total_trades"] = len(trades)

    if trades:
        winners = [t for t in trades if t.return_pct > 0]
        losers = [t for t in trades if t.return_pct <= 0]

        metrics["win_rate_pct"] = round(len(winners) / len(trades) * 100, 2)

        avg_win = (sum(t.return_pct for t in winners) / len(winners)) if winners else 0
        avg_loss = (abs(sum(t.return_pct for t in losers) / len(losers))) if losers else 0
        metrics["profit_loss_ratio"] = round(avg_win / avg_loss, 2) if avg_loss > 0 else float("inf")

        metrics["avg_holding_days"] = round(
            sum(t.holding_days for t in trades) / len(trades), 1
        )
        metrics["max_win_pct"] = round(max(t.return_pct for t in trades), 2)
        metrics["max_loss_pct"] = round(min(t.return_pct for t in trades), 2)

    return metrics
