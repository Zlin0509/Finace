import pandas as pd
import pytest

from src.data.stock_api import (
    AStockDataAPI,
    StockDataError,
    normalize_a_share_code,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_normalize_a_share_code_supports_common_forms():
    assert normalize_a_share_code("600519") == "600519.SH"
    assert normalize_a_share_code("sz000001") == "000001.SZ"
    assert normalize_a_share_code("830799.BJ") == "830799.BJ"

    with pytest.raises(ValueError, match="6 位数字"):
        normalize_a_share_code("贵州茅台")


def test_snapshot_uses_api_key_and_normalizes_provider_fields():
    calls = []

    def requester(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(
            {
                "code": 0,
                "message": "success",
                "data": {
                    "timestamp": 1784044800000,
                    "item": [
                        {
                            "thscode": "600519.SH",
                            "ticker": "600519",
                            "last_price": 1500.5,
                            "price_change": 15.5,
                            "price_change_ratio_pct": 1.04,
                            "open_price": 1480,
                            "high_price": 1510,
                            "low_price": 1475,
                            "prev_price": 1485,
                            "volume": 12345,
                            "turnover": 18500000,
                        }
                    ],
                },
            }
        )

    api = AStockDataAPI(api_key="secret", requester=requester)
    result = api.get_snapshot(["600519", "600519.SH"])

    assert result.iloc[0]["stock_code"] == "600519.SH"
    assert result.iloc[0]["change_pct"] == pytest.approx(1.04)
    assert calls[0][1]["headers"] == {"X-api-key": "secret"}
    assert calls[0][1]["params"]["thscodes"] == "600519.SH"


def test_history_maps_millisecond_dates_and_adjustment():
    calls = []
    date_ms = int(pd.Timestamp("2026-07-14", tz="Asia/Shanghai").timestamp() * 1000)

    def requester(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse(
            {
                "code": 0,
                "message": "success",
                "data": {
                    "timestamp": date_ms,
                    "item": [
                        {
                            "date_ms": date_ms,
                            "open_price": 10,
                            "high_price": 11,
                            "low_price": 9.5,
                            "close_price": 10.5,
                            "volume": 1000,
                            "turnover": 10500,
                        }
                    ],
                },
            }
        )

    api = AStockDataAPI(api_key="secret", requester=requester)
    result = api.get_history("000001", "2026-07-01", "2026-07-15", "backward")

    assert result.iloc[0]["date"] == pd.Timestamp("2026-07-14")
    assert result.iloc[0]["close"] == pytest.approx(10.5)
    assert calls[0][1]["params"]["thscode"] == "000001.SZ"
    assert calls[0][1]["params"]["adjust"] == "backward"


def test_provider_permission_error_is_actionable():
    def requester(_url, **_kwargs):
        return FakeResponse({"code": 2003, "message": "forbidden", "data": None})

    api = AStockDataAPI(api_key="secret", requester=requester)
    with pytest.raises(StockDataError, match="没有该行情能力") as error:
        api.get_snapshot(["600519"])
    assert error.value.code == 2003


def test_missing_api_key_stops_before_network_call():
    api = AStockDataAPI(api_key="", requester=lambda *_args, **_kwargs: None)
    with pytest.raises(StockDataError, match="未配置"):
        api.get_snapshot(["600519"])
