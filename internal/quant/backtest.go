package quant

import (
	"errors"
	"math"
	"sort"
)

const TradingDays = 244.0

type PricePoint struct {
	Date  string  `json:"date"`
	Price float64 `json:"price"`
}

type BacktestRequest struct {
	Strategy          string       `json:"strategy"`
	InitialCapital    float64      `json:"initial_capital"`
	CommissionRate    float64      `json:"commission_rate"`
	SlippageRate      float64      `json:"slippage_rate"`
	ShortWindow       int          `json:"short_window"`
	LongWindow        int          `json:"long_window"`
	MomentumWindow    int          `json:"momentum_window"`
	MomentumThreshold float64      `json:"momentum_threshold"`
	Prices            []PricePoint `json:"prices"`
}

type Metrics struct {
	FinalEquity      float64 `json:"final_equity"`
	TotalReturn      float64 `json:"total_return"`
	AnnualReturn     float64 `json:"annual_return"`
	BenchmarkReturn  float64 `json:"benchmark_return"`
	ExcessReturn     float64 `json:"excess_return"`
	MaxDrawdown      float64 `json:"max_drawdown"`
	SharpeRatio      float64 `json:"sharpe_ratio"`
	AnnualVolatility float64 `json:"annual_volatility"`
	Exposure         float64 `json:"exposure"`
	TradeCount       int     `json:"trade_count"`
}

type CurvePoint struct {
	Date            string  `json:"date"`
	Price           float64 `json:"price"`
	Position        float64 `json:"position"`
	StrategyReturn  float64 `json:"strategy_return"`
	Equity          float64 `json:"equity"`
	BenchmarkEquity float64 `json:"benchmark_equity"`
	Drawdown        float64 `json:"drawdown"`
}

type Trade struct {
	Date          string  `json:"date"`
	Action        string  `json:"action"`
	Price         float64 `json:"price"`
	PositionAfter float64 `json:"position_after"`
	EstimatedCost float64 `json:"estimated_cost"`
}

type BacktestResult struct {
	Metrics Metrics      `json:"metrics"`
	Curve   []CurvePoint `json:"curve"`
	Trades  []Trade      `json:"trades"`
}

func RunMetrics(request BacktestRequest) (Metrics, error) {
	request = defaults(request)
	if err := validate(request); err != nil {
		return Metrics{}, err
	}
	points := append([]PricePoint(nil), request.Prices...)
	sort.SliceStable(points, func(i, j int) bool { return points[i].Date < points[j].Date })
	return runMetricsPrepared(request, points)
}

func Run(request BacktestRequest) (BacktestResult, error) {
	request = defaults(request)
	if err := validate(request); err != nil {
		return BacktestResult{}, err
	}
	points := append([]PricePoint(nil), request.Prices...)
	sort.SliceStable(points, func(i, j int) bool { return points[i].Date < points[j].Date })
	n := len(points)
	prices := make([]float64, n)
	for i, point := range points {
		if point.Price <= 0 {
			return BacktestResult{}, errors.New("price must be positive")
		}
		prices[i] = point.Price
	}
	position := positions(request, prices)
	returns := make([]float64, n)
	equity := make([]float64, n)
	benchmark := make([]float64, n)
	drawdown := make([]float64, n)
	trades := make([]Trade, 0, n/20)
	costRate := request.CommissionRate + request.SlippageRate
	capital := request.InitialCapital
	peak := capital
	previousPosition := 0.0
	exposure := 0.0

	for i := 0; i < n; i++ {
		assetReturn := 0.0
		if i > 0 {
			assetReturn = prices[i]/prices[i-1] - 1
		}
		turnover := math.Abs(position[i] - previousPosition)
		if i == n-1 && position[i] > 0 {
			turnover += position[i]
		}
		returns[i] = position[i]*assetReturn - turnover*costRate
		capital *= 1 + returns[i]
		equity[i] = capital
		benchmark[i] = request.InitialCapital * prices[i] / prices[0]
		if capital > peak {
			peak = capital
		}
		drawdown[i] = capital/peak - 1
		exposure += position[i]
		if position[i] != previousPosition {
			action := "sell"
			if position[i] > previousPosition {
				action = "buy"
			}
			trades = append(trades, Trade{Date: points[i].Date, Action: action, Price: prices[i], PositionAfter: position[i], EstimatedCost: math.Abs(position[i]-previousPosition) * request.InitialCapital * costRate})
		}
		previousPosition = position[i]
	}
	if position[n-1] > 0 {
		trades = append(trades, Trade{Date: points[n-1].Date, Action: "sell", Price: prices[n-1], PositionAfter: 0, EstimatedCost: position[n-1] * request.InitialCapital * costRate})
	}

	metrics := calculateMetrics(request.InitialCapital, prices, returns, equity, drawdown, exposure/float64(n), len(trades))
	curve := make([]CurvePoint, n)
	for i := range points {
		curve[i] = CurvePoint{Date: points[i].Date, Price: prices[i], Position: position[i], StrategyReturn: returns[i], Equity: equity[i], BenchmarkEquity: benchmark[i], Drawdown: drawdown[i]}
	}
	return BacktestResult{Metrics: metrics, Curve: curve, Trades: trades}, nil
}

func positions(request BacktestRequest, prices []float64) []float64 {
	n := len(prices)
	position := make([]float64, n)
	if request.Strategy == "buy_hold" {
		for i := range position {
			position[i] = 1
		}
		return position
	}
	raw := make([]float64, n)
	if request.Strategy == "ma_cross" {
		shortSum, longSum := 0.0, 0.0
		for i, price := range prices {
			shortSum += price
			longSum += price
			if i >= request.ShortWindow {
				shortSum -= prices[i-request.ShortWindow]
			}
			if i >= request.LongWindow {
				longSum -= prices[i-request.LongWindow]
			}
			if i+1 >= request.LongWindow {
				shortMA := shortSum / float64(request.ShortWindow)
				longMA := longSum / float64(request.LongWindow)
				if shortMA > longMA {
					raw[i] = 1
				}
			}
		}
	} else {
		for i := request.MomentumWindow; i < n; i++ {
			momentum := prices[i]/prices[i-request.MomentumWindow] - 1
			if momentum > request.MomentumThreshold {
				raw[i] = 1
			}
		}
	}
	for i := 1; i < n; i++ {
		position[i] = raw[i-1]
	}
	return position
}

func calculateMetrics(initial float64, prices, returns, equity, drawdown []float64, exposure float64, tradeCount int) Metrics {
	n := len(equity)
	total := equity[n-1]/initial - 1
	periods := math.Max(float64(n-1), 1)
	annual := math.Pow(math.Max(equity[n-1]/initial, 0), TradingDays/periods) - 1
	benchmarkReturn := prices[n-1]/prices[0] - 1
	maxDrawdown := 0.0
	for _, value := range drawdown {
		if value < maxDrawdown {
			maxDrawdown = value
		}
	}
	mean := 0.0
	for _, value := range returns {
		mean += value
	}
	mean /= float64(n)
	variance := 0.0
	for _, value := range returns {
		delta := value - mean
		variance += delta * delta
	}
	if n > 1 {
		variance /= float64(n - 1)
	}
	volatility := math.Sqrt(variance) * math.Sqrt(TradingDays)
	sharpe := 0.0
	if volatility > 0 {
		sharpe = (mean*TradingDays - 0.02) / volatility
	}
	return Metrics{FinalEquity: equity[n-1], TotalReturn: total, AnnualReturn: annual, BenchmarkReturn: benchmarkReturn, ExcessReturn: total - benchmarkReturn, MaxDrawdown: maxDrawdown, SharpeRatio: sharpe, AnnualVolatility: volatility, Exposure: exposure, TradeCount: tradeCount}
}

func runMetricsPrepared(request BacktestRequest, points []PricePoint) (Metrics, error) {
	prices := make([]float64, len(points))
	for i := range points {
		if points[i].Price <= 0 {
			return Metrics{}, errors.New("price must be positive")
		}
		prices[i] = points[i].Price
	}
	return metricsFromPositions(request, prices, positions(request, prices)), nil
}

func metricsFromPositions(request BacktestRequest, prices, position []float64) Metrics {
	capital, peak, maxDrawdown := request.InitialCapital, request.InitialCapital, 0.0
	previous, exposure, mean, m2 := 0.0, 0.0, 0.0, 0.0
	tradeCount := 0
	costRate := request.CommissionRate + request.SlippageRate
	for i := range prices {
		assetReturn := 0.0
		if i > 0 {
			assetReturn = prices[i]/prices[i-1] - 1
		}
		turnover := math.Abs(position[i] - previous)
		if position[i] != previous {
			tradeCount++
		}
		if i == len(prices)-1 && position[i] > 0 {
			turnover += position[i]
			tradeCount++
		}
		value := position[i]*assetReturn - turnover*costRate
		capital *= 1 + value
		if capital > peak {
			peak = capital
		}
		drawdown := capital/peak - 1
		if drawdown < maxDrawdown {
			maxDrawdown = drawdown
		}
		count := float64(i + 1)
		delta := value - mean
		mean += delta / count
		m2 += delta * (value - mean)
		exposure += position[i]
		previous = position[i]
	}
	variance := 0.0
	if len(prices) > 1 {
		variance = m2 / float64(len(prices)-1)
	}
	volatility := math.Sqrt(variance) * math.Sqrt(TradingDays)
	sharpe := 0.0
	if volatility > 0 {
		sharpe = (mean*TradingDays - 0.02) / volatility
	}
	periods := math.Max(float64(len(prices)-1), 1)
	total := capital/request.InitialCapital - 1
	benchmark := prices[len(prices)-1]/prices[0] - 1
	return Metrics{
		FinalEquity: capital, TotalReturn: total,
		AnnualReturn:    math.Pow(math.Max(capital/request.InitialCapital, 0), TradingDays/periods) - 1,
		BenchmarkReturn: benchmark, ExcessReturn: total - benchmark, MaxDrawdown: maxDrawdown,
		SharpeRatio: sharpe, AnnualVolatility: volatility, Exposure: exposure / float64(len(prices)), TradeCount: tradeCount,
	}
}

func defaults(request BacktestRequest) BacktestRequest {
	if request.Strategy == "" {
		request.Strategy = "ma_cross"
	}
	if request.InitialCapital == 0 {
		request.InitialCapital = 100000
	}
	if request.ShortWindow == 0 {
		request.ShortWindow = 20
	}
	if request.LongWindow == 0 {
		request.LongWindow = 60
	}
	if request.MomentumWindow == 0 {
		request.MomentumWindow = 60
	}
	return request
}

func validate(request BacktestRequest) error {
	if request.Strategy != "buy_hold" && request.Strategy != "ma_cross" && request.Strategy != "momentum" {
		return errors.New("unsupported strategy")
	}
	if request.InitialCapital <= 0 {
		return errors.New("initial_capital must be positive")
	}
	if request.CommissionRate < 0 || request.SlippageRate < 0 {
		return errors.New("cost rates cannot be negative")
	}
	if request.ShortWindow < 2 || request.LongWindow <= request.ShortWindow {
		return errors.New("long_window must be greater than short_window")
	}
	if request.MomentumWindow < 2 {
		return errors.New("momentum_window must be at least 2")
	}
	minimum := 2
	if request.Strategy == "ma_cross" {
		minimum = request.LongWindow + 2
	}
	if request.Strategy == "momentum" {
		minimum = request.MomentumWindow + 2
	}
	if len(request.Prices) < minimum {
		return errors.New("not enough price points for strategy")
	}
	return nil
}
