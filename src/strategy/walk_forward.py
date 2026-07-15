from collections import Counter, defaultdict
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from src.backtest.engine import BacktestEngine, STRATEGY_LABELS


OBJECTIVE_LABELS = {
    "balanced": "稳健均衡",
    "sharpe": "夏普优先",
    "return": "收益优先",
}


class WalkForwardOptimizer:
    """Rolling parameter selection with strictly out-of-sample evaluation."""

    def __init__(self, engine: Optional[BacktestEngine] = None):
        self.engine = engine or BacktestEngine()
        self.trading_days = self.engine.trading_days
        self.risk_free_rate = self.engine.risk_free_rate

    def optimize(
        self,
        fund_code: str,
        start_date: str,
        end_date: str,
        strategy: str = "ma_cross",
        initial_capital: float = 100000,
        commission_rate: float = 0.0015,
        slippage_rate: float = 0.0005,
        train_days: int = 488,
        test_days: int = 122,
        objective: str = "balanced",
        search_space: str = "standard",
    ) -> Dict:
        error = self._validate_inputs(
            strategy, initial_capital, commission_rate, slippage_rate,
            train_days, test_days, objective, search_space,
        )
        if error:
            return {"error": error}

        nav = self.engine._load_nav(fund_code, start_date, end_date)
        if nav.empty:
            return {"error": "无法获取自优化区间的净值数据"}
        required_rows = train_days + test_days + 20
        if len(nav) < required_rows:
            return {"error": f"有效数据不足：至少需要 {required_rows} 个交易日，当前仅 {len(nav)} 个"}

        candidates = self._parameter_grid(strategy, search_space, train_days)
        if not candidates:
            return {"error": "当前训练窗口无法生成有效参数组合"}

        prices = nav["unit_nav"].astype(float)
        cost_rate = commission_rate + slippage_rate
        folds = []
        oos_returns = []
        oos_benchmark_returns = []
        oos_positions = []
        parameter_test_scores = defaultdict(list)

        test_start_idx = train_days
        fold_number = 1
        while test_start_idx < len(prices):
            test_end_idx = min(test_start_idx + test_days, len(prices))
            if test_end_idx - test_start_idx < max(20, test_days // 2):
                break

            train_start_idx = test_start_idx - train_days
            train_prices = prices.iloc[train_start_idx:test_start_idx]
            best = self._select_candidate(
                train_prices, strategy, candidates, cost_rate, initial_capital, objective
            )

            warmup = self._warmup_days(strategy, best["parameters"])
            context_start_idx = max(train_start_idx, test_start_idx - warmup - 2)
            context_prices = prices.iloc[context_start_idx:test_end_idx]
            test_start_date = prices.index[test_start_idx]
            test_end_date = prices.index[test_end_idx - 1]
            test_result = self._simulate(
                context_prices,
                strategy,
                best["parameters"],
                cost_rate,
                initial_capital,
                evaluation_start=test_start_date,
                evaluation_end=test_end_date,
            )
            test_score = self._score(test_result["metrics"], objective)
            parameter_key = self._parameter_key(best["parameters"])
            parameter_test_scores[parameter_key].append(test_score)

            folds.append({
                "fold": fold_number,
                "train_start": train_prices.index[0].strftime("%Y-%m-%d"),
                "train_end": train_prices.index[-1].strftime("%Y-%m-%d"),
                "test_start": test_start_date.strftime("%Y-%m-%d"),
                "test_end": test_end_date.strftime("%Y-%m-%d"),
                "parameters": best["parameters"],
                "parameter_label": self.parameter_label(strategy, best["parameters"]),
                "train_score": float(best["score"]),
                "test_score": float(test_score),
                "train_return": best["metrics"]["total_return"],
                "test_return": test_result["metrics"]["total_return"],
                "benchmark_return": test_result["metrics"]["benchmark_return"],
                "test_sharpe": test_result["metrics"]["sharpe_ratio"],
                "test_max_drawdown": test_result["metrics"]["max_drawdown"],
                "trade_count": test_result["metrics"]["trade_count"],
            })
            oos_returns.append(test_result["returns"])
            oos_benchmark_returns.append(test_result["benchmark_returns"])
            oos_positions.append(test_result["position"])
            fold_number += 1
            test_start_idx += test_days

        if len(folds) < 2:
            return {"error": "样本外窗口少于 2 个，请扩大日期范围或缩短训练窗口"}

        combined_returns = pd.concat(oos_returns).sort_index()
        combined_benchmark = pd.concat(oos_benchmark_returns).sort_index()
        combined_position = pd.concat(oos_positions).sort_index()
        combined_metrics = self._metrics(
            combined_returns,
            combined_benchmark,
            combined_position,
            initial_capital,
            trade_count=sum(fold["trade_count"] for fold in folds),
        )

        selected_keys = [self._parameter_key(fold["parameters"]) for fold in folds]
        counts = Counter(selected_keys)
        recommended_key = max(
            counts,
            key=lambda key: (counts[key], float(np.mean(parameter_test_scores[key]))),
        )
        recommended_parameters = next(
            fold["parameters"] for fold in reversed(folds)
            if self._parameter_key(fold["parameters"]) == recommended_key
        )

        frequencies = []
        for key, count in counts.most_common():
            parameters = next(
                fold["parameters"] for fold in folds
                if self._parameter_key(fold["parameters"]) == key
            )
            frequencies.append({
                "parameter_label": self.parameter_label(strategy, parameters),
                "count": count,
                "share": count / len(folds),
                "mean_test_score": float(np.mean(parameter_test_scores[key])),
            })

        diagnostics = self._diagnostics(folds, combined_metrics, counts)
        equity = initial_capital * (1.0 + combined_returns).cumprod()
        benchmark_equity = initial_capital * (1.0 + combined_benchmark).cumprod()
        drawdown = equity / equity.cummax() - 1.0
        oos_curve = pd.DataFrame({
            "date": combined_returns.index.strftime("%Y-%m-%d"),
            "equity": equity.values,
            "benchmark_equity": benchmark_equity.values,
            "position": combined_position.values,
            "drawdown": drawdown.values,
        })

        return {
            "fund_code": fund_code,
            "strategy": strategy,
            "strategy_name": STRATEGY_LABELS[strategy],
            "objective": objective,
            "objective_name": OBJECTIVE_LABELS[objective],
            "candidate_count": len(candidates),
            "fold_count": len(folds),
            "recommended_parameters": recommended_parameters,
            "recommended_label": self.parameter_label(strategy, recommended_parameters),
            "oos_metrics": combined_metrics,
            "diagnostics": diagnostics,
            "folds": folds,
            "parameter_frequency": frequencies,
            "oos_curve": oos_curve.to_dict(orient="records"),
            "data_warning": nav.attrs.get("data_warning", ""),
            "assumptions": {
                "train_days": train_days,
                "test_days": test_days,
                "commission_rate": commission_rate,
                "slippage_rate": slippage_rate,
                "search_space": search_space,
            },
        }

    def _select_candidate(self, prices, strategy, candidates, cost_rate, initial_capital, objective):
        best = None
        for parameters in candidates:
            result = self._simulate(prices, strategy, parameters, cost_rate, initial_capital)
            score = self._score(result["metrics"], objective)
            candidate = {"parameters": parameters, "metrics": result["metrics"], "score": score}
            if best is None or score > best["score"]:
                best = candidate
        return best

    def _simulate(
        self, prices, strategy, parameters, cost_rate, initial_capital,
        evaluation_start=None, evaluation_end=None,
    ):
        prices = prices.astype(float)
        asset_returns = prices.pct_change().fillna(0.0)
        position = self._position(prices, strategy, parameters)
        if evaluation_start is not None:
            mask = (prices.index >= evaluation_start) & (prices.index <= evaluation_end)
            asset_returns = asset_returns.loc[mask]
            position = position.loc[mask]

        changes = position.diff()
        changes.iloc[0] = position.iloc[0]
        turnover = changes.abs()
        trade_count = int((changes != 0).sum())
        if position.iloc[-1] > 0:
            turnover.iloc[-1] += position.iloc[-1]
            trade_count += 1
        returns = position * asset_returns - turnover * cost_rate
        metrics = self._metrics(
            returns, asset_returns, position, initial_capital, trade_count=trade_count
        )
        return {
            "returns": returns,
            "benchmark_returns": asset_returns,
            "position": position,
            "metrics": metrics,
        }

    def _metrics(
        self, returns, benchmark_returns, position, initial_capital, trade_count=None
    ):
        equity = initial_capital * (1.0 + returns).cumprod()
        benchmark_equity = initial_capital * (1.0 + benchmark_returns).cumprod()
        drawdown = equity / equity.cummax() - 1.0
        annual_factor = self.trading_days / max(len(returns), 1)
        total_return = equity.iloc[-1] / initial_capital - 1.0
        annual_return = (equity.iloc[-1] / initial_capital) ** annual_factor - 1.0
        annual_volatility = returns.std(ddof=1) * np.sqrt(self.trading_days)
        sharpe = (
            (returns.mean() * self.trading_days - self.risk_free_rate) / annual_volatility
            if annual_volatility > 0 else 0.0
        )
        max_drawdown = float(drawdown.min())
        calmar = annual_return / abs(max_drawdown) if max_drawdown < 0 else 0.0
        if trade_count is None:
            changes = position.diff()
            changes.iloc[0] = position.iloc[0]
            trade_count = int((changes != 0).sum()) + int(position.iloc[-1] > 0)
        benchmark_return = benchmark_equity.iloc[-1] / initial_capital - 1.0
        return {
            "initial_capital": float(initial_capital),
            "final_equity": float(equity.iloc[-1]),
            "total_return": float(total_return),
            "annual_return": float(annual_return),
            "annual_volatility": float(annual_volatility),
            "sharpe_ratio": float(sharpe),
            "max_drawdown": max_drawdown,
            "calmar_ratio": float(calmar),
            "exposure": float(position.mean()),
            "benchmark_return": float(benchmark_return),
            "excess_return": float(total_return - benchmark_return),
            "trade_count": int(trade_count),
        }

    @staticmethod
    def _position(prices, strategy, parameters):
        if strategy == "ma_cross":
            short_ma = prices.rolling(
                parameters["short_window"], min_periods=parameters["short_window"]
            ).mean()
            long_ma = prices.rolling(
                parameters["long_window"], min_periods=parameters["long_window"]
            ).mean()
            signal = ((short_ma > long_ma) & long_ma.notna()).astype(float)
        else:
            momentum = prices.pct_change(parameters["momentum_window"])
            signal = (momentum > parameters["momentum_threshold"]).astype(float)
        return signal.shift(1).fillna(0.0)

    @staticmethod
    def _score(metrics, objective):
        sharpe = float(np.clip(metrics["sharpe_ratio"], -3, 3))
        calmar = float(np.clip(metrics["calmar_ratio"], -3, 3))
        annual_return = float(np.clip(metrics["annual_return"], -0.6, 0.8))
        drawdown = abs(float(metrics["max_drawdown"]))
        if objective == "sharpe":
            score = sharpe + 0.20 * calmar - 0.15 * drawdown
        elif objective == "return":
            score = 4.0 * annual_return + 0.25 * calmar - 0.50 * drawdown
        else:
            score = 0.45 * sharpe + 0.25 * calmar + annual_return - 0.30 * drawdown
        if metrics["exposure"] < 0.10:
            score -= (0.10 - metrics["exposure"]) * 8.0
        return float(score)

    def _diagnostics(self, folds, oos_metrics, counts):
        positive_rate = float(np.mean([fold["test_return"] > 0 for fold in folds]))
        outperform_rate = float(np.mean([
            fold["test_return"] > fold["benchmark_return"] for fold in folds
        ]))
        stability = max(counts.values()) / len(folds)
        mean_train_score = float(np.mean([fold["train_score"] for fold in folds]))
        mean_test_score = float(np.mean([fold["test_score"] for fold in folds]))
        overfit_gap = max(0.0, mean_train_score - mean_test_score)
        sharpe_component = float(np.clip((oos_metrics["sharpe_ratio"] + 0.5) / 2.0, 0, 1))
        drawdown_component = float(np.clip(1.0 - abs(oos_metrics["max_drawdown"]) / 0.50, 0, 1))
        reliability = 100 * (
            0.25 * sharpe_component + 0.20 * drawdown_component
            + 0.20 * positive_rate + 0.20 * outperform_rate + 0.15 * stability
        ) - min(15.0, overfit_gap * 7.5)
        reliability = float(np.clip(reliability, 0, 100))
        if reliability >= 75:
            grade, verdict = "A", "样本外表现稳健"
        elif reliability >= 60:
            grade, verdict = "B", "具备继续跟踪价值"
        elif reliability >= 45:
            grade, verdict = "C", "稳定性一般，建议观察"
        else:
            grade, verdict = "D", "过拟合或样本外表现偏弱"
        return {
            "reliability_score": reliability,
            "grade": grade,
            "verdict": verdict,
            "parameter_stability": float(stability),
            "positive_fold_rate": positive_rate,
            "outperform_fold_rate": outperform_rate,
            "mean_train_score": mean_train_score,
            "mean_test_score": mean_test_score,
            "overfit_gap": float(overfit_gap),
        }

    @staticmethod
    def _parameter_grid(strategy, search_space, train_days):
        if strategy == "ma_cross":
            if search_space == "fast":
                pairs = [(10, 40), (20, 60), (20, 120), (40, 120), (50, 200)]
            else:
                shorts = [5, 10, 20, 30, 40, 60]
                longs = [40, 60, 90, 120, 180, 240]
                if search_space == "deep":
                    shorts = [5, 10, 15, 20, 30, 40, 50, 60]
                    longs = [30, 40, 60, 90, 120, 150, 180, 200, 240]
                pairs = [
                    (short, long) for short in shorts for long in longs
                    if short < long and long >= short * 1.5
                ]
            max_window = max(40, int(train_days * 0.80))
            return [
                {"short_window": short, "long_window": long}
                for short, long in pairs if long <= max_window
            ]
        windows = [20, 60, 120] if search_space == "fast" else [10, 20, 40, 60, 90, 120, 180]
        thresholds = [-0.03, 0.0, 0.05] if search_space != "deep" else [-0.08, -0.05, -0.03, 0.0, 0.03, 0.05, 0.08, 0.12]
        return [
            {"momentum_window": window, "momentum_threshold": threshold}
            for window in windows for threshold in thresholds
            if window <= int(train_days * 0.80)
        ]

    @staticmethod
    def _warmup_days(strategy, parameters):
        return parameters["long_window"] if strategy == "ma_cross" else parameters["momentum_window"]

    @staticmethod
    def _parameter_key(parameters):
        return tuple(sorted(parameters.items()))

    @staticmethod
    def parameter_label(strategy, parameters):
        if strategy == "ma_cross":
            return f"MA {parameters['short_window']} / {parameters['long_window']}"
        return f"{parameters['momentum_window']} 日 / {parameters['momentum_threshold'] * 100:+.0f}%"

    @staticmethod
    def _validate_inputs(
        strategy, initial_capital, commission_rate, slippage_rate,
        train_days, test_days, objective, search_space,
    ):
        if strategy not in {"ma_cross", "momentum"}:
            return "自优化仅支持双均线趋势和动量轮动"
        if initial_capital <= 0:
            return "初始资金必须大于 0"
        if not 0 <= commission_rate <= 0.05 or not 0 <= slippage_rate <= 0.05:
            return "手续费率和滑点率必须在 0% 到 5% 之间"
        if train_days < 120:
            return "训练窗口不能少于 120 个交易日"
        if test_days < 20:
            return "验证窗口不能少于 20 个交易日"
        if objective not in OBJECTIVE_LABELS:
            return "不支持的优化目标"
        if search_space not in {"fast", "standard", "deep"}:
            return "不支持的搜索深度"
        return ""
