package storage

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	_ "github.com/mattn/go-sqlite3"
)

const SchemaVersion = 1

type Transaction struct {
	ID        int64   `json:"id"`
	Date      string  `json:"date"`
	FundCode  string  `json:"fund_code"`
	Action    string  `json:"action"`
	Amount    float64 `json:"amount"`
	Price     float64 `json:"price"`
	Shares    float64 `json:"shares"`
	Fees      float64 `json:"fees"`
	CreatedAt string  `json:"created_at"`
}

type Stats struct {
	DatabasePath     string `json:"database_path"`
	SchemaVersion    int    `json:"schema_version"`
	SizeBytes        int64  `json:"size_bytes"`
	TransactionCount int    `json:"transaction_count"`
	SettingCount     int    `json:"setting_count"`
	LastBackupPath   string `json:"last_backup_path"`
	LastBackupAt     string `json:"last_backup_at"`
}

type Store struct {
	db        *sql.DB
	path      string
	backupDir string
}

func Open(path, backupDir string) (*Store, error) {
	if path == "" {
		path = "data/fundmaster.db"
	}
	abs, err := filepath.Abs(path)
	if err != nil {
		return nil, fmt.Errorf("resolve database path: %w", err)
	}
	if backupDir == "" {
		backupDir = filepath.Join(filepath.Dir(abs), "backups")
	}
	if err := os.MkdirAll(filepath.Dir(abs), 0o700); err != nil {
		return nil, fmt.Errorf("create database directory: %w", err)
	}

	dsn := fmt.Sprintf("file:%s?_busy_timeout=5000&_journal_mode=WAL&_foreign_keys=on", filepath.ToSlash(abs))
	db, err := sql.Open("sqlite3", dsn)
	if err != nil {
		return nil, fmt.Errorf("open sqlite database: %w", err)
	}
	db.SetMaxOpenConns(4)
	db.SetMaxIdleConns(2)
	store := &Store{db: db, path: abs, backupDir: backupDir}
	if err := store.migrate(context.Background()); err != nil {
		db.Close()
		return nil, err
	}
	store.secureFiles()
	return store, nil
}

func (s *Store) Close() error {
	err := s.db.Close()
	s.secureFiles()
	return err
}

func (s *Store) Path() string { return s.path }

func (s *Store) migrate(ctx context.Context) error {
	schema := `
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
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(trade_date, id);
CREATE TABLE IF NOT EXISTS settings (
  namespace TEXT NOT NULL,
  name TEXT NOT NULL,
  value_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (namespace, name)
);`
	if _, err := s.db.ExecContext(ctx, schema); err != nil {
		return fmt.Errorf("create sqlite schema: %w", err)
	}
	var current int
	err := s.db.QueryRowContext(ctx, "SELECT CAST(value AS INTEGER) FROM metadata WHERE key='schema_version'").Scan(&current)
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return fmt.Errorf("read schema version: %w", err)
	}
	if current > SchemaVersion {
		return fmt.Errorf("database schema v%d requires a newer FundMaster version", current)
	}
	_, err = s.db.ExecContext(ctx, `
INSERT INTO metadata(key,value) VALUES('schema_version',?)
ON CONFLICT(key) DO UPDATE SET value=excluded.value`, SchemaVersion)
	if err != nil {
		return fmt.Errorf("write schema version: %w", err)
	}
	return nil
}

func (s *Store) AddTransaction(ctx context.Context, in Transaction) (Transaction, error) {
	in.FundCode = strings.TrimSpace(in.FundCode)
	if err := validateTransaction(in); err != nil {
		return Transaction{}, err
	}
	if in.Shares == 0 {
		if in.Action == "buy" {
			in.Shares = in.Amount / in.Price
		} else {
			in.Shares = in.Amount
		}
	}
	if in.CreatedAt == "" {
		in.CreatedAt = time.Now().UTC().Format(time.RFC3339)
	}
	result, err := s.db.ExecContext(ctx, `
INSERT INTO transactions(trade_date,fund_code,action,amount,price,shares,fees,created_at)
VALUES(?,?,?,?,?,?,?,?)`, in.Date, strings.TrimSpace(in.FundCode), in.Action, in.Amount, in.Price, in.Shares, in.Fees, in.CreatedAt)
	if err != nil {
		return Transaction{}, fmt.Errorf("save transaction: %w", err)
	}
	in.ID, _ = result.LastInsertId()
	s.secureFiles()
	return in, nil
}

func (s *Store) Transactions(ctx context.Context) ([]Transaction, error) {
	rows, err := s.db.QueryContext(ctx, `
SELECT id,trade_date,fund_code,action,amount,price,shares,fees,created_at
FROM transactions ORDER BY trade_date,id`)
	if err != nil {
		return nil, fmt.Errorf("query transactions: %w", err)
	}
	defer rows.Close()
	items := make([]Transaction, 0)
	for rows.Next() {
		var item Transaction
		if err := rows.Scan(&item.ID, &item.Date, &item.FundCode, &item.Action, &item.Amount, &item.Price, &item.Shares, &item.Fees, &item.CreatedAt); err != nil {
			return nil, fmt.Errorf("scan transaction: %w", err)
		}
		items = append(items, item)
	}
	return items, rows.Err()
}

func (s *Store) SaveSettings(ctx context.Context, namespace string, values map[string]any) error {
	if strings.TrimSpace(namespace) == "" {
		return errors.New("settings namespace is required")
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return err
	}
	defer tx.Rollback()
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	now := time.Now().UTC().Format(time.RFC3339)
	for _, key := range keys {
		encoded, err := json.Marshal(values[key])
		if err != nil {
			return fmt.Errorf("encode setting %s: %w", key, err)
		}
		_, err = tx.ExecContext(ctx, `
INSERT INTO settings(namespace,name,value_json,updated_at) VALUES(?,?,?,?)
ON CONFLICT(namespace,name) DO UPDATE SET value_json=excluded.value_json,updated_at=excluded.updated_at`, namespace, key, string(encoded), now)
		if err != nil {
			return fmt.Errorf("save setting %s: %w", key, err)
		}
	}
	if err := tx.Commit(); err != nil {
		return err
	}
	s.secureFiles()
	return nil
}

func (s *Store) Settings(ctx context.Context, namespace string) (map[string]any, error) {
	rows, err := s.db.QueryContext(ctx, "SELECT name,value_json FROM settings WHERE namespace=? ORDER BY name", namespace)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	values := map[string]any{}
	for rows.Next() {
		var name, raw string
		if err := rows.Scan(&name, &raw); err != nil {
			return nil, err
		}
		var value any
		if err := json.Unmarshal([]byte(raw), &value); err != nil {
			return nil, fmt.Errorf("decode setting %s.%s: %w", namespace, name, err)
		}
		values[name] = value
	}
	return values, rows.Err()
}

func (s *Store) Stats(ctx context.Context) (Stats, error) {
	stats := Stats{DatabasePath: s.path, SchemaVersion: SchemaVersion}
	if info, err := os.Stat(s.path); err == nil {
		stats.SizeBytes = info.Size()
	}
	if err := s.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM transactions").Scan(&stats.TransactionCount); err != nil {
		return stats, err
	}
	if err := s.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM settings").Scan(&stats.SettingCount); err != nil {
		return stats, err
	}
	stats.LastBackupPath, _ = s.metadata(ctx, "last_backup_path")
	stats.LastBackupAt, _ = s.metadata(ctx, "last_backup_at")
	return stats, nil
}

func (s *Store) Backup(ctx context.Context) (string, error) {
	if err := os.MkdirAll(s.backupDir, 0o700); err != nil {
		return "", err
	}
	target := filepath.Join(s.backupDir, "fundmaster-"+time.Now().Format("20060102-150405.000000000")+".db")
	escaped := strings.ReplaceAll(target, "'", "''")
	if _, err := s.db.ExecContext(ctx, "VACUUM INTO '"+escaped+"'"); err != nil {
		return "", fmt.Errorf("backup sqlite database: %w", err)
	}
	_ = os.Chmod(target, 0o600)
	now := time.Now().UTC().Format(time.RFC3339)
	if err := s.setMetadata(ctx, "last_backup_path", target); err != nil {
		return "", err
	}
	if err := s.setMetadata(ctx, "last_backup_at", now); err != nil {
		return "", err
	}
	return target, nil
}

func (s *Store) BackupIfDue(ctx context.Context, interval time.Duration) (string, error) {
	stats, err := s.Stats(ctx)
	if err != nil || (stats.TransactionCount == 0 && stats.SettingCount == 0) {
		return "", err
	}
	if stats.LastBackupAt != "" {
		last, err := time.Parse(time.RFC3339, stats.LastBackupAt)
		if err == nil && time.Since(last) < interval {
			return "", nil
		}
	}
	return s.Backup(ctx)
}

func (s *Store) MigrateLegacy(ctx context.Context, path string) (int, error) {
	var count int
	if err := s.db.QueryRowContext(ctx, "SELECT COUNT(*) FROM transactions").Scan(&count); err != nil || count > 0 {
		return 0, err
	}
	file, err := os.Open(path)
	if errors.Is(err, os.ErrNotExist) {
		return 0, nil
	}
	if err != nil {
		return 0, err
	}
	defer file.Close()
	var legacy struct {
		Transactions []Transaction `json:"transactions"`
		Holdings     map[string]struct {
			Shares float64 `json:"shares"`
			Cost   float64 `json:"cost"`
		} `json:"holdings"`
	}
	if err := json.NewDecoder(file).Decode(&legacy); err != nil {
		return 0, fmt.Errorf("decode legacy portfolio: %w", err)
	}
	if len(legacy.Transactions) == 0 {
		info, _ := os.Stat(path)
		date := time.Now().Format("2006-01-02")
		if info != nil {
			date = info.ModTime().Format("2006-01-02")
		}
		for code, holding := range legacy.Holdings {
			if holding.Shares <= 0 || holding.Cost <= 0 {
				continue
			}
			legacy.Transactions = append(legacy.Transactions, Transaction{Date: date, FundCode: code, Action: "buy", Amount: holding.Cost, Price: holding.Cost / holding.Shares, Shares: holding.Shares})
		}
	}
	if len(legacy.Transactions) == 0 {
		return 0, nil
	}
	if err := os.MkdirAll(s.backupDir, 0o700); err != nil {
		return 0, err
	}
	backup := filepath.Join(s.backupDir, "portfolio-legacy-"+time.Now().Format("20060102-150405.000000000")+".json")
	if err := copyFile(path, backup); err != nil {
		return 0, err
	}
	_ = os.Chmod(backup, 0o600)

	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return 0, err
	}
	defer tx.Rollback()
	for i := range legacy.Transactions {
		item := legacy.Transactions[i]
		item.FundCode = strings.TrimSpace(item.FundCode)
		if item.Shares == 0 {
			if item.Action == "buy" {
				item.Shares = item.Amount / item.Price
			} else {
				item.Shares = item.Amount
			}
		}
		if item.CreatedAt == "" {
			item.CreatedAt = time.Now().UTC().Format(time.RFC3339)
		}
		if err := validateTransaction(item); err != nil {
			return 0, err
		}
		_, err = tx.ExecContext(ctx, `INSERT INTO transactions(trade_date,fund_code,action,amount,price,shares,fees,created_at) VALUES(?,?,?,?,?,?,?,?)`, item.Date, item.FundCode, item.Action, item.Amount, item.Price, item.Shares, item.Fees, item.CreatedAt)
		if err != nil {
			return 0, err
		}
	}
	if err := tx.Commit(); err != nil {
		return 0, err
	}
	_ = s.setMetadata(ctx, "legacy_portfolio_path", path)
	_ = s.setMetadata(ctx, "legacy_portfolio_backup", backup)
	_ = s.setMetadata(ctx, "legacy_portfolio_migrated_at", time.Now().UTC().Format(time.RFC3339))
	s.secureFiles()
	return len(legacy.Transactions), nil
}

func validateTransaction(in Transaction) error {
	if _, err := time.Parse("2006-01-02", in.Date); err != nil {
		return errors.New("date must use YYYY-MM-DD")
	}
	if len(in.FundCode) != 6 {
		return errors.New("fund_code must be 6 digits")
	}
	for _, char := range in.FundCode {
		if char < '0' || char > '9' {
			return errors.New("fund_code must be 6 digits")
		}
	}
	if in.Action != "buy" && in.Action != "sell" {
		return errors.New("action must be buy or sell")
	}
	if in.Amount <= 0 || in.Price <= 0 || in.Fees < 0 {
		return errors.New("amount and price must be positive; fees cannot be negative")
	}
	return nil
}

func (s *Store) metadata(ctx context.Context, key string) (string, error) {
	var value string
	err := s.db.QueryRowContext(ctx, "SELECT value FROM metadata WHERE key=?", key).Scan(&value)
	if errors.Is(err, sql.ErrNoRows) {
		return "", nil
	}
	return value, err
}

func (s *Store) setMetadata(ctx context.Context, key, value string) error {
	_, err := s.db.ExecContext(ctx, `INSERT INTO metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value`, key, value)
	s.secureFiles()
	return err
}

func (s *Store) secureFiles() {
	_ = os.Chmod(s.path, 0o600)
	_ = os.Chmod(s.path+"-wal", 0o600)
	_ = os.Chmod(s.path+"-shm", 0o600)
}

func copyFile(source, target string) error {
	in, err := os.Open(source)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.OpenFile(target, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o600)
	if err != nil {
		return err
	}
	defer out.Close()
	_, err = io.Copy(out, in)
	return err
}
