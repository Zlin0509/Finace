package portfolio

import (
	"context"
	"path/filepath"
	"testing"

	"github.com/Zlin0509/Finace/internal/storage"
)

func TestPortfolioRebuildAndSellValidation(t *testing.T) {
	t.Parallel()
	store, err := storage.Open(filepath.Join(t.TempDir(), "fundmaster.db"), "")
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	service := New(store)
	ctx := context.Background()
	if _, err := service.Add(ctx, storage.Transaction{Date: "2026-01-02", FundCode: "510300", Action: "buy", Amount: 1000, Price: 2, Fees: 5}); err != nil {
		t.Fatal(err)
	}
	if _, err := service.Add(ctx, storage.Transaction{Date: "2026-02-02", FundCode: "510300", Action: "sell", Amount: 100, Price: 2.2}); err != nil {
		t.Fatal(err)
	}
	snapshot, err := service.Snapshot(ctx)
	if err != nil {
		t.Fatal(err)
	}
	if len(snapshot.Holdings) != 1 || snapshot.Holdings[0].Shares != 400 || snapshot.Holdings[0].Cost != 804 {
		t.Fatalf("unexpected snapshot: %+v", snapshot)
	}
	if _, err := service.Add(ctx, storage.Transaction{Date: "2026-02-03", FundCode: "510300", Action: "sell", Amount: 401, Price: 2.2}); err == nil {
		t.Fatal("expected oversell error")
	}
}
