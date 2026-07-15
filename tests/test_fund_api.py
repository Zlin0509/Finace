import os
from datetime import datetime, timedelta

import pandas as pd

from src.data.fund_api import FundDataAPI


def test_stale_nav_cache_is_used_when_refresh_fails(tmp_path, monkeypatch):
    api = FundDataAPI(cache_dir=tmp_path, cache_ttl_hours=1)
    cache_path = api._get_cache_path("fund_nav", code="510300")
    cached = pd.DataFrame(
        {
            "净值日期": ["2026-07-01", "2026-07-02"],
            "unit_nav": [1.0, 1.1],
            "daily_return": [0.0, 10.0],
        }
    )
    api._write_cache(cached, cache_path)
    old_timestamp = (datetime.now() - timedelta(days=2)).timestamp()
    os.utime(cache_path, (old_timestamp, old_timestamp))

    def fail(**_kwargs):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr("src.data.fund_api.ak.fund_open_fund_info_em", fail)
    result = api.get_fund_nav("510300", "2026-07-01", "2026-07-02")

    assert result["unit_nav"].tolist() == [1.0, 1.1]
    assert result.attrs["cache_stale"] is True
    assert "历史缓存" in result.attrs["data_warning"]
