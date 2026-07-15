import numpy as np
import pandas as pd
from typing import Dict, List
from scipy.optimize import minimize
from src.data.fund_api import FundDataAPI

class PortfolioOptimizer:
    def __init__(self):
        self.api = FundDataAPI()
        
    def _get_returns_matrix(self, fund_codes: List[str], start_date: str, end_date: str) -> pd.DataFrame:
        """获取所有基金的收益率矩阵"""
        prices = {}
        for code in fund_codes:
            df = self.api.get_fund_nav(code, start_date, end_date)
            if not df.empty:
                df['净值日期'] = pd.to_datetime(df['净值日期'])
                df.set_index('净值日期', inplace=True)
                prices[code] = df['unit_nav']
                
        if not prices:
            return pd.DataFrame()
            
        prices_df = pd.DataFrame(prices)
        prices_df.dropna(inplace=True)
        return prices_df.pct_change().dropna()
        
    def optimize_risk_parity(self, fund_codes: List[str], start_date: str, end_date: str) -> Dict:
        """风险平价组合优化"""
        returns = self._get_returns_matrix(fund_codes, start_date, end_date)
        if returns.empty:
            return {"error": "获取历史数据失败"}
            
        cov_matrix = returns.cov() * 252
        n = len(fund_codes)
        
        # 风险平价目标函数：最小化各项资产风险贡献的方差
        def risk_parity_objective(weights, cov_matrix):
            # 组合方差
            portfolio_var = np.dot(weights.T, np.dot(cov_matrix, weights))
            # 边际风险贡献
            mrc = np.dot(cov_matrix, weights)
            # 风险贡献
            rc = weights * mrc
            # 目标：各项资产风险贡献相等
            target_rc = portfolio_var / n
            return np.sum(np.square(rc - target_rc))
            
        # 约束条件
        constraints = [
            {'type': 'eq', 'fun': lambda x: np.sum(x) - 1.0}  # 权重和为1
        ]
        bounds = tuple((0.0, 1.0) for _ in range(n))  # 不允许做空
        initial_weights = np.array([1.0 / n] * n)
        
        result = minimize(
            risk_parity_objective, 
            initial_weights, 
            args=(cov_matrix,),
            method='SLSQP',
            bounds=bounds,
            constraints=constraints
        )
        
        if result.success:
            weights = {code: float(weight) for code, weight in zip(fund_codes, result.x)}
            
            # 计算优化后组合的预期指标
            exp_return = np.sum(returns.mean() * 252 * result.x)
            exp_vol = np.sqrt(np.dot(result.x.T, np.dot(cov_matrix, result.x)))
            
            return {
                "权重分配": weights,
                "预期年化收益": f"{exp_return * 100:.2f}%",
                "预期年化波动率": f"{exp_vol * 100:.2f}%"
            }
            
        return {"error": "优化求解失败"}
