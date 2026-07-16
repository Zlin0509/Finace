package portfolio

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"time"

	"github.com/Zlin0509/Finace/internal/storage"
)

type Holding struct {
	FundCode string  `json:"fund_code"`
	Shares   float64 `json:"shares"`
	Cost     float64 `json:"cost"`
	UnitCost float64 `json:"unit_cost"`
}

type Snapshot struct {
	Holdings     []Holding             `json:"holdings"`
	Transactions []storage.Transaction `json:"transactions"`
	TotalCost    float64               `json:"total_cost"`
}

type Export struct {
	FormatVersion int                   `json:"format_version"`
	ExportedAt    string                `json:"exported_at"`
	Holdings      []Holding             `json:"holdings"`
	Transactions  []storage.Transaction `json:"transactions"`
}

type Service struct{ store *storage.Store }

func New(store *storage.Store) *Service { return &Service{store: store} }

func (s *Service) Snapshot(ctx context.Context) (Snapshot, error) {
	transactions, err := s.store.Transactions(ctx)
	if err != nil {
		return Snapshot{}, err
	}
	holdings := rebuild(transactions)
	total := 0.0
	for _, holding := range holdings {
		total += holding.Cost
	}
	return Snapshot{Holdings: holdings, Transactions: transactions, TotalCost: total}, nil
}

func (s *Service) Add(ctx context.Context, transaction storage.Transaction) (storage.Transaction, error) {
	if transaction.Action == "sell" {
		snapshot, err := s.Snapshot(ctx)
		if err != nil {
			return storage.Transaction{}, err
		}
		available := 0.0
		for _, holding := range snapshot.Holdings {
			if holding.FundCode == transaction.FundCode {
				available = holding.Shares
				break
			}
		}
		if transaction.Amount > available+1e-9 {
			return storage.Transaction{}, fmt.Errorf("卖出份额超过当前持仓：可用 %.4f 份", available)
		}
	}
	return s.store.AddTransaction(ctx, transaction)
}

func (s *Service) ExportJSON(ctx context.Context) ([]byte, error) {
	snapshot, err := s.Snapshot(ctx)
	if err != nil {
		return nil, err
	}
	payload := Export{FormatVersion: 1, ExportedAt: time.Now().UTC().Format(time.RFC3339), Holdings: snapshot.Holdings, Transactions: snapshot.Transactions}
	return json.MarshalIndent(payload, "", "  ")
}

func rebuild(transactions []storage.Transaction) []Holding {
	type current struct{ shares, cost float64 }
	byCode := map[string]*current{}
	order := make([]string, 0)
	for _, transaction := range transactions {
		item, exists := byCode[transaction.FundCode]
		if !exists {
			item = &current{}
			byCode[transaction.FundCode] = item
			order = append(order, transaction.FundCode)
		}
		if transaction.Action == "buy" {
			item.shares += transaction.Shares
			item.cost += transaction.Amount + transaction.Fees
			continue
		}
		if item.shares <= 0 {
			continue
		}
		sold := math.Min(transaction.Shares, item.shares)
		item.cost *= 1 - sold/item.shares
		item.shares -= sold
		if item.shares <= 1e-9 {
			item.shares, item.cost = 0, 0
		}
	}
	holdings := make([]Holding, 0, len(byCode))
	for _, code := range order {
		item := byCode[code]
		if item.shares <= 0 {
			continue
		}
		holdings = append(holdings, Holding{FundCode: code, Shares: item.shares, Cost: item.cost, UnitCost: item.cost / item.shares})
	}
	return holdings
}
