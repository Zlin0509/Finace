package quant

import (
	"fmt"
	"math"
	"testing"
	"time"
)

func syntheticPrices(count int) []PricePoint {
	points := make([]PricePoint, count)
	start := time.Date(2015, 1, 1, 0, 0, 0, 0, time.UTC)
	for i := range points {
		trend := 100 * math.Pow(1.00035, float64(i))
		wave := 1 + 0.045*math.Sin(float64(i)/21)
		points[i] = PricePoint{Date: start.AddDate(0, 0, i).Format("2006-01-02"), Price: trend * wave}
	}
	return points
}

func TestBacktestCostsAndSignalDelay(t *testing.T) {
	points := syntheticPrices(700)
	base := BacktestRequest{Strategy: "ma_cross", InitialCapital: 100000, ShortWindow: 10, LongWindow: 40, Prices: points}
	withoutCost, err := Run(base)
	if err != nil {
		t.Fatal(err)
	}
	base.CommissionRate = .0015
	base.SlippageRate = .0005
	withCost, err := Run(base)
	if err != nil {
		t.Fatal(err)
	}
	if withCost.Metrics.FinalEquity >= withoutCost.Metrics.FinalEquity {
		t.Fatal("costs should reduce equity")
	}
	for i := 0; i < 40; i++ {
		if withCost.Curve[i].Position != 0 {
			t.Fatalf("position entered before long window at %d", i)
		}
	}
}

func TestFuturePricesDoNotChangeEarlierPositions(t *testing.T) {
	points := syntheticPrices(500)
	request := BacktestRequest{Strategy: "momentum", MomentumWindow: 40, Prices: points}
	first, err := Run(request)
	if err != nil {
		t.Fatal(err)
	}
	modified := append([]PricePoint(nil), points...)
	for i := 350; i < len(modified); i++ {
		modified[i].Price *= 1 + float64(i-349)*.02
	}
	request.Prices = modified
	second, err := Run(request)
	if err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 350; i++ {
		if first.Curve[i].Position != second.Curve[i].Position {
			t.Fatalf("future changed position at %d", i)
		}
	}
}

func TestWalkForwardProducesOutOfSampleFolds(t *testing.T) {
	request := OptimizeRequest{Backtest: BacktestRequest{Strategy: "ma_cross", InitialCapital: 100000, CommissionRate: .0015, SlippageRate: .0005, Prices: syntheticPrices(1100)}, TrainDays: 488, TestDays: 122, Objective: "balanced", SearchDepth: "fast"}
	result, err := Optimize(request)
	if err != nil {
		t.Fatal(err)
	}
	if result.FoldCount < 4 || result.RecommendedLabel == "" {
		t.Fatalf("unexpected optimize result: %+v", result)
	}
	for index, fold := range result.Folds {
		if fold.TrainEnd >= fold.TestStart {
			t.Fatalf("fold %d overlaps train and test", index)
		}
	}
	compounded, benchmark := 1.0, 1.0
	for _, fold := range result.Folds {
		compounded *= 1 + fold.TestReturn
		benchmark *= 1 + fold.BenchmarkReturn
	}
	if math.Abs(result.OOSReturn-(compounded-1)) > 1e-12 {
		t.Fatalf("combined OOS return %.12f does not match folds %.12f", result.OOSReturn, compounded-1)
	}
	if math.Abs(result.BenchmarkReturn-(benchmark-1)) > 1e-12 {
		t.Fatalf("combined benchmark %.12f does not match folds %.12f", result.BenchmarkReturn, benchmark-1)
	}
}

func TestWalkForwardRejectsUnsafeWindowValues(t *testing.T) {
	prices := syntheticPrices(700)
	for _, test := range []OptimizeRequest{
		{Backtest: BacktestRequest{Strategy: "ma_cross", Prices: prices}, TrainDays: -1, TestDays: 122},
		{Backtest: BacktestRequest{Strategy: "ma_cross", Prices: prices}, TrainDays: 488, TestDays: -1},
	} {
		if _, err := Optimize(test); err == nil {
			t.Fatal("expected invalid window error")
		}
	}
}

func TestWalkForwardDoesNotReorderInputPrices(t *testing.T) {
	prices := syntheticPrices(900)
	prices[0], prices[1] = prices[1], prices[0]
	firstDate := prices[0].Date
	request := OptimizeRequest{Backtest: BacktestRequest{Strategy: "ma_cross", Prices: prices}, TrainDays: 488, TestDays: 122, SearchDepth: "fast"}
	if _, err := Optimize(request); err != nil {
		t.Fatal(err)
	}
	if prices[0].Date != firstDate {
		t.Fatal("optimizer reordered caller-owned price data")
	}
}

func TestCombinedReturnSeriesTracksCrossFoldDrawdown(t *testing.T) {
	metrics := metricsFromReturnSeries(100, []float64{0.10, -0.05, -0.10}, []float64{0.05, 0, -0.02})
	if math.Abs(metrics.MaxDrawdown-(-0.145)) > 1e-12 {
		t.Fatalf("unexpected combined drawdown: %.12f", metrics.MaxDrawdown)
	}
}

func BenchmarkBacktestTenYears(b *testing.B) {
	request := BacktestRequest{Strategy: "ma_cross", InitialCapital: 100000, CommissionRate: .0015, SlippageRate: .0005, ShortWindow: 20, LongWindow: 60, Prices: syntheticPrices(2440)}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if _, err := Run(request); err != nil {
			b.Fatal(fmt.Errorf("run: %w", err))
		}
	}
}

func BenchmarkMetricsTenYears(b *testing.B) {
	request := BacktestRequest{Strategy: "ma_cross", InitialCapital: 100000, CommissionRate: .0015, SlippageRate: .0005, ShortWindow: 20, LongWindow: 60, Prices: syntheticPrices(2440)}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if _, err := RunMetrics(request); err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkWalkForwardFast(b *testing.B) {
	request := OptimizeRequest{Backtest: BacktestRequest{Strategy: "ma_cross", InitialCapital: 100000, CommissionRate: .0015, SlippageRate: .0005, Prices: syntheticPrices(2440)}, TrainDays: 488, TestDays: 122, Objective: "balanced", SearchDepth: "fast"}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if _, err := Optimize(request); err != nil {
			b.Fatal(err)
		}
	}
}
