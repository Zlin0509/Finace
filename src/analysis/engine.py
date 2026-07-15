import pandas as pd
import numpy as np
from typing import Dict, List
from src.data.fund_api import FundDataAPI

class AnalysisEngine:
    def __init__(self):
        self.api = FundDataAPI()
        
    def calculate_max_drawdown(self, df: pd.DataFrame, value_col: str = 'unit_nav') -> float:
        """计算最大回撤"""
        if df.empty:
            return 0.0
            
        rolling_max = df[value_col].cummax()
        drawdowns = (df[value_col] - rolling_max) / rolling_max
        return float(drawdowns.min())
        
    def calculate_annual_return(self, df: pd.DataFrame, date_col: str = '净值日期', value_col: str = 'unit_nav') -> float:
        """计算年化收益率"""
        if len(df) < 2:
            return 0.0
            
        start_val = df.iloc[0][value_col]
        end_val = df.iloc[-1][value_col]
        
        start_date = pd.to_datetime(df.iloc[0][date_col])
        end_date = pd.to_datetime(df.iloc[-1][date_col])
        days = (end_date - start_date).days
        
        if days == 0:
            return 0.0
            
        total_return = (end_val / start_val) - 1
        annual_return = (1 + total_return) ** (365 / days) - 1
        return float(annual_return)
        
    def calculate_sharpe_ratio(self, df: pd.DataFrame, return_col: str = 'daily_return', risk_free: float = 0.02) -> float:
        """计算夏普比率"""
        if df.empty or len(df) < 2:
            return 0.0
            
        returns = df[return_col].astype(float) / 100  # AKShare的日增长率是百分数
        
        mean_return = returns.mean() * 252  # 年化收益
        volatility = returns.std() * np.sqrt(252)  # 年化波动率
        
        if volatility == 0:
            return 0.0
            
        return float((mean_return - risk_free) / volatility)
        
    def analyze_fund(self, fund_code: str) -> Dict:
        """综合分析单个基金"""
        nav_df = self.api.get_fund_nav(fund_code)
        
        if nav_df.empty:
            return {"error": "无法获取净值数据"}
            
        return {
            "最大回撤": f"{self.calculate_max_drawdown(nav_df) * 100:.2f}%",
            "年化收益": f"{self.calculate_annual_return(nav_df) * 100:.2f}%",
            "夏普比率": f"{self.calculate_sharpe_ratio(nav_df):.2f}",
            "数据天数": len(nav_df)
        }
