import click
import pandas as pd
from rich.console import Console
from rich.table import Table
from src.data.fund_api import FundDataAPI
from src.data.stock_api import AStockDataAPI, StockDataError
from src.portfolio.manager import PortfolioManager
from src.analysis.engine import AnalysisEngine
from src.backtest.engine import BacktestEngine
from src.strategy.optimizer import PortfolioOptimizer
from src.strategy.walk_forward import WalkForwardOptimizer
from src.news.service import NewsService
import sys

console = Console()

@click.group()
def cli():
    """基金智能分析助手 CLI"""
    pass

@cli.command()
@click.argument('fund_code')
def info(fund_code):
    """获取单个基金信息"""
    api = FundDataAPI()
    console.print(f"正在获取基金 {fund_code} 的信息...", style="bold blue")
    
    info_data = api.get_fund_info(fund_code)
    
    table = Table(title=f"基金基本信息 - {fund_code}")
    table.add_column("字段", style="cyan")
    table.add_column("内容", style="magenta")
    
    for k, v in info_data.items():
        table.add_row(str(k), str(v))
        
    console.print(table)


@cli.command()
@click.argument("stock_code")
@click.option("--days", default=30, show_default=True, type=click.IntRange(2, 3650))
@click.option(
    "--adjust",
    default="forward",
    show_default=True,
    type=click.Choice(["none", "forward", "backward"]),
)
def stock(stock_code, days, adjust):
    """查看 A 股最新行情和近期日线摘要。"""
    end = pd.Timestamp.now().date()
    start = end - pd.Timedelta(days=days)
    api = AStockDataAPI()
    try:
        snapshot = api.get_snapshot([stock_code])
        history = api.get_history(stock_code, start, end, adjust=adjust)
    except (StockDataError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    if snapshot.empty or history.empty:
        raise click.ClickException("没有获取到可用的 A 股行情")

    quote = snapshot.iloc[0]
    console.print(
        f"[bold]{quote['stock_code']}[/bold]  "
        f"最新价 {quote['last_price']:.2f}  "
        f"涨跌幅 {quote['change_pct']:+.2f}%"
    )
    table = Table(title=f"最近 {min(10, len(history))} 个交易日")
    for label in ["日期", "开盘", "最高", "最低", "收盘", "成交额"]:
        table.add_column(label, justify="right" if label != "日期" else "left")
    for _, row in history.tail(10).iloc[::-1].iterrows():
        table.add_row(
            row["date"].strftime("%Y-%m-%d"),
            f"{row['open']:.2f}",
            f"{row['high']:.2f}",
            f"{row['low']:.2f}",
            f"{row['close']:.2f}",
            f"{row['turnover']:,.0f}",
        )
    console.print(table)

@cli.command()
def portfolio():
    """查看当前持仓"""
    pm = PortfolioManager()
    df = pm.get_holdings()
    
    if df.empty:
        console.print("当前无持仓数据。", style="yellow")
        return
        
    api = FundDataAPI()
    
    table = Table(title="当前持仓概览")
    table.add_column("基金代码", style="cyan")
    table.add_column("基金名称", style="cyan")
    table.add_column("持有份额", justify="right")
    table.add_column("持仓成本", justify="right")
    table.add_column("单位成本", justify="right")
    table.add_column("最新净值", justify="right")
    table.add_column("估算盈亏", justify="right")
    
    total_cost = 0
    total_value = 0
    
    for _, row in df.iterrows():
        code = row['fund_code']
        nav_df = api.get_fund_nav(code)
        latest_nav = 0
        fund_name = api.get_fund_info(code).get("基金简称", "未知")
        
        if not nav_df.empty:
            latest_nav = float(nav_df.iloc[-1]['unit_nav'])
            
        current_value = row['shares'] * latest_nav
        profit = current_value - row['cost']
        
        total_cost += row['cost']
        total_value += current_value
        
        profit_style = "green" if profit >= 0 else "red"
        
        table.add_row(
            code,
            fund_name,
            f"{row['shares']:.2f}",
            f"{row['cost']:.2f}",
            f"{row['unit_cost']:.4f}",
            f"{latest_nav:.4f}",
            f"[{profit_style}]{profit:.2f}[/{profit_style}]"
        )
        
    console.print(table)
    
    total_profit = total_value - total_cost
    profit_pct = (total_profit / total_cost * 100) if total_cost > 0 else 0
    profit_style = "green" if total_profit >= 0 else "red"
    
    console.print(f"\n总成本: {total_cost:.2f}")
    console.print(f"总市值: {total_value:.2f}")
    console.print(f"总盈亏: [{profit_style}]{total_profit:.2f} ({profit_pct:.2f}%)[/{profit_style}]")

@cli.command()
@click.option('--date', required=True, help='交易日期 YYYY-MM-DD')
@click.option('--code', required=True, help='基金代码')
@click.option('--action', required=True, type=click.Choice(['buy', 'sell']), help='买入或卖出')
@click.option('--amount', required=True, type=float, help='金额(买入)/份额(卖出)')
@click.option('--price', required=True, type=float, help='成交净值')
@click.option('--fee', default=0.0, type=float, help='手续费')
def trade(date, code, action, amount, price, fee):
    """记录一笔交易"""
    pm = PortfolioManager()
    pm.add_transaction(date, code, action, amount, price, fee)
    console.print(f"成功记录交易: {date} {action} {code}", style="green")

@cli.command()
@click.argument('fund_code')
def analyze(fund_code):
    """分析基金风险指标"""
    engine = AnalysisEngine()
    console.print(f"正在分析基金 {fund_code} ...", style="bold blue")
    
    result = engine.analyze_fund(fund_code)
    
    if "error" in result:
        console.print(result["error"], style="red")
        return
        
    table = Table(title=f"基金风险收益分析 - {fund_code}")
    table.add_column("指标", style="cyan")
    table.add_column("数值", style="magenta")
    
    for k, v in result.items():
        table.add_row(str(k), str(v))
        
    console.print(table)

@cli.command()
@click.argument('fund_code')
@click.option('--start', required=True, help='开始日期 YYYY-MM-DD')
@click.option('--end', required=True, help='结束日期 YYYY-MM-DD')
@click.option('--amount', default=1000.0, help='每期定投金额')
@click.option('--freq', default='M', type=click.Choice(['M', 'W']), help='定投频率: M(月), W(周)')
def backtest(fund_code, start, end, amount, freq):
    """回测定投策略"""
    engine = BacktestEngine()
    console.print(f"正在回测 {fund_code} 的定投策略...", style="bold blue")
    
    result = engine.run_dca(fund_code, start, end, amount, freq)
    
    if "error" in result:
        console.print(result["error"], style="red")
        return
        
    table = Table(title=f"定投回测结果 - {fund_code}")
    table.add_column("指标", style="cyan")
    table.add_column("结果", style="magenta")
    
    for k, v in result.items():
        if isinstance(v, float):
            table.add_row(str(k), f"{v:.2f}")
        else:
            table.add_row(str(k), str(v))
            
    console.print(table)

@cli.command()
@click.argument('fund_codes', nargs=-1)
@click.option('--start', required=True, help='开始日期 YYYY-MM-DD')
@click.option('--end', required=True, help='结束日期 YYYY-MM-DD')
def optimize(fund_codes, start, end):
    """风险平价组合优化调仓建议"""
    if len(fund_codes) < 2:
        console.print("请至少提供2个基金代码", style="red")
        return
        
    optimizer = PortfolioOptimizer()
    console.print(f"正在分析基金组合: {', '.join(fund_codes)}", style="bold blue")
    
    result = optimizer.optimize_risk_parity(list(fund_codes), start, end)
    
    if "error" in result:
        console.print(result["error"], style="red")
        return
        
    console.print("\n[bold green]优化完成！调仓建议：[/bold green]")
    
    weight_table = Table(title="目标仓位权重")
    weight_table.add_column("基金代码", style="cyan")
    weight_table.add_column("目标权重", style="magenta")
    
    for code, weight in result["权重分配"].items():
        weight_table.add_row(code, f"{weight * 100:.2f}%")
        
    console.print(weight_table)
    
    metric_table = Table(title="组合预期指标")
    metric_table.add_column("指标", style="cyan")
    metric_table.add_column("数值", style="magenta")
    
    metric_table.add_row("预期年化收益", result["预期年化收益"])
    metric_table.add_row("预期波动率", result["预期年化波动率"])
    
    console.print(metric_table)


@cli.command()
@click.argument("fund_code")
@click.option("--start", required=True, help="开始日期 YYYY-MM-DD")
@click.option("--end", required=True, help="结束日期 YYYY-MM-DD")
@click.option(
    "--strategy",
    default="ma_cross",
    type=click.Choice(["buy_hold", "ma_cross", "momentum"]),
    show_default=True,
)
@click.option("--capital", default=100000.0, show_default=True, help="初始资金")
@click.option("--short-window", default=20, show_default=True)
@click.option("--long-window", default=60, show_default=True)
@click.option("--momentum-window", default=60, show_default=True)
def quant(fund_code, start, end, strategy, capital, short_window, long_window, momentum_window):
    """运行量化择时回测。"""
    result = BacktestEngine().run_strategy(
        fund_code,
        start,
        end,
        strategy=strategy,
        initial_capital=capital,
        short_window=short_window,
        long_window=long_window,
        momentum_window=momentum_window,
    )
    if "error" in result:
        console.print(result["error"], style="red")
        return

    metrics = result["metrics"]
    table = Table(title=f"量化回测 - {fund_code} / {result['strategy_name']}")
    table.add_column("指标", style="cyan")
    table.add_column("结果", justify="right")
    rows = {
        "期末权益": f"{metrics['final_equity']:,.2f}",
        "累计收益": f"{metrics['total_return']:.2%}",
        "年化收益": f"{metrics['annual_return']:.2%}",
        "最大回撤": f"{metrics['max_drawdown']:.2%}",
        "夏普比率": f"{metrics['sharpe_ratio']:.2f}",
        "基准收益": f"{metrics['benchmark_return']:.2%}",
        "交易次数": str(metrics["trade_count"]),
    }
    for label, value in rows.items():
        table.add_row(label, value)
    console.print(table)


@cli.command(name="auto-optimize")
@click.argument("fund_code")
@click.option("--start", required=True, help="开始日期 YYYY-MM-DD")
@click.option("--end", required=True, help="结束日期 YYYY-MM-DD")
@click.option(
    "--strategy",
    default="ma_cross",
    type=click.Choice(["ma_cross", "momentum"]),
    show_default=True,
)
@click.option("--train-days", default=488, show_default=True, help="滚动训练交易日")
@click.option("--test-days", default=122, show_default=True, help="样本外验证交易日")
@click.option(
    "--objective",
    default="balanced",
    type=click.Choice(["balanced", "sharpe", "return"]),
    show_default=True,
)
@click.option(
    "--depth",
    default="standard",
    type=click.Choice(["fast", "standard", "deep"]),
    show_default=True,
)
def auto_optimize(fund_code, start, end, strategy, train_days, test_days, objective, depth):
    """运行 Walk-Forward 参数自优化与样本外验证。"""
    result = WalkForwardOptimizer().optimize(
        fund_code,
        start,
        end,
        strategy=strategy,
        train_days=train_days,
        test_days=test_days,
        objective=objective,
        search_space=depth,
    )
    if "error" in result:
        console.print(result["error"], style="red")
        return

    metrics = result["oos_metrics"]
    diagnostics = result["diagnostics"]
    table = Table(title=f"Walk-Forward 自优化 - {fund_code}")
    table.add_column("指标", style="cyan")
    table.add_column("结果", justify="right")
    rows = {
        "策略": result["strategy_name"],
        "推荐参数": result["recommended_label"],
        "验证窗口": str(result["fold_count"]),
        "候选参数": str(result["candidate_count"]),
        "样本外收益": f"{metrics['total_return']:.2%}",
        "样本外超额": f"{metrics['excess_return']:.2%}",
        "最大回撤": f"{metrics['max_drawdown']:.2%}",
        "夏普比率": f"{metrics['sharpe_ratio']:.2f}",
        "可靠性": f"{diagnostics['reliability_score']:.0f}/100 ({diagnostics['grade']})",
        "结论": diagnostics["verdict"],
    }
    for label, value in rows.items():
        table.add_row(label, value)
    console.print(table)


@cli.command(name="news")
@click.argument("query")
@click.option("--scope", default="keyword", type=click.Choice(["keyword", "global"]))
@click.option("--limit", default=10, type=click.IntRange(1, 50), show_default=True)
def news_command(query, scope, limit):
    """按基金代码或关键词检索财经新闻。"""
    result = NewsService().search(query, scope=scope, limit=limit)
    if result.warning:
        console.print(result.warning, style="yellow")
    if result.items.empty:
        console.print("没有找到相关新闻。", style="yellow")
        return

    table = Table(title=f"新闻检索 - {query}")
    table.add_column("时间", width=18)
    table.add_column("来源", width=14)
    table.add_column("标题", overflow="fold")
    for _, item in result.items.iterrows():
        published_at = item["published_at"]
        published = published_at.strftime("%Y-%m-%d %H:%M") if pd.notna(published_at) else "-"
        table.add_row(published, str(item["source"]), str(item["title"]))
    console.print(table)

if __name__ == "__main__":
    cli()
