import re
from typing import Dict

import numpy as np
import pandas as pd

from src.data.stock_api import normalize_a_share_code


def analyze_stock_history(history: pd.DataFrame, trading_days: int = 244) -> Dict:
    if history.empty or len(history) < 2:
        return {
            "period_return": 0.0,
            "annual_volatility": 0.0,
            "max_drawdown": 0.0,
            "average_turnover": 0.0,
        }

    close = pd.to_numeric(history["close"], errors="coerce").dropna()
    if len(close) < 2:
        return {
            "period_return": 0.0,
            "annual_volatility": 0.0,
            "max_drawdown": 0.0,
            "average_turnover": 0.0,
        }

    returns = close.pct_change().dropna()
    drawdown = close / close.cummax() - 1.0
    turnover = pd.to_numeric(
        history.get("turnover", pd.Series(dtype=float)), errors="coerce"
    )
    volatility = returns.std(ddof=1) if len(returns) > 1 else 0.0
    return {
        "period_return": float(close.iloc[-1] / close.iloc[0] - 1.0),
        "annual_volatility": float(volatility * np.sqrt(trading_days)),
        "max_drawdown": float(drawdown.min()),
        "average_turnover": float(turnover.mean()) if turnover.notna().any() else 0.0,
    }


def normalize_fund_stock_holdings(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalize AKShare fund holdings and keep the latest disclosed quarter."""
    columns = [
        "stock_code",
        "stock_name",
        "nav_weight_pct",
        "shares",
        "market_value",
        "report_period",
    ]
    if raw is None or raw.empty:
        return pd.DataFrame(columns=columns)

    aliases = {
        "股票代码": "stock_code",
        "股票名称": "stock_name",
        "占净值比例": "nav_weight_pct",
        "占净值比例（%）": "nav_weight_pct",
        "持股数": "shares",
        "持股数（万股）": "shares",
        "持仓市值": "market_value",
        "持仓市值（万元）": "market_value",
        "季度": "report_period",
    }
    frame = raw.rename(columns=aliases).copy()
    for column in columns:
        if column not in frame:
            frame[column] = pd.NA

    frame["report_period"] = frame["report_period"].astype("string").fillna("")
    report_dates = frame["report_period"].map(_extract_report_date)
    if report_dates.notna().any():
        latest = report_dates.max()
        frame = frame[report_dates == latest].copy()

    frame["stock_code"] = frame["stock_code"].map(_safe_normalize_code)
    frame["nav_weight_pct"] = frame["nav_weight_pct"].map(_number)
    frame["shares"] = frame["shares"].map(_number)
    frame["market_value"] = frame["market_value"].map(_number)
    frame = frame.dropna(subset=["stock_code", "nav_weight_pct"])
    frame = frame[frame["nav_weight_pct"] > 0]
    return (
        frame[columns]
        .sort_values("nav_weight_pct", ascending=False)
        .drop_duplicates("stock_code")
        .reset_index(drop=True)
    )


def calculate_holding_contributions(
    holdings: pd.DataFrame, snapshots: pd.DataFrame
) -> pd.DataFrame:
    columns = list(holdings.columns) + [
        "last_price",
        "change_pct",
        "contribution_pct_points",
    ]
    if holdings.empty or snapshots.empty:
        return pd.DataFrame(columns=columns)

    quotes = snapshots[["stock_code", "last_price", "change_pct"]].copy()
    result = holdings.merge(quotes, on="stock_code", how="left")
    result["contribution_pct_points"] = (
        result["nav_weight_pct"] * result["change_pct"] / 100.0
    )
    return result.sort_values(
        "contribution_pct_points", ascending=False, na_position="last"
    ).reset_index(drop=True)


def _extract_report_date(value: str):
    match = re.search(r"(20\d{2})[^0-9]?(0?[1-4])季度", str(value))
    if match:
        month_day = {"1": "03-31", "2": "06-30", "3": "09-30", "4": "12-31"}
        return pd.Timestamp(f"{match.group(1)}-{month_day[str(int(match.group(2)))]}")
    parsed = pd.to_datetime(value, errors="coerce")
    return parsed if pd.notna(parsed) else pd.NaT


def _safe_normalize_code(value):
    try:
        digits = re.sub(r"\D", "", str(value))[-6:]
        return normalize_a_share_code(digits)
    except ValueError:
        return pd.NA


def _number(value) -> float:
    if pd.isna(value):
        return np.nan
    cleaned = str(value).replace(",", "").replace("%", "").strip()
    return float(cleaned) if cleaned and cleaned not in {"--", "-"} else np.nan
