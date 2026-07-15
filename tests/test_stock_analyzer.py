import pandas as pd
import pytest

from src.analysis.stock_analyzer import (
    analyze_stock_history,
    calculate_holding_contributions,
    normalize_fund_stock_holdings,
)


def test_stock_history_metrics_are_calculated_from_close_prices():
    history = pd.DataFrame(
        {
            "close": [10.0, 11.0, 9.0, 12.0],
            "turnover": [100, 120, 110, 130],
        }
    )
    result = analyze_stock_history(history)

    assert result["period_return"] == pytest.approx(0.2)
    assert result["max_drawdown"] == pytest.approx(9 / 11 - 1)
    assert result["annual_volatility"] > 0
    assert result["average_turnover"] == pytest.approx(115)


def test_latest_fund_holdings_are_normalized_and_joined_to_quotes():
    raw = pd.DataFrame(
        [
            ["600000", "浦发银行", "4.0", 10, 100, "2026年1季度"],
            ["600519", "贵州茅台", "5.5%", 20, 200, "2026年2季度"],
            ["000001", "平安银行", 3.0, 30, 300, "2026年2季度"],
        ],
        columns=["股票代码", "股票名称", "占净值比例", "持股数", "持仓市值", "季度"],
    )
    holdings = normalize_fund_stock_holdings(raw)

    assert holdings["stock_code"].tolist() == ["600519.SH", "000001.SZ"]
    assert holdings["report_period"].nunique() == 1

    quotes = pd.DataFrame(
        {
            "stock_code": ["600519.SH", "000001.SZ"],
            "last_price": [1500, 10],
            "change_pct": [2.0, -1.0],
        }
    )
    result = calculate_holding_contributions(holdings, quotes)

    contribution = result.set_index("stock_code")["contribution_pct_points"]
    assert contribution["600519.SH"] == pytest.approx(0.11)
    assert contribution["000001.SZ"] == pytest.approx(-0.03)
