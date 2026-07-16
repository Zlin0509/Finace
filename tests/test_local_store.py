import json
import os
import sqlite3

import pytest

from src.portfolio.manager import PortfolioManager
from src.storage.local_store import LocalStore


def test_transactions_survive_restart_and_rebuild_holdings(tmp_path):
    database = tmp_path / "fundmaster.db"
    manager = PortfolioManager(
        data_path=str(database),
        legacy_data_path=str(tmp_path / "missing.json"),
    )
    first_id = manager.add_transaction(
        "2026-01-02", "510300", "buy", 1000, 2.0, 5
    )
    manager.add_transaction("2026-02-03", "510300", "sell", 100, 2.2, 1)

    restarted = PortfolioManager(
        data_path=str(database),
        legacy_data_path=str(tmp_path / "missing.json"),
    )
    holding = restarted.get_holdings().iloc[0]

    assert first_id == 1
    assert len(restarted.get_transactions()) == 2
    assert holding["shares"] == pytest.approx(400)
    assert holding["cost"] == pytest.approx(804)
    assert holding["unit_cost"] == pytest.approx(2.01)
    if os.name == "posix":
        assert database.stat().st_mode & 0o777 == 0o600


def test_sell_more_than_available_is_rejected(tmp_path):
    manager = PortfolioManager(
        data_path=str(tmp_path / "fundmaster.db"),
        legacy_data_path=str(tmp_path / "missing.json"),
    )
    manager.add_transaction("2026-01-02", "510300", "buy", 100, 2.0)

    with pytest.raises(ValueError, match="卖出份额超过当前持仓"):
        manager.add_transaction("2026-01-03", "510300", "sell", 51, 2.1)

    assert len(manager.get_transactions()) == 1


def test_legacy_json_is_backed_up_and_migrated_once(tmp_path):
    legacy = tmp_path / "portfolio.json"
    legacy.write_text(
        json.dumps(
            {
                "holdings": {},
                "transactions": [
                    {
                        "date": "2025-06-01",
                        "fund_code": "159919",
                        "action": "buy",
                        "amount": 1200,
                        "price": 1.2,
                        "shares": 1000,
                        "fees": 2,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    database = tmp_path / "fundmaster.db"
    store = LocalStore(database, tmp_path / "backups")

    first = PortfolioManager(store=store, legacy_data_path=str(legacy))
    second = PortfolioManager(store=store, legacy_data_path=str(legacy))

    assert first.migrated_transaction_count == 1
    assert second.migrated_transaction_count == 0
    assert store.transaction_count() == 1
    legacy_backup = store.get_metadata("legacy_portfolio_backup")
    assert legacy_backup
    assert (tmp_path / "backups" / legacy_backup.split("/")[-1]).exists()


def test_settings_and_backup_survive_new_store_instance(tmp_path):
    database = tmp_path / "fundmaster.db"
    backup_dir = tmp_path / "backups"
    store = LocalStore(database, backup_dir)
    store.save_settings(
        "llm",
        {
            "provider": "codex_responses",
            "api_key": "local-secret",
            "model": "test-model",
        },
    )

    backup = store.create_backup()
    restarted = LocalStore(database, backup_dir)

    assert restarted.load_settings("llm")["model"] == "test-model"
    assert backup.exists()
    if os.name == "posix":
        assert backup.stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(backup) as connection:
        stored_model = connection.execute(
            """
            SELECT value_json FROM settings
            WHERE namespace = 'llm' AND name = 'model'
            """
        ).fetchone()[0]
    assert json.loads(stored_model) == "test-model"


def test_portfolio_export_excludes_persisted_credentials(tmp_path):
    database = tmp_path / "fundmaster.db"
    store = LocalStore(database)
    store.save_settings("llm", {"api_key": "must-not-export"})
    manager = PortfolioManager(
        store=store,
        legacy_data_path=str(tmp_path / "missing.json"),
    )
    manager.add_transaction("2026-01-02", "510300", "buy", 1000, 2.0)

    exported = json.dumps(manager.export_data())

    assert "must-not-export" not in exported
    assert "510300" in exported
