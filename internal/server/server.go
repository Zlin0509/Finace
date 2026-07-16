package server

import (
	"context"
	"embed"
	"encoding/json"
	"fmt"
	"io/fs"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/Zlin0509/Finace/internal/market"
	"github.com/Zlin0509/Finace/internal/portfolio"
	"github.com/Zlin0509/Finace/internal/quant"
	"github.com/Zlin0509/Finace/internal/storage"
)

const Version = "0.3.1"

//go:embed static/*
var staticFiles embed.FS

type Server struct {
	store     *storage.Store
	portfolio *portfolio.Service
	market    *market.Client
	logger    *log.Logger
}

func New(store *storage.Store, logger *log.Logger) *Server {
	return &Server{store: store, portfolio: portfolio.New(store), market: market.NewClient(15 * time.Second), logger: logger}
}

func (s *Server) Handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /api/health", s.health)
	mux.HandleFunc("GET /api/version", s.version)
	mux.HandleFunc("GET /api/portfolio", s.getPortfolio)
	mux.HandleFunc("GET /api/transactions", s.getTransactions)
	mux.HandleFunc("POST /api/transactions", s.addTransaction)
	mux.HandleFunc("GET /api/storage", s.storageStats)
	mux.HandleFunc("POST /api/storage/backup", s.backup)
	mux.HandleFunc("GET /api/storage/export", s.exportPortfolio)
	mux.HandleFunc("GET /api/settings/{namespace}", s.getSettings)
	mux.HandleFunc("PUT /api/settings/{namespace}", s.saveSettings)
	mux.HandleFunc("GET /api/funds/{code}/nav", s.fundNAV)
	mux.HandleFunc("POST /api/quant/backtest", s.backtest)
	mux.HandleFunc("POST /api/quant/optimize", s.optimize)
	assets, _ := fs.Sub(staticFiles, "static")
	mux.Handle("/", http.FileServer(http.FS(assets)))
	return s.middleware(mux)
}

func (s *Server) middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		started := time.Now()
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("X-Frame-Options", "DENY")
		w.Header().Set("Referrer-Policy", "no-referrer")
		next.ServeHTTP(w, r)
		if strings.HasPrefix(r.URL.Path, "/api/") {
			s.logger.Printf("%s %s %s", r.Method, r.URL.Path, time.Since(started).Round(time.Millisecond))
		}
	})
}

func (s *Server) health(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]any{"status": "ok", "version": Version, "runtime": "go"})
}
func (s *Server) version(w http.ResponseWriter, _ *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"version": Version, "language": "Go"})
}

func (s *Server) getPortfolio(w http.ResponseWriter, r *http.Request) {
	snapshot, err := s.portfolio.Snapshot(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, snapshot)
}
func (s *Server) getTransactions(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.Transactions(r.Context())
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, items)
}
func (s *Server) addTransaction(w http.ResponseWriter, r *http.Request) {
	var item storage.Transaction
	if err := decodeJSON(w, r, &item); err != nil {
		return
	}
	created, err := s.portfolio.Add(r.Context(), item)
	if err != nil {
		writeError(w, http.StatusBadRequest, err)
		return
	}
	writeJSON(w, http.StatusCreated, created)
}
func (s *Server) storageStats(w http.ResponseWriter, r *http.Request) {
	stats, err := s.store.Stats(r.Context())
	if err != nil {
		writeError(w, 500, err)
		return
	}
	writeJSON(w, 200, stats)
}
func (s *Server) backup(w http.ResponseWriter, r *http.Request) {
	path, err := s.store.Backup(r.Context())
	if err != nil {
		writeError(w, 500, err)
		return
	}
	writeJSON(w, 201, map[string]string{"path": path})
}
func (s *Server) exportPortfolio(w http.ResponseWriter, r *http.Request) {
	payload, err := s.portfolio.ExportJSON(r.Context())
	if err != nil {
		writeError(w, 500, err)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Content-Disposition", "attachment; filename=fundmaster-portfolio.json")
	w.Write(payload)
}

func (s *Server) getSettings(w http.ResponseWriter, r *http.Request) {
	namespace := r.PathValue("namespace")
	if !allowedNamespace(namespace) {
		writeError(w, 404, fmt.Errorf("unknown settings namespace"))
		return
	}
	values, err := s.store.Settings(r.Context(), namespace)
	if err != nil {
		writeError(w, 500, err)
		return
	}
	if _, ok := values["api_key"]; ok {
		values["api_key"] = ""
		values["api_key_saved"] = true
	}
	writeJSON(w, 200, values)
}
func (s *Server) saveSettings(w http.ResponseWriter, r *http.Request) {
	namespace := r.PathValue("namespace")
	if !allowedNamespace(namespace) {
		writeError(w, 404, fmt.Errorf("unknown settings namespace"))
		return
	}
	var values map[string]any
	if err := decodeJSON(w, r, &values); err != nil {
		return
	}
	if key, ok := values["api_key"].(string); ok && key == "" {
		existing, _ := s.store.Settings(r.Context(), namespace)
		if saved, exists := existing["api_key"]; exists {
			values["api_key"] = saved
		}
	}
	if err := s.store.SaveSettings(r.Context(), namespace, values); err != nil {
		writeError(w, 500, err)
		return
	}
	writeJSON(w, 200, map[string]bool{"saved": true})
}

func (s *Server) fundNAV(w http.ResponseWriter, r *http.Request) {
	points, err := s.market.FundNAV(r.Context(), r.PathValue("code"), r.URL.Query().Get("start"), r.URL.Query().Get("end"))
	if err != nil {
		writeError(w, 502, err)
		return
	}
	writeJSON(w, 200, points)
}

type quantRequest struct {
	FundCode          string             `json:"fund_code"`
	Start             string             `json:"start"`
	End               string             `json:"end"`
	Strategy          string             `json:"strategy"`
	InitialCapital    float64            `json:"initial_capital"`
	CommissionRate    float64            `json:"commission_rate"`
	SlippageRate      float64            `json:"slippage_rate"`
	ShortWindow       int                `json:"short_window"`
	LongWindow        int                `json:"long_window"`
	MomentumWindow    int                `json:"momentum_window"`
	MomentumThreshold float64            `json:"momentum_threshold"`
	TrainDays         int                `json:"train_days"`
	TestDays          int                `json:"test_days"`
	Objective         string             `json:"objective"`
	SearchDepth       string             `json:"search_depth"`
	Prices            []quant.PricePoint `json:"prices"`
}

func (q quantRequest) backtestRequest() quant.BacktestRequest {
	return quant.BacktestRequest{Strategy: q.Strategy, InitialCapital: q.InitialCapital, CommissionRate: q.CommissionRate, SlippageRate: q.SlippageRate, ShortWindow: q.ShortWindow, LongWindow: q.LongWindow, MomentumWindow: q.MomentumWindow, MomentumThreshold: q.MomentumThreshold, Prices: q.Prices}
}
func (s *Server) prices(ctx context.Context, q *quantRequest) error {
	if len(q.Prices) > 0 {
		return nil
	}
	points, err := s.market.FundNAV(ctx, q.FundCode, q.Start, q.End)
	if err != nil {
		return err
	}
	q.Prices = points
	return nil
}
func (s *Server) backtest(w http.ResponseWriter, r *http.Request) {
	var request quantRequest
	if err := decodeJSON(w, r, &request); err != nil {
		return
	}
	if err := s.prices(r.Context(), &request); err != nil {
		writeError(w, 502, err)
		return
	}
	result, err := quant.Run(request.backtestRequest())
	if err != nil {
		writeError(w, 400, err)
		return
	}
	writeJSON(w, 200, result)
}
func (s *Server) optimize(w http.ResponseWriter, r *http.Request) {
	var request quantRequest
	if err := decodeJSON(w, r, &request); err != nil {
		return
	}
	if err := s.prices(r.Context(), &request); err != nil {
		writeError(w, 502, err)
		return
	}
	result, err := quant.Optimize(quant.OptimizeRequest{Backtest: request.backtestRequest(), TrainDays: request.TrainDays, TestDays: request.TestDays, Objective: request.Objective, SearchDepth: request.SearchDepth})
	if err != nil {
		writeError(w, 400, err)
		return
	}
	writeJSON(w, 200, result)
}

func decodeJSON(w http.ResponseWriter, r *http.Request, target any) error {
	r.Body = http.MaxBytesReader(w, r.Body, 1<<20)
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		writeError(w, 400, fmt.Errorf("invalid JSON: %w", err))
		return err
	}
	return nil
}
func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}
func writeError(w http.ResponseWriter, status int, err error) {
	writeJSON(w, status, map[string]string{"error": err.Error()})
}
func allowedNamespace(value string) bool {
	return value == "llm" || value == "fund_data" || value == "stock_data"
}
