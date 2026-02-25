"""
回测引擎

两阶段架构：
- Phase 1: 信号检测（逐日对每只股票运行因子组合）
- Phase 2: 交易模拟（管理入场等待、买卖、净值）
"""

import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import pandas as pd

from pipeline.factors.base import Factor, FactorResult
from pipeline.factors.combination import Combination
from pipeline.factors.registry import get_combination, get_factor
from pipeline.backtest.models import (
    PendingSignal, BacktestResult, Trade,
)
from pipeline.backtest.strategy import EntryExitStrategy
from pipeline.backtest.portfolio import Portfolio
from pipeline.backtest.metrics import calc_metrics

logger = logging.getLogger(__name__)


class BacktestEngine:
    """回测引擎"""

    WARMUP_DAYS = 61

    def __init__(
        self,
        combination_id: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        initial_capital: float = 1_000_000,
        entry_window: int = 5,
        take_profit_pct: float = 10.0,
        combination: Optional[Combination] = None,
        factors: Optional[List[Factor]] = None,
        max_hold_days: int = 0,
        stop_loss_pct: float = 0,
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.entry_window = entry_window
        self.take_profit_pct = take_profit_pct
        self.max_hold_days = max_hold_days
        self.stop_loss_pct = stop_loss_pct

        if combination is not None and factors is not None:
            self.combination = combination
            self.factors = factors
            self.combination_id = combination.id
        else:
            self.combination_id = combination_id
            self.combination = get_combination(combination_id)
            self.factors = [get_factor(fid) for fid in self.combination.factors]

        self.strategy = EntryExitStrategy(
            entry_window=entry_window,
            take_profit_pct=take_profit_pct,
            stop_loss_pct=stop_loss_pct,
            max_hold_days=self.max_hold_days,
        )

    def run(
        self,
        stock_data: Dict[str, pd.DataFrame],
        stock_names: Optional[Dict[str, str]] = None,
        progress_callback=None,
    ) -> BacktestResult:
        stock_names = stock_names or {}

        # Phase 1: Signal detection
        logger.info("Phase 1: 检测信号...")
        signals = self._detect_all_signals(stock_data, stock_names, progress_callback)

        # Phase 2: Prepare data
        all_dates = self._get_trading_dates(stock_data)
        price_lookup = self._build_price_lookup(stock_data)

        # Phase 3: Trade simulation
        logger.info("Phase 2: 模拟交易...")
        portfolio = Portfolio(self.initial_capital)
        pending: Dict[str, PendingSignal] = {}
        nav_history: List[Tuple[str, float]] = []

        for date in all_dates:
            # (a) Check exits (take profit / max hold days)
            codes_to_sell = []
            for code in list(portfolio.positions.keys()):
                if code not in price_lookup or date not in price_lookup[code]:
                    continue
                close = price_lookup[code][date]["close"]
                pos = portfolio.positions[code]
                # 止盈退出
                if self.strategy.should_exit(close, pos.entry_price):
                    codes_to_sell.append((code, close))
                    continue
                # 最大持仓天数退出
                if self.max_hold_days > 0:
                    hold = (datetime.strptime(date, "%Y-%m-%d") - datetime.strptime(pos.entry_date, "%Y-%m-%d")).days
                    if hold >= self.max_hold_days:
                        codes_to_sell.append((code, close))

            for code, price in codes_to_sell:
                portfolio.sell(code, price, date)

            # (b) Check entries from pending queue
            entries_today = []
            expired = []
            for code, sig in pending.items():
                sig.days_waited += 1
                if code in price_lookup and date in price_lookup[code]:
                    row = price_lookup[code][date]
                    if self.strategy.is_bearish_candle(row):
                        entries_today.append((code, sig.name, row["close"]))
                        continue
                if sig.days_waited > self.entry_window:
                    expired.append(code)

            for code in expired:
                pending.pop(code, None)

            if entries_today:
                per_stock = portfolio.cash / len(entries_today)
                for code, name, price in entries_today:
                    pending.pop(code, None)
                    portfolio.buy(code, name, price, date, per_stock)

            # (c) New signals enter pending queue
            if date in signals:
                for code, name in signals[date]:
                    if not portfolio.has_position(code) and code not in pending:
                        pending[code] = PendingSignal(
                            code=code, name=name, signal_date=date,
                        )

            # (d) Record NAV
            market_prices = {}
            for code in portfolio.positions:
                if code in price_lookup and date in price_lookup[code]:
                    market_prices[code] = price_lookup[code][date]["close"]
            nav = portfolio.get_nav(market_prices)
            nav_history.append((date, nav))

        # Force close remaining positions
        if all_dates:
            last_date = all_dates[-1]
            for code in list(portfolio.positions.keys()):
                if code in price_lookup and last_date in price_lookup[code]:
                    portfolio.sell(code, price_lookup[code][last_date]["close"], last_date)

        # Calculate metrics
        metrics = calc_metrics(
            portfolio.closed_trades, nav_history, self.initial_capital,
        )

        return BacktestResult(
            combination_id=self.combination_id,
            combination_label=self.combination.label,
            start_date=self.start_date or (all_dates[0] if all_dates else ""),
            end_date=self.end_date or (all_dates[-1] if all_dates else ""),
            initial_capital=self.initial_capital,
            final_nav=nav_history[-1][1] if nav_history else self.initial_capital,
            trades=portfolio.closed_trades,
            nav_history=nav_history,
            metrics=metrics,
        )

    def _detect_all_signals(
        self,
        stock_data: Dict[str, pd.DataFrame],
        stock_names: Dict[str, str],
        progress_callback=None,
    ) -> Dict[str, List[Tuple[str, str]]]:
        signals: Dict[str, List[Tuple[str, str]]] = {}
        total = len(stock_data)

        for i, (code, df) in enumerate(stock_data.items()):
            if progress_callback:
                progress_callback(i + 1, total, "signal")

            df = df.sort_values("date").reset_index(drop=True)
            if len(df) < self.WARMUP_DAYS:
                continue

            name = stock_names.get(code, "")

            # 向量化扫描：每个因子只需调用一次 scan()
            mask = pd.Series(True, index=df.index)
            for factor in self.factors:
                mask = mask & factor.scan(df)

            # 只考虑 warmup 之后的行
            mask.iloc[: self.WARMUP_DAYS - 1] = False

            # 日期过滤
            if self.start_date:
                mask = mask & (df["date"] >= self.start_date)
            if self.end_date:
                mask = mask & (df["date"] <= self.end_date)

            # 提取信号日期
            for date in df.loc[mask, "date"]:
                signals.setdefault(date, []).append((code, name))

        return signals

    def _get_trading_dates(
        self, stock_data: Dict[str, pd.DataFrame],
    ) -> List[str]:
        all_dates = set()
        for df in stock_data.values():
            all_dates.update(df["date"].tolist())

        dates = sorted(all_dates)

        if self.start_date:
            dates = [d for d in dates if d >= self.start_date]
        if self.end_date:
            dates = [d for d in dates if d <= self.end_date]

        return dates

    def _build_price_lookup(
        self, stock_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, Dict[str, dict]]:
        lookup: Dict[str, Dict[str, dict]] = {}
        for code, df in stock_data.items():
            lookup[code] = {}
            for _, row in df.iterrows():
                lookup[code][row["date"]] = {
                    "open": float(row["open"]),
                    "close": float(row["close"]),
                }
        return lookup
