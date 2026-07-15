import akshare as ak
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import os
import json
from pathlib import Path

class FundDataAPI:
    def __init__(self, cache_dir: str = "data/cache", cache_ttl_hours: int = 24):
        self.cache_dir = Path(cache_dir)
        self.cache_ttl_hours = cache_ttl_hours
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
    def _get_cache_path(self, func_name: str, **kwargs) -> Path:
        """生成缓存文件路径"""
        key_str = "_".join(f"{k}-{v}" for k, v in sorted(kwargs.items()))
        filename = f"{func_name}_{key_str}.json"
        return self.cache_dir / filename
        
    def _read_cache(
        self, cache_path: Path, max_age_hours: Optional[float] = None
    ) -> Optional[pd.DataFrame]:
        """读取有效的缓存"""
        if not cache_path.exists():
            return None
            
        if max_age_hours is not None:
            mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
            if datetime.now() - mtime > timedelta(hours=max_age_hours):
                return None
            
        try:
            return pd.read_json(cache_path)
        except (OSError, ValueError, TypeError):
            return None
            
    def _write_cache(self, df: pd.DataFrame, cache_path: Path):
        """写入缓存"""
        if not df.empty:
            df.to_json(cache_path, orient="records", date_format="iso")
        
    def get_fund_info(self, fund_code: str) -> Dict:
        """获取单个基金基本信息"""
        try:
            # 天天基金的开放式基金列表包含名称
            df = ak.fund_open_fund_daily_em()
            # 由于列表太大，通常我们在初始化时缓存整个列表
            fund_row = df[df["基金代码"] == fund_code]
            if not fund_row.empty:
                return {
                    "基金代码": fund_code,
                    "基金简称": fund_row.iloc[0]["基金简称"],
                    "单位净值": fund_row.iloc[0]["单位净值"],
                    "净值日期": str(fund_row.iloc[0].get("净值日期", ""))
                }
        except Exception as e:
            pass
            
        try:
            # 尝试天天基金场内基金
            df = ak.fund_etf_fund_daily_em()
            fund_row = df[df["基金代码"] == fund_code]
            if not fund_row.empty:
                return {
                    "基金代码": fund_code,
                    "基金简称": fund_row.iloc[0]["基金简称"],
                    "市价": fund_row.iloc[0]["市价"],
                    "类型": "场内ETF"
                }
        except Exception as e:
            pass
            
        return {"基金代码": fund_code, "基金简称": "未知"}
        
    def get_fund_nav(self, fund_code: str, start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """获取基金历史净值"""
        cache_path = self._get_cache_path("fund_nav", code=fund_code)
        
        df = self._read_cache(cache_path, self.cache_ttl_hours)
        stale_df = self._read_cache(cache_path) if df is None else None
        
        if df is None:
            try:
                df = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
                if not df.empty:
                    df["净值日期"] = pd.to_datetime(df["净值日期"]).dt.strftime("%Y-%m-%d")
                    df.rename(columns={"单位净值": "unit_nav", "日增长率": "daily_return"}, inplace=True)
                    self._write_cache(df, cache_path)
                elif stale_df is not None:
                    df = stale_df
                    df.attrs["cache_stale"] = True
                    df.attrs["data_warning"] = "实时数据为空，已回退到历史缓存"
            except Exception as e:
                if stale_df is None:
                    print(f"Error getting nav for {fund_code}: {e}")
                    return pd.DataFrame()
                df = stale_df
                df.attrs["cache_stale"] = True
                df.attrs["data_warning"] = f"实时数据获取失败，已回退到历史缓存: {e}"
                
        if not df.empty and start_date and end_date:
            start_dt = pd.to_datetime(start_date).strftime("%Y-%m-%d")
            end_dt = pd.to_datetime(end_date).strftime("%Y-%m-%d")
            df = df[(df["净值日期"] >= start_dt) & (df["净值日期"] <= end_dt)]
            
        return df

    def get_fund_portfolio(self, fund_code: str, year: str = "2023") -> pd.DataFrame:
        """获取基金持仓(股票/债券)"""
        try:
            df = ak.fund_portfolio_hold_em(symbol=fund_code, date=year)
            return df
        except Exception as e:
            print(f"Error getting portfolio for {fund_code}: {e}")
            return pd.DataFrame()
