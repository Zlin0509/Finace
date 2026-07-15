import numpy as np
import pandas as pd

from src.backtest.engine import BacktestEngine
from src.strategy.walk_forward import WalkForwardOptimizer


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


def make_market(rows=920):
    dates = pd.bdate_range("2020-01-01", periods=rows)
    trend = np.linspace(0, 0.75, rows)
    medium_cycle = np.sin(np.linspace(0, 26, rows)) * 0.12
    fast_cycle = np.sin(np.linspace(0, 90, rows)) * 0.025
    prices = 1.0 + trend + medium_cycle + fast_cycle
    return pd.DataFrame(
        {"净值日期": dates.strftime("%Y-%m-%d"), "unit_nav": prices}
    )


def optimizer_with_frame(frame):
    engine = BacktestEngine()
    engine.api = StubFundAPI(frame)
    return WalkForwardOptimizer(engine)


def optimize(frame, strategy="ma_cross"):
    return optimizer_with_frame(frame).optimize(
        "TEST",
        frame.iloc[0]["净值日期"],
        frame.iloc[-1]["净值日期"],
        strategy=strategy,
        train_days=240,
        test_days=80,
        search_space="fast",
    )


def test_walk_forward_returns_oos_metrics_and_non_overlapping_folds():
    result = optimize(make_market())

    assert "error" not in result
    assert result["fold_count"] >= 7
    assert result["candidate_count"] >= 4
    assert result["recommended_parameters"]["short_window"] < result[
        "recommended_parameters"
    ]["long_window"]
    assert 0 <= result["diagnostics"]["reliability_score"] <= 100

    for fold in result["folds"]:
        assert fold["train_end"] < fold["test_start"]

    dates = [row["date"] for row in result["oos_curve"]]
    assert dates == sorted(set(dates))


def test_future_prices_do_not_change_first_fold_parameter_selection():
    original = make_market(720)
    altered = original.copy()
    future_start = 240
    future_multiplier = np.linspace(1.0, 3.0, len(altered) - future_start)
    altered.loc[future_start:, "unit_nav"] *= future_multiplier

    original_result = optimize(original)
    altered_result = optimize(altered)

    assert original_result["folds"][0]["parameters"] == altered_result["folds"][0][
        "parameters"
    ]
    assert original_result["folds"][0]["train_score"] == altered_result["folds"][0][
        "train_score"
    ]


def test_momentum_walk_forward_selects_supported_parameters():
    result = optimize(make_market(), strategy="momentum")

    assert "error" not in result
    assert result["recommended_parameters"]["momentum_window"] in {20, 60, 120}
    assert result["recommended_parameters"]["momentum_threshold"] in {-0.03, 0.0, 0.05}


def test_walk_forward_rejects_insufficient_history():
    frame = make_market(300)
    result = optimizer_with_frame(frame).optimize(
        "TEST",
        frame.iloc[0]["净值日期"],
        frame.iloc[-1]["净值日期"],
        train_days=240,
        test_days=80,
    )

    assert "有效数据不足" in result["error"]
