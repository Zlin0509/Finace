from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from src.storage.local_store import LocalStore


class PortfolioManager:
    """Rebuild portfolio holdings from durable transaction records."""

    def __init__(
        self,
        data_path: Optional[str] = None,
        legacy_data_path: Optional[str] = None,
        store: Optional[LocalStore] = None,
    ):
        resolved_data_path = data_path or os.getenv(
            "FUNDMASTER_DATABASE_PATH", "data/fundmaster.db"
        )
        resolved_backup_path = os.getenv("FUNDMASTER_BACKUP_PATH") or None
        self.store = store or LocalStore(resolved_data_path, resolved_backup_path)
        self.data_path = self.store.database_path
        self.legacy_data_path = Path(
            legacy_data_path
            or os.getenv("FUNDMASTER_LEGACY_PORTFOLIO_PATH", "data/portfolio.json")
        )
        self.migrated_transaction_count = self.store.import_legacy_portfolio(
            self.legacy_data_path
        )

    @property
    def portfolio(self) -> Dict[str, Any]:
        """Compatibility view for callers that previously read the JSON payload."""
        holdings = self._rebuild_holdings()
        return {
            "holdings": holdings,
            "transactions": self.get_transactions(),
        }

    def add_transaction(
        self,
        date: str,
        fund_code: str,
        action: str,
        amount: float,
        price: float,
        fees: float = 0,
    ) -> int:
        """Persist a buy amount or sell share quantity and return its local ID."""
        normalized_action = str(action).strip().lower()
        normalized_code = str(fund_code).strip()
        numeric_amount = float(amount)
        numeric_price = float(price)
        numeric_fees = float(fees)

        if normalized_action == "sell":
            current = self._rebuild_holdings().get(normalized_code, {})
            available_shares = float(current.get("shares", 0))
            if numeric_amount > available_shares + 1e-9:
                raise ValueError(
                    f"卖出份额超过当前持仓：可用 {available_shares:.4f} 份"
                )

        shares = (
            numeric_amount / numeric_price
            if normalized_action == "buy" and numeric_price > 0
            else numeric_amount
        )
        return self.store.add_transaction(
            {
                "date": date,
                "fund_code": normalized_code,
                "action": normalized_action,
                "amount": numeric_amount,
                "price": numeric_price,
                "shares": shares,
                "fees": numeric_fees,
            }
        )

    def get_transactions(self) -> List[Dict[str, Any]]:
        return self.store.list_transactions()

    def get_holdings(self) -> pd.DataFrame:
        holdings = []
        for code, data in self._rebuild_holdings().items():
            shares = float(data["shares"])
            cost = float(data["cost"])
            if shares <= 0:
                continue
            holdings.append(
                {
                    "fund_code": code,
                    "shares": shares,
                    "cost": cost,
                    "unit_cost": cost / shares,
                }
            )
        return pd.DataFrame(
            holdings,
            columns=["fund_code", "shares", "cost", "unit_cost"],
        )

    def export_data(self) -> Dict[str, Any]:
        """Export portfolio data without persisted API credentials."""
        return {
            "format_version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "holdings": self._rebuild_holdings(),
            "transactions": self.get_transactions(),
        }

    def create_backup(self, destination_dir: str | Path | None = None) -> Path:
        return self.store.create_backup(destination_dir)

    def _rebuild_holdings(self) -> Dict[str, Dict[str, float]]:
        holdings: Dict[str, Dict[str, float]] = {}
        for transaction in self.get_transactions():
            code = transaction["fund_code"]
            action = transaction["action"]
            shares = float(transaction["shares"])
            current = holdings.setdefault(code, {"shares": 0.0, "cost": 0.0})

            if action == "buy":
                current["shares"] += shares
                current["cost"] += float(transaction["amount"]) + float(
                    transaction["fees"]
                )
                continue

            previous_shares = current["shares"]
            if previous_shares <= 0:
                continue
            sold_shares = min(shares, previous_shares)
            current["cost"] *= 1 - sold_shares / previous_shares
            current["shares"] = previous_shares - sold_shares
            if current["shares"] <= 1e-9:
                current["shares"] = 0.0
                current["cost"] = 0.0
        return holdings
