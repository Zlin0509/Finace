import numpy as np
import pandas as pd

from src.backtest.engine import BacktestEngine


class StubFundAPI:
    def __init__(self, frame):
        self.frame = frame

    def get_fund_nav(self, _code, start_date=None, end_date=None):
        frame = self.frame.copy()
        if start_date and end_date:
            frame = frame[
                (frame["净值日期"] >= start_date) & (frame["净值日期"] <= end_date)
            ]
        return frame


def make_nav(rows=320):
    dates = pd.bdate_range("2024-01-01", periods=rows)
    trend = np.linspace(0, 0.45, rows)
    cycles = np.sin(np.linspace(0, 18, rows)) * 0.08
    prices = 1.0 + trend + cycles
    return pd.DataFrame(
        {
            "净值日期": dates.strftime("%Y-%m-%d"),
            "unit_nav": prices,
            "daily_return": pd.Series(prices).pct_change().fillna(0) * 100,
        }
    )


def engine_with_data():
    engine = BacktestEngine()
    engine.api = StubFundAPI(make_nav())
    return engine


def test_buy_and_hold_returns_metrics_curve_and_round_trip():
    result = engine_with_data().run_strategy(
        "TEST",
        "2024-01-01",
        "2025-12-31",
        strategy="buy_hold",
        commission_rate=0.001,
        slippage_rate=0.0,
    )

    assert "error" not in result
    assert result["metrics"]["final_equity"] > 100000
    assert result["metrics"]["trade_count"] == 2
    assert result["trades"][0]["action"] == "buy"
    assert result["trades"][-1]["action"] == "sell"
    assert len(result["equity_curve"]) == 320


def test_ma_signal_is_delayed_and_strategy_has_risk_metrics():
    result = engine_with_data().run_strategy(
        "TEST",
        "2024-01-01",
        "2025-12-31",
        strategy="ma_cross",
        short_window=10,
        long_window=30,
    )

    assert "error" not in result
    curve = pd.DataFrame(result["equity_curve"])
    assert curve.loc[:29, "position"].eq(0).all()
    assert -1 <= result["metrics"]["max_drawdown"] <= 0
    assert 0 <= result["metrics"]["exposure"] <= 1
    assert result["metrics"]["trade_count"] >= 2


def test_transaction_costs_reduce_final_equity():
    engine = engine_with_data()
    free = engine.run_strategy(
        "TEST", "2024-01-01", "2025-12-31", strategy="buy_hold", commission_rate=0
    )
    costly = engine.run_strategy(
        "TEST", "2024-01-01", "2025-12-31", strategy="buy_hold", commission_rate=0.01
    )

    assert costly["metrics"]["final_equity"] < free["metrics"]["final_equity"]


def test_invalid_strategy_parameters_return_actionable_error():
    result = engine_with_data().run_strategy(
        "TEST",
        "2024-01-01",
        "2025-12-31",
        strategy="ma_cross",
        short_window=60,
        long_window=20,
    )

    assert result["error"] == "短均线必须不少于 2 天且小于长均线"
