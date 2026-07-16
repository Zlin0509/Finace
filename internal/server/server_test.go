package server

import (
	"bytes"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"
	"time"

	"github.com/Zlin0509/Finace/internal/quant"
	"github.com/Zlin0509/Finace/internal/storage"
)

func TestHTTPPortfolioSettingsAndBacktest(t *testing.T) {
	t.Parallel()
	store, err := storage.Open(filepath.Join(t.TempDir(), "fundmaster.db"), "")
	if err != nil {
		t.Fatal(err)
	}
	defer store.Close()
	handler := New(store, log.New(io.Discard, "", 0)).Handler()

	health := requestJSON(t, handler, http.MethodGet, "/api/health", nil)
	if health["runtime"] != "go" || health["version"] != Version {
		t.Fatalf("unexpected health: %#v", health)
	}
	requestJSON(t, handler, http.MethodPost, "/api/transactions", map[string]any{"date": "2026-01-02", "fund_code": "510300", "action": "buy", "amount": 1000, "price": 2, "fees": 5})
	portfolio := requestJSON(t, handler, http.MethodGet, "/api/portfolio", nil)
	if portfolio["total_cost"].(float64) != 1005 {
		t.Fatalf("unexpected portfolio: %#v", portfolio)
	}

	requestJSON(t, handler, http.MethodPut, "/api/settings/llm", map[string]any{"provider": "codex_responses", "api_key": "secret", "model": "go-model"})
	settings := requestJSON(t, handler, http.MethodGet, "/api/settings/llm", nil)
	if settings["api_key"] != "" || settings["api_key_saved"] != true {
		t.Fatalf("API key was not redacted: %#v", settings)
	}

	prices := make([]quant.PricePoint, 100)
	start := time.Date(2025, 1, 1, 0, 0, 0, 0, time.UTC)
	for i := range prices {
		prices[i] = quant.PricePoint{Date: start.AddDate(0, 0, i).Format("2006-01-02"), Price: 100 + float64(i)*.2}
	}
	result := requestJSON(t, handler, http.MethodPost, "/api/quant/backtest", map[string]any{"strategy": "ma_cross", "short_window": 5, "long_window": 20, "prices": prices})
	if _, ok := result["metrics"]; !ok {
		t.Fatalf("missing metrics: %#v", result)
	}

	page := httptest.NewRecorder()
	handler.ServeHTTP(page, httptest.NewRequest(http.MethodGet, "/", nil))
	if page.Code != http.StatusOK || !bytes.Contains(page.Body.Bytes(), []byte(`id="view-home"`)) {
		t.Fatalf("welcome page was not served: HTTP %d", page.Code)
	}
	asset := httptest.NewRecorder()
	handler.ServeHTTP(asset, httptest.NewRequest(http.MethodGet, "/assets/welcome-miku.webp", nil))
	if asset.Code != http.StatusOK || asset.Header().Get("Content-Type") != "image/webp" || asset.Body.Len() < 1000 {
		t.Fatalf("embedded welcome image was not served: HTTP %d, type %q, bytes %d", asset.Code, asset.Header().Get("Content-Type"), asset.Body.Len())
	}
}

func requestJSON(t *testing.T, handler http.Handler, method, url string, payload any) map[string]any {
	t.Helper()
	var body io.Reader
	if payload != nil {
		encoded, err := json.Marshal(payload)
		if err != nil {
			t.Fatal(err)
		}
		body = bytes.NewReader(encoded)
	}
	request := httptest.NewRequest(method, url, body)
	if payload != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	response := httptest.NewRecorder()
	handler.ServeHTTP(response, request)
	if response.Code >= 300 {
		data, _ := io.ReadAll(response.Body)
		t.Fatalf("HTTP %d: %s", response.Code, data)
	}
	var decoded map[string]any
	if err := json.NewDecoder(response.Body).Decode(&decoded); err != nil {
		t.Fatal(err)
	}
	return decoded
}
