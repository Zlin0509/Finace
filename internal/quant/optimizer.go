package quant

import (
	"errors"
	"fmt"
	"math"
	"sort"
)

type OptimizeRequest struct {
	Backtest    BacktestRequest `json:"backtest"`
	TrainDays   int             `json:"train_days"`
	TestDays    int             `json:"test_days"`
	Objective   string          `json:"objective"`
	SearchDepth string          `json:"search_depth"`
}

type Parameters struct {
	ShortWindow       int     `json:"short_window,omitempty"`
	LongWindow        int     `json:"long_window,omitempty"`
	MomentumWindow    int     `json:"momentum_window,omitempty"`
	MomentumThreshold float64 `json:"momentum_threshold,omitempty"`
}

type Fold struct {
	Fold            int        `json:"fold"`
	TrainStart      string     `json:"train_start"`
	TrainEnd        string     `json:"train_end"`
	TestStart       string     `json:"test_start"`
	TestEnd         string     `json:"test_end"`
	Parameters      Parameters `json:"parameters"`
	ParameterLabel  string     `json:"parameter_label"`
	TrainScore      float64    `json:"train_score"`
	TestScore       float64    `json:"test_score"`
	TrainReturn     float64    `json:"train_return"`
	TestReturn      float64    `json:"test_return"`
	BenchmarkReturn float64    `json:"benchmark_return"`
	Sharpe          float64    `json:"sharpe"`
	MaxDrawdown     float64    `json:"max_drawdown"`
}

type Diagnostics struct {
	ParameterStability float64 `json:"parameter_stability"`
	PositiveFoldRate   float64 `json:"positive_fold_rate"`
	OutperformFoldRate float64 `json:"outperform_fold_rate"`
	OverfitGap         float64 `json:"overfit_gap"`
	ReliabilityScore   float64 `json:"reliability_score"`
	Grade              string  `json:"grade"`
	Verdict            string  `json:"verdict"`
}

type OptimizeResult struct {
	Recommended      Parameters  `json:"recommended_parameters"`
	RecommendedLabel string      `json:"recommended_label"`
	CandidateCount   int         `json:"candidate_count"`
	FoldCount        int         `json:"fold_count"`
	OOSReturn        float64     `json:"oos_return"`
	BenchmarkReturn  float64     `json:"benchmark_return"`
	ExcessReturn     float64     `json:"excess_return"`
	MaxDrawdown      float64     `json:"max_drawdown"`
	Sharpe           float64     `json:"sharpe"`
	Diagnostics      Diagnostics `json:"diagnostics"`
	Folds            []Fold      `json:"folds"`
}

func Optimize(request OptimizeRequest) (OptimizeResult, error) {
	base := defaults(request.Backtest)
	if base.Strategy != "ma_cross" && base.Strategy != "momentum" {
		return OptimizeResult{}, errors.New("optimizer supports ma_cross or momentum")
	}
	if request.TrainDays == 0 {
		request.TrainDays = 488
	}
	if request.TestDays == 0 {
		request.TestDays = 122
	}
	if request.Objective == "" {
		request.Objective = "balanced"
	}
	if request.SearchDepth == "" {
		request.SearchDepth = "standard"
	}
	if request.TrainDays < 40 {
		return OptimizeResult{}, errors.New("train_days must be at least 40")
	}
	if request.TestDays < 20 {
		return OptimizeResult{}, errors.New("test_days must be at least 20")
	}
	if request.Objective != "balanced" && request.Objective != "return" && request.Objective != "sharpe" {
		return OptimizeResult{}, errors.New("objective must be balanced, return, or sharpe")
	}
	if request.SearchDepth != "fast" && request.SearchDepth != "standard" && request.SearchDepth != "deep" {
		return OptimizeResult{}, errors.New("search_depth must be fast, standard, or deep")
	}
	if len(base.Prices) < request.TrainDays+request.TestDays+20 {
		return OptimizeResult{}, errors.New("not enough price points for walk-forward optimization")
	}
	base.Prices = append([]PricePoint(nil), base.Prices...)
	sort.SliceStable(base.Prices, func(i, j int) bool { return base.Prices[i].Date < base.Prices[j].Date })
	if err := validate(base); err != nil {
		return OptimizeResult{}, err
	}
	candidates := candidateGrid(base.Strategy, request.SearchDepth, request.TrainDays)
	if len(candidates) == 0 {
		return OptimizeResult{}, errors.New("no valid parameter candidates")
	}

	folds := make([]Fold, 0)
	oosReturns := make([]float64, 0, len(base.Prices)-request.TrainDays)
	oosBenchmarkReturns := make([]float64, 0, len(base.Prices)-request.TrainDays)
	counts := map[string]int{}
	paramsByKey := map[string]Parameters{}
	for testStart, number := request.TrainDays, 1; testStart < len(base.Prices); testStart, number = testStart+request.TestDays, number+1 {
		testEnd := min(testStart+request.TestDays, len(base.Prices))
		if testEnd-testStart < max(20, request.TestDays/2) {
			break
		}
		train := base.Prices[testStart-request.TrainDays : testStart]
		bestScore := math.Inf(-1)
		var best Parameters
		var bestMetrics Metrics
		for _, candidate := range candidates {
			candidateRequest := applyParameters(base, candidate)
			candidateRequest.Prices = train
			metrics, err := runMetricsPrepared(candidateRequest, train)
			if err != nil {
				continue
			}
			value := objectiveScore(metrics, request.Objective)
			if value > bestScore {
				bestScore, best, bestMetrics = value, candidate, metrics
			}
		}
		if math.IsInf(bestScore, -1) {
			return OptimizeResult{}, errors.New("all parameter candidates failed")
		}

		warmup := warmupDays(base.Strategy, best)
		contextStart := max(0, testStart-warmup-2)
		context := base.Prices[contextStart:testEnd]
		evaluationOffset := testStart - contextStart
		testMetrics, testReturns, benchmarkReturns, err := evaluateSegment(applyParameters(base, best), context, evaluationOffset)
		if err != nil {
			return OptimizeResult{}, err
		}
		label := parameterLabel(base.Strategy, best)
		key := parameterKey(best)
		counts[key]++
		paramsByKey[key] = best
		folds = append(folds, Fold{
			Fold: number, TrainStart: train[0].Date, TrainEnd: train[len(train)-1].Date,
			TestStart: base.Prices[testStart].Date, TestEnd: base.Prices[testEnd-1].Date,
			Parameters: best, ParameterLabel: label, TrainScore: bestScore,
			TestScore: objectiveScore(testMetrics, request.Objective), TrainReturn: bestMetrics.TotalReturn,
			TestReturn: testMetrics.TotalReturn, BenchmarkReturn: testMetrics.BenchmarkReturn,
			Sharpe: testMetrics.SharpeRatio, MaxDrawdown: testMetrics.MaxDrawdown,
		})
		oosReturns = append(oosReturns, testReturns...)
		oosBenchmarkReturns = append(oosBenchmarkReturns, benchmarkReturns...)
	}
	if len(folds) < 2 {
		return OptimizeResult{}, errors.New("fewer than two validation folds")
	}

	keys := make([]string, 0, len(counts))
	for key := range counts {
		keys = append(keys, key)
	}
	sort.Slice(keys, func(i, j int) bool {
		if counts[keys[i]] == counts[keys[j]] {
			return keys[i] < keys[j]
		}
		return counts[keys[i]] > counts[keys[j]]
	})
	recommended := paramsByKey[keys[0]]
	diagnostics := diagnose(folds, counts[keys[0]])
	combined := metricsFromReturnSeries(base.InitialCapital, oosReturns, oosBenchmarkReturns)
	return OptimizeResult{Recommended: recommended, RecommendedLabel: parameterLabel(base.Strategy, recommended), CandidateCount: len(candidates), FoldCount: len(folds), OOSReturn: combined.TotalReturn, BenchmarkReturn: combined.BenchmarkReturn, ExcessReturn: combined.ExcessReturn, MaxDrawdown: combined.MaxDrawdown, Sharpe: combined.SharpeRatio, Diagnostics: diagnostics, Folds: folds}, nil
}

func evaluateSegment(request BacktestRequest, context []PricePoint, offset int) (Metrics, []float64, []float64, error) {
	request = defaults(request)
	prices := make([]float64, len(context))
	for i := range context {
		prices[i] = context[i].Price
	}
	allPositions := positions(request, prices)
	points := context[offset:]
	prices = prices[offset:]
	position := allPositions[offset:]
	if len(points) < 2 {
		return Metrics{}, nil, nil, errors.New("validation segment is too short")
	}
	strategyReturns := make([]float64, len(prices))
	benchmarkReturns := make([]float64, len(prices))
	previous := 0.0
	costRate := request.CommissionRate + request.SlippageRate
	for i := range prices {
		assetReturn := 0.0
		if i > 0 {
			assetReturn = prices[i]/prices[i-1] - 1
		}
		benchmarkReturns[i] = assetReturn
		turnover := math.Abs(position[i] - previous)
		if i == len(prices)-1 && position[i] > 0 {
			turnover += position[i]
		}
		strategyReturns[i] = position[i]*assetReturn - turnover*costRate
		previous = position[i]
	}
	return metricsFromReturnSeries(request.InitialCapital, strategyReturns, benchmarkReturns), strategyReturns, benchmarkReturns, nil
}

func metricsFromReturnSeries(initial float64, strategyReturns, benchmarkReturns []float64) Metrics {
	capital, benchmarkCapital, peak, maxDrawdown := initial, initial, initial, 0.0
	mean, m2 := 0.0, 0.0
	for i, value := range strategyReturns {
		capital *= 1 + value
		if i < len(benchmarkReturns) {
			benchmarkCapital *= 1 + benchmarkReturns[i]
		}
		if capital > peak {
			peak = capital
		}
		if drawdown := capital/peak - 1; drawdown < maxDrawdown {
			maxDrawdown = drawdown
		}
		count := float64(i + 1)
		delta := value - mean
		mean += delta / count
		m2 += delta * (value - mean)
	}
	variance := 0.0
	if len(strategyReturns) > 1 {
		variance = m2 / float64(len(strategyReturns)-1)
	}
	volatility := math.Sqrt(variance) * math.Sqrt(TradingDays)
	sharpe := 0.0
	if volatility > 0 {
		sharpe = (mean*TradingDays - 0.02) / volatility
	}
	total := capital/initial - 1
	benchmark := benchmarkCapital/initial - 1
	periods := math.Max(float64(len(strategyReturns)-1), 1)
	return Metrics{FinalEquity: capital, TotalReturn: total, AnnualReturn: math.Pow(math.Max(capital/initial, 0), TradingDays/periods) - 1, BenchmarkReturn: benchmark, ExcessReturn: total - benchmark, MaxDrawdown: maxDrawdown, SharpeRatio: sharpe, AnnualVolatility: volatility}
}

func candidateGrid(strategy, depth string, trainDays int) []Parameters {
	if strategy == "momentum" {
		windows := []int{20, 40, 60, 90, 120}
		thresholds := []float64{-0.05, 0, 0.05}
		if depth == "fast" {
			windows = []int{40, 60, 90}
			thresholds = []float64{0, 0.05}
		}
		if depth == "deep" {
			windows = []int{10, 20, 30, 40, 60, 90, 120, 180}
			thresholds = []float64{-0.1, -0.05, 0, 0.03, 0.05, 0.1}
		}
		out := make([]Parameters, 0, len(windows)*len(thresholds))
		for _, w := range windows {
			if w >= trainDays/2 {
				continue
			}
			for _, t := range thresholds {
				out = append(out, Parameters{MomentumWindow: w, MomentumThreshold: t})
			}
		}
		return out
	}
	shorts := []int{5, 10, 20, 30, 50}
	longs := []int{40, 60, 90, 120, 180, 240}
	if depth == "fast" {
		return []Parameters{{ShortWindow: 5, LongWindow: 20}, {ShortWindow: 10, LongWindow: 40}, {ShortWindow: 20, LongWindow: 60}, {ShortWindow: 30, LongWindow: 90}, {ShortWindow: 50, LongWindow: 200}}
	}
	if depth == "deep" {
		shorts = []int{3, 5, 8, 10, 15, 20, 30, 40, 50, 60}
		longs = []int{20, 30, 40, 60, 90, 120, 150, 180, 200, 240}
	}
	out := make([]Parameters, 0)
	for _, s := range shorts {
		for _, l := range longs {
			if l > s && l <= trainDays/2 {
				out = append(out, Parameters{ShortWindow: s, LongWindow: l})
			}
		}
	}
	return out
}

func applyParameters(request BacktestRequest, parameters Parameters) BacktestRequest {
	if request.Strategy == "ma_cross" {
		request.ShortWindow = parameters.ShortWindow
		request.LongWindow = parameters.LongWindow
	} else {
		request.MomentumWindow = parameters.MomentumWindow
		request.MomentumThreshold = parameters.MomentumThreshold
	}
	return request
}
func warmupDays(strategy string, p Parameters) int {
	if strategy == "ma_cross" {
		return p.LongWindow
	}
	return p.MomentumWindow
}
func parameterKey(p Parameters) string {
	return fmt.Sprintf("%d:%d:%d:%.4f", p.ShortWindow, p.LongWindow, p.MomentumWindow, p.MomentumThreshold)
}
func parameterLabel(strategy string, p Parameters) string {
	if strategy == "ma_cross" {
		return fmt.Sprintf("MA %d / %d", p.ShortWindow, p.LongWindow)
	}
	return fmt.Sprintf("%d 日 / %+.0f%%", p.MomentumWindow, p.MomentumThreshold*100)
}
func objectiveScore(m Metrics, objective string) float64 {
	if objective == "return" {
		return m.AnnualReturn
	}
	if objective == "sharpe" {
		return m.SharpeRatio
	}
	return m.SharpeRatio + 0.5*m.AnnualReturn + 0.8*m.MaxDrawdown
}

func diagnose(folds []Fold, topCount int) Diagnostics {
	positive, outperform, gap := 0, 0, 0.0
	for _, f := range folds {
		if f.TestReturn > 0 {
			positive++
		}
		if f.TestReturn > f.BenchmarkReturn {
			outperform++
		}
		gap += math.Abs(f.TrainScore - f.TestScore)
	}
	n := float64(len(folds))
	stability := float64(topCount) / n
	positiveRate := float64(positive) / n
	outperformRate := float64(outperform) / n
	gap /= n
	gapScore := math.Max(0, 1-math.Min(gap, 2)/2)
	score := 100 * (0.35*stability + 0.3*positiveRate + 0.25*outperformRate + 0.1*gapScore)
	grade, verdict := "D", "过拟合或样本外表现偏弱"
	if score >= 75 {
		grade, verdict = "A", "参数稳定且样本外表现良好"
	} else if score >= 60 {
		grade, verdict = "B", "具备一定样本外稳定性"
	} else if score >= 45 {
		grade, verdict = "C", "稳定性一般，需要谨慎验证"
	}
	return Diagnostics{ParameterStability: stability, PositiveFoldRate: positiveRate, OutperformFoldRate: outperformRate, OverfitGap: gap, ReliabilityScore: score, Grade: grade, Verdict: verdict}
}
