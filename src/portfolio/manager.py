import json
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
from datetime import datetime

class PortfolioManager:
    def __init__(self, data_path: str = "data/portfolio.json"):
        self.data_path = Path(data_path)
        self.portfolio = self._load()
        
    def _load(self) -> Dict:
        """加载持仓数据"""
        if not self.data_path.exists():
            return {"holdings": {}, "transactions": []}
            
        with open(self.data_path, "r", encoding="utf-8") as f:
            return json.load(f)
            
    def _save(self):
        """保存持仓数据"""
        with open(self.data_path, "w", encoding="utf-8") as f:
            json.dump(self.portfolio, f, indent=2, ensure_ascii=False)
            
    def add_transaction(self, date: str, fund_code: str, action: str, amount: float, price: float, fees: float = 0):
        """添加交易记录并更新持仓
        
        Args:
            action: 'buy' or 'sell'
        """
        # 记录交易
        tx = {
            "date": date,
            "fund_code": fund_code,
            "action": action,
            "amount": amount, # 交易金额
            "price": price,   # 净值
            "shares": amount / price if action == "buy" else amount, # 买入算份额，卖出传份额
            "fees": fees
        }
        self.portfolio["transactions"].append(tx)
        
        # 更新持仓
        shares = tx["shares"]
        if fund_code not in self.portfolio["holdings"]:
            if action == "buy":
                self.portfolio["holdings"][fund_code] = {
                    "shares": shares,
                    "cost": amount + fees
                }
        else:
            current = self.portfolio["holdings"][fund_code]
            if action == "buy":
                current["shares"] += shares
                current["cost"] += (amount + fees)
            elif action == "sell":
                current["shares"] -= shares
                # 简单处理：按比例减少成本
                if current["shares"] > 0:
                    reduce_ratio = shares / (current["shares"] + shares)
                    current["cost"] *= (1 - reduce_ratio)
                else:
                    current["shares"] = 0
                    current["cost"] = 0
                    
        self._save()
        
    def get_holdings(self) -> pd.DataFrame:
        """获取当前持仓摘要"""
        holdings = []
        for code, data in self.portfolio["holdings"].items():
            if data["shares"] > 0:
                holdings.append({
                    "fund_code": code,
                    "shares": data["shares"],
                    "cost": data["cost"],
                    "unit_cost": data["cost"] / data["shares"] if data["shares"] > 0 else 0
                })
        return pd.DataFrame(holdings)
