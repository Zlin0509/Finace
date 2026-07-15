import os
import re
from datetime import date, datetime, time
from typing import Callable, Iterable, Optional
from zoneinfo import ZoneInfo

import pandas as pd
import requests


HITHINK_BASE_URL = "https://fuyao.aicubes.cn"
SNAPSHOT_COLUMNS = [
    "stock_code",
    "ticker",
    "last_price",
    "price_change",
    "change_pct",
    "open",
    "high",
    "low",
    "previous_close",
    "volume",
    "turnover",
]
HISTORY_COLUMNS = ["date", "open", "high", "low", "close", "volume", "turnover"]


class StockDataError(RuntimeError):
    """Actionable error returned by an A-share data provider."""

    def __init__(self, message: str, code: Optional[int] = None):
        super().__init__(message)
        self.code = code


def normalize_a_share_code(value: str) -> str:
    """Normalize common A-share code forms to the provider's 600519.SH form."""
    code = str(value or "").strip().upper()
    if not code:
        raise ValueError("请输入 A 股代码")

    prefixed = re.fullmatch(r"(SH|SZ|BJ)[.\-]?(\d{6})", code)
    if prefixed:
        return f"{prefixed.group(2)}.{prefixed.group(1)}"

    suffixed = re.fullmatch(r"(\d{6})[.\-]?(SH|SZ|BJ)", code)
    if suffixed:
        return f"{suffixed.group(1)}.{suffixed.group(2)}"

    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("A 股代码应为 6 位数字，可带 .SH、.SZ 或 .BJ 后缀")

    if code.startswith(("4", "8", "92")):
        exchange = "BJ"
    elif code.startswith(("5", "6", "9")):
        exchange = "SH"
    elif code.startswith(("0", "1", "2", "3")):
        exchange = "SZ"
    else:
        raise ValueError("无法判断交易所，请输入带 .SH、.SZ 或 .BJ 后缀的完整代码")
    return f"{code}.{exchange}"


class AStockDataAPI:
    """Client for the official Tonghuashun Financial-API A-share endpoints."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: float = 10.0,
        requester: Optional[Callable] = None,
    ):
        self.api_key = api_key if api_key is not None else os.getenv(
            "HITHINK_FINANCE_API_KEY", ""
        )
        self.base_url = (
            os.getenv("HITHINK_FINANCE_BASE_URL", "")
            or base_url
            or HITHINK_BASE_URL
        ).rstrip("/")
        self.timeout_seconds = float(timeout_seconds)
        self.requester = requester or requests.get

    @property
    def configured(self) -> bool:
        return bool(self.api_key.strip())

    def update_config(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        self.api_key = api_key.strip()
        if base_url:
            self.base_url = base_url.rstrip("/")
        if timeout_seconds is not None:
            self.timeout_seconds = float(timeout_seconds)

    def get_snapshot(self, stock_codes: Iterable[str]) -> pd.DataFrame:
        codes = list(dict.fromkeys(normalize_a_share_code(code) for code in stock_codes))
        if not codes:
            return pd.DataFrame(columns=SNAPSHOT_COLUMNS)

        data = self._request(
            "/api/a-share/prices/snapshot",
            params={"thscodes": ",".join(codes)},
        )
        frame = pd.DataFrame(data.get("item") or [])
        if frame.empty:
            return pd.DataFrame(columns=SNAPSHOT_COLUMNS)

        frame = frame.rename(
            columns={
                "thscode": "stock_code",
                "price_change_ratio_pct": "change_pct",
                "open_price": "open",
                "high_price": "high",
                "low_price": "low",
                "prev_price": "previous_close",
            }
        )
        frame = self._ensure_columns(frame, SNAPSHOT_COLUMNS)
        numeric = [
            column
            for column in SNAPSHOT_COLUMNS
            if column not in {"stock_code", "ticker"}
        ]
        frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
        frame.attrs["data_timestamp"] = data.get("timestamp")
        return frame[SNAPSHOT_COLUMNS]

    def get_history(
        self,
        stock_code: str,
        start_date: str | date,
        end_date: str | date,
        adjust: str = "forward",
    ) -> pd.DataFrame:
        code = normalize_a_share_code(stock_code)
        if adjust not in {"none", "forward", "backward"}:
            raise ValueError("adjust 必须是 none、forward 或 backward")

        start = self._as_date(start_date)
        end = self._as_date(end_date)
        if start > end:
            raise ValueError("开始日期不能晚于结束日期")
        if (end - start).days > 3660:
            raise ValueError("同花顺历史行情单次查询不能超过 10 年")

        data = self._request(
            "/api/a-share/prices/historical",
            params={
                "thscode": code,
                "interval": "1d",
                "start": self._date_to_milliseconds(start),
                "end": self._date_to_milliseconds(end, end_of_day=True),
                "adjust": adjust,
            },
        )
        frame = pd.DataFrame(data.get("item") or [])
        if frame.empty:
            return pd.DataFrame(columns=HISTORY_COLUMNS)

        frame = frame.rename(
            columns={
                "date_ms": "date",
                "open_price": "open",
                "high_price": "high",
                "low_price": "low",
                "close_price": "close",
            }
        )
        frame = self._ensure_columns(frame, HISTORY_COLUMNS)
        frame["date"] = pd.to_datetime(
            pd.to_numeric(frame["date"], errors="coerce"), unit="ms", utc=True
        ).dt.tz_convert("Asia/Shanghai").dt.tz_localize(None).dt.normalize()
        numeric = [column for column in HISTORY_COLUMNS if column != "date"]
        frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
        frame = frame.dropna(subset=["date", "close"]).sort_values("date")
        frame.attrs["data_timestamp"] = data.get("timestamp")
        frame.attrs["stock_code"] = code
        frame.attrs["adjust"] = adjust
        return frame[HISTORY_COLUMNS].reset_index(drop=True)

    def _request(self, path: str, params: dict) -> dict:
        if not self.configured:
            raise StockDataError(
                "未配置同花顺行情 API Key，请在全局系统设置中填写"
            )
        try:
            response = self.requester(
                f"{self.base_url}{path}",
                params=params,
                headers={"X-api-key": self.api_key},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise StockDataError(f"A 股行情请求失败: {exc}") from exc
        except (TypeError, ValueError) as exc:
            raise StockDataError("A 股行情接口返回了无法识别的数据") from exc

        if not isinstance(payload, dict):
            raise StockDataError("A 股行情接口返回了无法识别的数据")
        code = payload.get("code")
        if code != 0:
            message = payload.get("message") or "未知错误"
            if code == 2001:
                message = "API Key 缺失或无效"
            elif code == 2003:
                message = "当前 API Key 没有该行情能力，请在同花顺后台开通"
            raise StockDataError(f"同花顺行情接口错误: {message}", code=code)
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _ensure_columns(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
        result = frame.copy()
        for column in columns:
            if column not in result:
                result[column] = pd.NA
        return result

    @staticmethod
    def _as_date(value: str | date) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return datetime.strptime(str(value), "%Y-%m-%d").date()

    @staticmethod
    def _date_to_milliseconds(value: date, end_of_day: bool = False) -> int:
        clock = time.max if end_of_day else time.min
        localized = datetime.combine(value, clock, tzinfo=ZoneInfo("Asia/Shanghai"))
        return int(localized.timestamp() * 1000)
