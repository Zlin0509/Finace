from typing import Dict

import numpy as np
import pandas as pd

from src.analysis.engine import AnalysisEngine
from src.data.fund_api import FundDataAPI


STRATEGY_LABELS = {
    "buy_hold": "买入并持有",
    "ma_cross": "双均线趋势",
    "momentum": "动量轮动",
}


class BacktestEngine:
    def __init__(self, trading_days: int = 244, risk_free_rate: float = 0.02):
        self.api = FundDataAPI()
        self.analyzer = AnalysisEngine()
        self.trading_days = trading_days
        self.risk_free_rate = risk_free_rate

    def run_strategy(
        self,
        fund_code: str,
        start_date: str,
        end_date: str,
        strategy: str = "ma_cross",
        initial_capital: float = 100000,
        commission_rate: float = 0.0015,
        slippage_rate: float = 0.0005,
        short_window: int = 20,
        long_window: int = 60,
        momentum_window: int = 60,
        momentum_threshold: float = 0.0,
    ) -> Dict:
        """Run a long-or-cash strategy against fund NAV history.

        Signals are shifted by one trading day so a close-based signal can only
        affect the following day's return. Costs apply whenever exposure changes
        and when the final position is liquidated.
        """
        validation_error = self._validate_strategy_inputs(
            strategy,
            initial_capital,
            commission_rate,
            slippage_rate,
            short_window,
            long_window,
            momentum_window,
        )
        if validation_error:
            return {"error": validation_error}

        nav = self._load_nav(fund_code, start_date, end_date)
        if nav.empty:
            return {"error": "无法获取回测期间数据"}

        minimum_rows = 2
        if strategy == "ma_cross":
            minimum_rows = long_window + 2
        elif strategy == "momentum":
            minimum_rows = momentum_window + 2
        if len(nav) < minimum_rows:
            return {"error": f"有效数据不足，当前策略至少需要 {minimum_rows} 个交易日"}

        prices = nav["unit_nav"].astype(float)
        asset_returns = prices.pct_change().fillna(0.0)

        if strategy == "buy_hold":
            position = pd.Series(1.0, index=prices.index)
            short_ma = pd.Series(np.nan, index=prices.index)
            long_ma = pd.Series(np.nan, index=prices.index)
            momentum = pd.Series(np.nan, index=prices.index)
        elif strategy == "ma_cross":
            short_ma = prices.rolling(short_window, min_periods=short_window).mean()
            long_ma = prices.rolling(long_window, min_periods=long_window).mean()
            raw_signal = ((short_ma > long_ma) & long_ma.notna()).astype(float)
            position = raw_signal.shift(1).fillna(0.0)
            momentum = pd.Series(np.nan, index=prices.index)
        else:
            momentum = prices.pct_change(momentum_window)
            raw_signal = (momentum > momentum_threshold).astype(float)
            position = raw_signal.shift(1).fillna(0.0)
            short_ma = pd.Series(np.nan, index=prices.index)
            long_ma = pd.Series(np.nan, index=prices.index)

        position_changes = position.diff().fillna(position)
        turnover = position_changes.abs()
        if position.iloc[-1] > 0:
            turnover.iloc[-1] += position.iloc[-1]

        cost_rate = commission_rate + slippage_rate
        strategy_returns = position * asset_returns - turnover * cost_rate
        equity = initial_capital * (1.0 + strategy_returns).cumprod()
        benchmark_equity = initial_capital * (prices / prices.iloc[0])
        drawdown = equity / equity.cummax() - 1.0

        trades = self._build_trades(position_changes, position, prices, cost_rate, initial_capital)
        metrics = self._calculate_metrics(
            strategy_returns,
            equity,
            benchmark_equity,
            drawdown,
            position,
            trades,
            initial_capital,
        )

        curve = pd.DataFrame(
            {
                "date": prices.index.strftime("%Y-%m-%d"),
                "unit_nav": prices.values,
                "position": position.values,
                "strategy_return": strategy_returns.values,
                "equity": equity.values,
                "benchmark_equity": benchmark_equity.values,
                "drawdown": drawdown.values,
                "short_ma": short_ma.values,
                "long_ma": long_ma.values,
                "momentum": momentum.values,
            }
        )

        return {
            "fund_code": fund_code,
            "strategy": strategy,
            "strategy_name": STRATEGY_LABELS[strategy],
            "start_date": curve.iloc[0]["date"],
            "end_date": curve.iloc[-1]["date"],
            "metrics": metrics,
            "equity_curve": curve.replace({np.nan: None}).to_dict(orient="records"),
            "trades": trades,
            "parameters": {
                "initial_capital": initial_capital,
                "commission_rate": commission_rate,
                "slippage_rate": slippage_rate,
                "short_window": short_window,
                "long_window": long_window,
                "momentum_window": momentum_window,
                "momentum_threshold": momentum_threshold,
            },
            "data_warning": nav.attrs.get("data_warning", ""),
        }

    def _load_nav(self, fund_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        nav = self.api.get_fund_nav(fund_code, start_date, end_date)
        if nav.empty or "净值日期" not in nav or "unit_nav" not in nav:
            return pd.DataFrame()
        source_attrs = dict(nav.attrs)
        nav = nav[["净值日期", "unit_nav"]].copy()
        nav["净值日期"] = pd.to_datetime(nav["净值日期"], errors="coerce")
        nav["unit_nav"] = pd.to_numeric(nav["unit_nav"], errors="coerce")
        nav = nav.dropna().drop_duplicates("净值日期").sort_values("净值日期")
        nav = nav[nav["unit_nav"] > 0].set_index("净值日期")
        nav.attrs.update(source_attrs)
        return nav

    @staticmethod
    def _validate_strategy_inputs(
        strategy,
        initial_capital,
        commission_rate,
        slippage_rate,
        short_window,
        long_window,
        momentum_window,
    ) -> str:
        if strategy not in STRATEGY_LABELS:
            return f"不支持的策略: {strategy}"
        if initial_capital <= 0:
            return "初始资金必须大于 0"
        if not 0 <= commission_rate <= 0.05 or not 0 <= slippage_rate <= 0.05:
            return "手续费率和滑点率必须在 0% 到 5% 之间"
        if short_window < 2 or long_window < 3 or short_window >= long_window:
            return "短均线必须不少于 2 天且小于长均线"
        if momentum_window < 2:
            return "动量观察期必须不少于 2 天"
        return ""

    def _calculate_metrics(
        self,
        returns: pd.Series,
        equity: pd.Series,
        benchmark_equity: pd.Series,
        drawdown: pd.Series,
        position: pd.Series,
        trades,
        initial_capital: float,
    ) -> Dict:
        total_return = equity.iloc[-1] / initial_capital - 1.0
        benchmark_return = benchmark_equity.iloc[-1] / benchmark_equity.iloc[0] - 1.0
        years = max((equity.index[-1] - equity.index[0]).days / 365.25, 1 / 365.25)
        annual_return = (equity.iloc[-1] / initial_capital) ** (1 / years) - 1.0
        annual_volatility = returns.std(ddof=1) * np.sqrt(self.trading_days)
        sharpe = (
            (returns.mean() * self.trading_days - self.risk_free_rate) / annual_volatility
            if annual_volatility > 0
            else 0.0
        )
        max_drawdown = drawdown.min()
        calmar = annual_return / abs(max_drawdown) if max_drawdown < 0 else 0.0
        active_returns = returns[position > 0]
        win_rate = (active_returns > 0).mean() if not active_returns.empty else 0.0

        return {
            "initial_capital": float(initial_capital),
            "final_equity": float(equity.iloc[-1]),
            "total_return": float(total_return),
            "annual_return": float(annual_return),
            "annual_volatility": float(annual_volatility),
            "sharpe_ratio": float(sharpe),
            "max_drawdown": float(max_drawdown),
            "calmar_ratio": float(calmar),
            "win_rate": float(win_rate),
            "exposure": float(position.mean()),
            "benchmark_return": float(benchmark_return),
            "excess_return": float(total_return - benchmark_return),
            "trade_count": len(trades),
        }

    @staticmethod
    def _build_trades(
        changes: pd.Series,
        position: pd.Series,
        prices: pd.Series,
        cost_rate: float,
        initial_capital: float,
    ):
        trades = []
        for date, change in changes[changes != 0].items():
            action = "buy" if change > 0 else "sell"
            trades.append(
                {
                    "date": date.strftime("%Y-%m-%d"),
                    "action": action,
                    "price": float(prices.loc[date]),
                    "position_after": float(position.loc[date]),
                    "estimated_cost": float(abs(change) * initial_capital * cost_rate),
                }
            )

        if position.iloc[-1] > 0:
            trades.append(
                {
                    "date": position.index[-1].strftime("%Y-%m-%d"),
                    "action": "sell",
                    "price": float(prices.iloc[-1]),
                    "position_after": 0.0,
                    "estimated_cost": float(position.iloc[-1] * initial_capital * cost_rate),
                }
            )
        return trades

    def run_dca(
        self,
        fund_code: str,
        start_date: str,
        end_date: str,
        amount: float = 1000,
        freq: str = "M",
        mode: str = "normal",
        ma_window: int = 250,
    ) -> Dict:
        """Run a periodic investment backtest."""
        nav_df = self.api.get_fund_nav(fund_code, start_date, end_date)
        if nav_df.empty:
            return {"error": "无法获取回测期间数据"}

        data_warning = nav_df.attrs.get("data_warning", "")
        nav_df = nav_df.copy()
        nav_df["净值日期"] = pd.to_datetime(nav_df["净值日期"])
        nav_df.set_index("净值日期", inplace=True)
        nav_df.sort_index(inplace=True)

        if mode == "ma":
            nav_df["ma"] = nav_df["unit_nav"].rolling(window=ma_window, min_periods=1).mean()

        invest_dates = pd.date_range(
            start=start_date,
            end=end_date,
            freq="MS" if freq == "M" else "W-MON",
        )
        total_shares = 0.0
        total_cost = 0.0
        history = []

        for date in invest_dates:
            available_dates = nav_df.index[nav_df.index >= date]
            if len(available_dates) == 0:
                continue

            trade_date = available_dates[0]
            price = float(nav_df.loc[trade_date, "unit_nav"])
            current_amount = float(amount)
            if mode == "ma":
                ma_price = float(nav_df.loc[trade_date, "ma"])
                if price < ma_price * 0.8:
                    current_amount = amount * 2.0
                elif price < ma_price * 0.9:
                    current_amount = amount * 1.5
                elif price >= ma_price * 1.1:
                    current_amount = amount * 0.5
                elif price >= ma_price:
                    current_amount = amount * 0.8

            shares = current_amount / price
            total_shares += shares
            total_cost += current_amount
            history.append(
                {
                    "date": trade_date.strftime("%Y-%m-%d"),
                    "price": price,
                    "shares": shares,
                    "cost": current_amount,
                    "total_shares": total_shares,
                    "total_cost": total_cost,
                    "market_value": total_shares * price,
                }
            )

        if not history:
            return {"error": "无有效定投记录"}

        final_price = float(nav_df.iloc[-1]["unit_nav"])
        final_value = total_shares * final_price
        total_return = final_value / total_cost - 1.0
        return {
            "总投入": total_cost,
            "期末市值": final_value,
            "总收益率": f"{total_return * 100:.2f}%",
            "总份额": total_shares,
            "定投期数": len(history),
            "历史详情": history,
            "data_warning": data_warning,
        }
