from __future__ import annotations

import json
import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional


SCHEMA_VERSION = 1


class LocalStoreError(RuntimeError):
    """Actionable local persistence error."""


class LocalStore:
    """SQLite-backed storage for transactions, settings, and backups."""

    def __init__(
        self,
        database_path: str | Path = "data/fundmaster.db",
        backup_dir: str | Path | None = None,
    ):
        self.database_path = Path(database_path).expanduser()
        self.backup_dir = (
            Path(backup_dir).expanduser()
            if backup_dir is not None
            else self.database_path.parent / "backups"
        )
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self._set_private_file_permissions(self.database_path)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            connection.close()
            self._secure_database_files()

    def _initialize(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS metadata (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS transactions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        trade_date TEXT NOT NULL,
                        fund_code TEXT NOT NULL,
                        action TEXT NOT NULL CHECK (action IN ('buy', 'sell')),
                        amount REAL NOT NULL CHECK (amount > 0),
                        price REAL NOT NULL CHECK (price > 0),
                        shares REAL NOT NULL CHECK (shares > 0),
                        fees REAL NOT NULL DEFAULT 0 CHECK (fees >= 0),
                        created_at TEXT NOT NULL
                    );

                    CREATE INDEX IF NOT EXISTS idx_transactions_date
                    ON transactions(trade_date, id);

                    CREATE TABLE IF NOT EXISTS settings (
                        namespace TEXT NOT NULL,
                        name TEXT NOT NULL,
                        value_json TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        PRIMARY KEY (namespace, name)
                    );
                    """
                )
                current_version = connection.execute(
                    "SELECT value FROM metadata WHERE key = 'schema_version'"
                ).fetchone()
                if current_version and int(current_version["value"]) > SCHEMA_VERSION:
                    raise LocalStoreError(
                        "本地数据库来自更新版本，请升级 FundMaster Pro 后再打开"
                    )
                connection.execute(
                    """
                    INSERT INTO metadata(key, value) VALUES('schema_version', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (str(SCHEMA_VERSION),),
                )
                connection.commit()
        except (OSError, sqlite3.Error, ValueError) as exc:
            if isinstance(exc, LocalStoreError):
                raise
            raise LocalStoreError(f"无法初始化本地数据库: {exc}") from exc

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _set_private_file_permissions(path: Path) -> None:
        if os.name == "posix" and path.exists():
            path.chmod(0o600)

    def _secure_database_files(self) -> None:
        self._set_private_file_permissions(self.database_path)
        self._set_private_file_permissions(
            self.database_path.with_name(f"{self.database_path.name}-wal")
        )
        self._set_private_file_permissions(
            self.database_path.with_name(f"{self.database_path.name}-shm")
        )

    def set_metadata(self, key: str, value: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO metadata(key, value) VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            connection.commit()

    def get_metadata(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def add_transaction(self, transaction: Mapping[str, Any]) -> int:
        normalized = self._normalize_transaction(transaction)
        try:
            with self._connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO transactions(
                        trade_date, fund_code, action, amount, price, shares, fees, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        normalized["date"],
                        normalized["fund_code"],
                        normalized["action"],
                        normalized["amount"],
                        normalized["price"],
                        normalized["shares"],
                        normalized["fees"],
                        normalized["created_at"],
                    ),
                )
                connection.commit()
                return int(cursor.lastrowid)
        except sqlite3.Error as exc:
            raise LocalStoreError(f"交易保存失败: {exc}") from exc

    def list_transactions(self) -> List[Dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, trade_date, fund_code, action, amount, price, shares, fees,
                       created_at
                FROM transactions
                ORDER BY trade_date, id
                """
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "date": row["trade_date"],
                "fund_code": row["fund_code"],
                "action": row["action"],
                "amount": float(row["amount"]),
                "price": float(row["price"]),
                "shares": float(row["shares"]),
                "fees": float(row["fees"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def transaction_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM transactions").fetchone()
        return int(row["count"])

    def save_settings(self, namespace: str, values: Mapping[str, Any]) -> None:
        if not namespace.strip():
            raise ValueError("配置命名空间不能为空")
        timestamp = self._now()
        try:
            serialized = [
                (
                    namespace,
                    str(name),
                    json.dumps(value, ensure_ascii=False),
                    timestamp,
                )
                for name, value in values.items()
            ]
        except (TypeError, ValueError) as exc:
            raise LocalStoreError(f"配置无法序列化: {exc}") from exc

        try:
            with self._connect() as connection:
                connection.executemany(
                    """
                    INSERT INTO settings(namespace, name, value_json, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(namespace, name) DO UPDATE SET
                        value_json = excluded.value_json,
                        updated_at = excluded.updated_at
                    """,
                    serialized,
                )
                connection.commit()
        except sqlite3.Error as exc:
            raise LocalStoreError(f"配置保存失败: {exc}") from exc

    def load_settings(self, namespace: str) -> Dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT name, value_json FROM settings
                WHERE namespace = ? ORDER BY name
                """,
                (namespace,),
            ).fetchall()
        values: Dict[str, Any] = {}
        for row in rows:
            try:
                values[row["name"]] = json.loads(row["value_json"])
            except json.JSONDecodeError as exc:
                raise LocalStoreError(
                    f"本地配置 {namespace}.{row['name']} 已损坏"
                ) from exc
        return values

    def import_legacy_portfolio(self, legacy_path: str | Path) -> int:
        legacy = Path(legacy_path).expanduser()
        if not legacy.exists() or self.transaction_count() > 0:
            return 0

        try:
            payload = json.loads(legacy.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LocalStoreError(f"旧持仓文件无法读取: {legacy}: {exc}") from exc

        raw_transactions = payload.get("transactions") or []
        if not raw_transactions:
            raw_transactions = self._synthetic_transactions_from_holdings(
                payload.get("holdings") or {}, legacy
            )
        if not raw_transactions:
            return 0

        normalized = [self._normalize_transaction(item) for item in raw_transactions]
        backup_path = self._copy_legacy_source(legacy)
        try:
            with self._connect() as connection:
                connection.executemany(
                    """
                    INSERT INTO transactions(
                        trade_date, fund_code, action, amount, price, shares, fees, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            item["date"],
                            item["fund_code"],
                            item["action"],
                            item["amount"],
                            item["price"],
                            item["shares"],
                            item["fees"],
                            item["created_at"],
                        )
                        for item in normalized
                    ],
                )
                connection.execute(
                    """
                    INSERT INTO metadata(key, value) VALUES(?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    ("legacy_portfolio_path", str(legacy.resolve())),
                )
                connection.execute(
                    """
                    INSERT INTO metadata(key, value) VALUES(?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    ("legacy_portfolio_backup", str(backup_path.resolve())),
                )
                connection.execute(
                    """
                    INSERT INTO metadata(key, value) VALUES(?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    ("legacy_portfolio_migrated_at", self._now()),
                )
                connection.commit()
        except sqlite3.Error as exc:
            raise LocalStoreError(f"旧持仓迁移失败: {exc}") from exc
        return len(normalized)

    def create_backup(self, destination_dir: str | Path | None = None) -> Path:
        target_dir = (
            Path(destination_dir).expanduser()
            if destination_dir is not None
            else self.backup_dir
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            target_dir.chmod(0o700)

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup_path = target_dir / f"fundmaster-{timestamp}.db"
        try:
            with self._connect() as source:
                destination = sqlite3.connect(backup_path)
                try:
                    source.backup(destination)
                finally:
                    destination.close()
        except (OSError, sqlite3.Error) as exc:
            raise LocalStoreError(f"本地数据库备份失败: {exc}") from exc
        self._set_private_file_permissions(backup_path)
        self.set_metadata("last_backup_path", str(backup_path.resolve()))
        self.set_metadata("last_backup_at", self._now())
        return backup_path

    def backup_if_due(self, max_age_hours: float = 24) -> Optional[Path]:
        if max_age_hours <= 0:
            return self.create_backup()
        if self.transaction_count() == 0 and self.setting_count() == 0:
            return None

        last_backup_at = self.get_metadata("last_backup_at")
        if last_backup_at:
            try:
                last_backup = datetime.fromisoformat(last_backup_at)
                if datetime.now(timezone.utc) - last_backup < timedelta(hours=max_age_hours):
                    return None
            except ValueError:
                pass
        return self.create_backup()

    def setting_count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM settings").fetchone()
        return int(row["count"])

    def describe(self) -> Dict[str, Any]:
        return {
            "database_path": str(self.database_path.resolve()),
            "schema_version": int(self.get_metadata("schema_version", "0") or 0),
            "size_bytes": self.database_path.stat().st_size,
            "transaction_count": self.transaction_count(),
            "setting_count": self.setting_count(),
            "last_backup_path": self.get_metadata("last_backup_path", "") or "",
            "last_backup_at": self.get_metadata("last_backup_at", "") or "",
        }

    @classmethod
    def _normalize_transaction(cls, transaction: Mapping[str, Any]) -> Dict[str, Any]:
        action = str(transaction.get("action", "")).strip().lower()
        if action not in {"buy", "sell"}:
            raise ValueError("交易方向必须是 buy 或 sell")

        fund_code = str(transaction.get("fund_code", "")).strip()
        if not fund_code:
            raise ValueError("基金代码不能为空")

        trade_date = str(transaction.get("date", "")).strip()
        try:
            datetime.strptime(trade_date, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("交易日期必须使用 YYYY-MM-DD 格式") from exc

        amount = float(transaction.get("amount", 0))
        price = float(transaction.get("price", 0))
        fees = float(transaction.get("fees", 0))
        shares = float(
            transaction.get(
                "shares", amount / price if action == "buy" and price > 0 else amount
            )
        )
        if amount <= 0 or price <= 0 or shares <= 0:
            raise ValueError("交易金额、净值和份额必须大于 0")
        if fees < 0:
            raise ValueError("手续费不能为负数")

        return {
            "date": trade_date,
            "fund_code": fund_code,
            "action": action,
            "amount": amount,
            "price": price,
            "shares": shares,
            "fees": fees,
            "created_at": str(transaction.get("created_at") or cls._now()),
        }

    @classmethod
    def _synthetic_transactions_from_holdings(
        cls, holdings: Mapping[str, Any], legacy_path: Path
    ) -> List[Dict[str, Any]]:
        trade_date = datetime.fromtimestamp(legacy_path.stat().st_mtime).strftime("%Y-%m-%d")
        transactions = []
        for fund_code, values in holdings.items():
            shares = float(values.get("shares", 0))
            cost = float(values.get("cost", 0))
            if shares <= 0 or cost <= 0:
                continue
            transactions.append(
                {
                    "date": trade_date,
                    "fund_code": fund_code,
                    "action": "buy",
                    "amount": cost,
                    "price": cost / shares,
                    "shares": shares,
                    "fees": 0,
                }
            )
        return transactions

    def _copy_legacy_source(self, legacy_path: Path) -> Path:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        if os.name == "posix":
            self.backup_dir.chmod(0o700)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = self.backup_dir / f"portfolio-legacy-{timestamp}.json"
        try:
            shutil.copy2(legacy_path, target)
        except OSError as exc:
            raise LocalStoreError(f"旧持仓文件备份失败: {exc}") from exc
        self._set_private_file_permissions(target)
        return target
