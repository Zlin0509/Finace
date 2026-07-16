package storage

import (
	"context"
	"os"
	"path/filepath"
	"testing"
)

func TestStorePersistsTransactionsSettingsAndBackup(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	database := filepath.Join(dir, "fundmaster.db")
	backups := filepath.Join(dir, "backups")
	store, err := Open(database, backups)
	if err != nil {
		t.Fatal(err)
	}
	created, err := store.AddTransaction(context.Background(), Transaction{Date: "2026-01-02", FundCode: "510300", Action: "buy", Amount: 1000, Price: 2, Fees: 5})
	if err != nil {
		t.Fatal(err)
	}
	if created.ID != 1 || created.Shares != 500 {
		t.Fatalf("unexpected transaction: %+v", created)
	}
	if err := store.SaveSettings(context.Background(), "llm", map[string]any{"model": "go-model", "api_key": "local-only"}); err != nil {
		t.Fatal(err)
	}
	backup, err := store.Backup(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(backup); err != nil {
		t.Fatal(err)
	}
	if err := store.Close(); err != nil {
		t.Fatal(err)
	}

	reopened, err := Open(database, backups)
	if err != nil {
		t.Fatal(err)
	}
	defer reopened.Close()
	transactions, err := reopened.Transactions(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	settings, err := reopened.Settings(context.Background(), "llm")
	if err != nil {
		t.Fatal(err)
	}
	if len(transactions) != 1 || settings["model"] != "go-model" {
		t.Fatalf("data did not persist: %#v %#v", transactions, settings)
	}
	if info, _ := os.Stat(database); info.Mode().Perm() != 0o600 {
		t.Fatalf("database mode is %o", info.Mode().Perm())
	}
}

func TestTransactionRejectsNonNumericFundCode(t *testing.T) {
	t.Parallel()
	store, err := Open(filepath.Join(t.TempDir(), "fundmaster.db"), "")
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	_, err = store.AddTransaction(context.Background(), Transaction{Date: "2026-01-02", FundCode: `<script>`, Action: "buy", Amount: 1000, Price: 2})
	if err == nil {
		t.Fatal("expected invalid fund code to be rejected")
	}
}

func TestMigrateLegacyJSONOnce(t *testing.T) {
	t.Parallel()
	dir := t.TempDir()
	legacy := filepath.Join(dir, "portfolio.json")
	payload := `{"holdings":{},"transactions":[{"date":"2025-01-01","fund_code":"159919","action":"buy","amount":1200,"price":1.2,"shares":1000,"fees":2}]}`
	if err := os.WriteFile(legacy, []byte(payload), 0o600); err != nil {
		t.Fatal(err)
	}
	store, err := Open(filepath.Join(dir, "fundmaster.db"), filepath.Join(dir, "backups"))
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	first, err := store.MigrateLegacy(context.Background(), legacy)
	if err != nil {
		t.Fatal(err)
	}
	second, err := store.MigrateLegacy(context.Background(), legacy)
	if err != nil {
		t.Fatal(err)
	}
	if first != 1 || second != 0 {
		t.Fatalf("migration counts %d %d", first, second)
	}
}
