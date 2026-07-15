import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

from src.data.fund_api import FundDataAPI
from src.portfolio.manager import PortfolioManager
from src.analysis.engine import AnalysisEngine
from src.backtest.engine import BacktestEngine
from src.strategy.optimizer import PortfolioOptimizer
from src.strategy.walk_forward import WalkForwardOptimizer
from src.analysis.ai_analyzer import AIFundAnalyzer
from src.integrations.llm_gateway import PROVIDER_LABELS
from src.news.service import NewsService
from src.utils.config import config

# ==========================================
# 页面基础配置 & 样式优化
# ==========================================
st.set_page_config(
    page_title="FundMaster Pro | 智能基金分析系统",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 注入自定义CSS来美化界面
st.markdown("""
<style>
    /* 全局背景与隐藏默认元素 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    [data-testid="stToolbar"] {visibility: hidden;}
    .stApp {
        background-color: #F9FAFB;
    }
    .stApp > header {
        background-color: rgba(249, 250, 251, 0.8);
        backdrop-filter: blur(10px);
    }
    
    /* 紧凑的工作台卡片 */
    div[data-testid="stMetric"], div[data-testid="stExpander"], div.stDataFrame, div[data-testid="stForm"] {
        background-color: #FFFFFF;
        border-radius: 8px !important;
        padding: 16px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03) !important;
        border: 1px solid rgba(0, 0, 0, 0.02);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    div[data-testid="stMetric"] {
        container-type: inline-size;
        min-width: 0;
    }
    
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(0, 0, 0, 0.06) !important;
    }

    /* 指标数值的现代感排版 */
    [data-testid="stMetricValue"] {
        font-size: clamp(1.15rem, 12cqw, 1.8rem);
        line-height: 1.2;
        font-weight: 800;
        color: #111827;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    [data-testid="stMetricLabel"] {
        font-size: 1rem;
        color: #6B7280;
        font-weight: 500;
    }
    
    /* 所有的输入框、下拉框做大圆角和柔和边框 */
    .stTextInput>div>div>input, .stNumberInput>div>div>input, .stSelectbox>div>div>div, .stDateInput>div>div>input {
        border-radius: 8px !important;
        border: 1px solid #E5E7EB !important;
        background-color: #FFFFFF !important;
        padding: 10px 14px !important;
        transition: all 0.3s;
    }
    .stTextInput>div>div>input:focus, .stNumberInput>div>div>input:focus {
        border-color: #3B82F6 !important;
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1) !important;
    }

    /* 操作按钮 */
    .stButton>button, .stFormSubmitButton>button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 6px 20px !important;
        border: none !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    /* 主按钮 */
    button[kind="primary"] {
        background: #2563EB !important;
        color: white !important;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2) !important;
    }
    button[kind="primary"]:hover {
        box-shadow: 0 6px 16px rgba(37, 99, 235, 0.3) !important;
        transform: translateY(-2px);
    }
    /* 次级按钮 */
    button[kind="secondary"] {
        background-color: #F3F4F6 !important;
        color: #374151 !important;
    }
    button[kind="secondary"]:hover {
        background-color: #E5E7EB !important;
        transform: translateY(-2px);
    }
    
    /* 自定义标题栏，苹果极简风 */
    .main-header {
        font-size: 2.2rem;
        line-height: 1.2;
        font-weight: 800;
        color: #111827;
        letter-spacing: -0.02em;
        margin-bottom: 24px;
    }
    .sub-text {
        font-size: 1.1rem;
        color: #6B7280;
        margin-top: -16px;
        margin-bottom: 32px;
    }
    
    /* 侧边栏整体美化 */
    [data-testid="stSidebar"] {
        background-color: #FCFCFD;
        border-right: 1px solid #E5E7EB;
    }
    [data-testid="stSidebarContent"] {
        padding: 8px 14px 0;
    }
    [data-testid="stSidebarHeader"] {
        min-height: 40px;
        height: 40px;
    }
    [data-testid="stSidebar"] [data-testid="stLogoSpacer"] {
        display: none;
    }
    [data-testid="stSidebarUserContent"] {
        padding-bottom: 8px;
    }
    [data-testid="stSidebarUserContent"] > [data-testid="stVerticalBlock"] {
        gap: 0.45rem;
    }
    [data-testid="stSidebar"] [data-testid="stForm"] [data-testid="stVerticalBlock"] {
        gap: 0.75rem;
    }
    .sidebar-brand {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 2px 2px 6px;
    }
    .sidebar-brand-mark {
        display: flex;
        align-items: center;
        justify-content: center;
        width: 36px;
        height: 36px;
        flex: 0 0 36px;
        border-radius: 8px;
        background: #111827;
        color: #FFFFFF;
        font-family: Georgia, "Noto Serif SC", serif;
        font-size: 0.85rem;
        font-weight: 700;
    }
    .sidebar-brand-name {
        color: #111827;
        font-family: Georgia, "Noto Serif SC", serif;
        font-size: 1rem;
        font-weight: 700;
        line-height: 1.15;
    }
    .sidebar-brand-subtitle {
        margin-top: 3px;
        color: #64748B;
        font-size: 0.72rem;
    }
    .sidebar-status {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 9px 10px;
        margin-bottom: 8px;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        background: #FFFFFF;
        color: #475569;
        font-size: 0.75rem;
    }
    .sidebar-status-left {
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .sidebar-status-dot {
        width: 7px;
        height: 7px;
        border-radius: 50%;
        background: #16A34A;
        box-shadow: 0 0 0 3px rgba(22, 163, 74, 0.10);
    }
    .sidebar-group-label {
        margin: 8px 8px 2px;
        color: #94A3B8;
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.08em;
    }
    [data-testid="stSidebar"] .stButton {
        margin-bottom: 2px;
    }
    [data-testid="stSidebar"] .stButton > button {
        min-height: 34px;
        height: 34px;
        justify-content: flex-start;
        padding: 7px 10px !important;
        box-shadow: none !important;
        font-size: 0.88rem;
    }
    [data-testid="stSidebar"] .stButton > button[kind="secondary"] {
        border: 1px solid transparent !important;
        background: transparent !important;
        color: #475569 !important;
    }
    [data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover {
        border-color: #E2E8F0 !important;
        background: #F1F5F9 !important;
        color: #0F172A !important;
        transform: none;
    }
    [data-testid="stSidebar"] .stButton > button[kind="primary"] {
        background: #111827 !important;
        color: #FFFFFF !important;
        box-shadow: none !important;
    }
    [data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
        background: #1F2937 !important;
        transform: none;
    }
    [data-testid="stSidebar"] hr {
        margin: 14px 0;
    }
    [data-testid="stSidebar"] div[data-testid="stExpander"] {
        padding: 0;
        margin-top: 8px;
        border-color: #E5E7EB;
        box-shadow: none !important;
    }
    [data-testid="stSidebar"] div[data-testid="stForm"] {
        padding: 4px 2px 2px;
        border: 0;
        box-shadow: none !important;
    }
    [data-testid="stSidebar"] [data-testid="stExpander"] summary {
        font-weight: 650;
    }
    
    /* 优化提示框(info/success/error)圆角 */
    div[data-testid="stAlert"] {
        border-radius: 8px !important;
        border: none !important;
    }
    
    hr {
        margin-top: 2em;
        margin-bottom: 2em;
        border-top: 1px solid #F3F4F6;
    }
    
    /* 优化 Tab 样式 */
    [data-testid="stTabs"] button {
        border-radius: 8px 8px 0 0 !important;
        font-weight: 600 !important;
    }

    @media (max-width: 768px) {
        .main-header {
            font-size: 1.75rem;
            margin-bottom: 18px;
        }
        .sub-text {
            font-size: 0.95rem;
            margin-bottom: 20px;
        }
        [data-testid="stMain"] [data-testid="stHorizontalBlock"] {
            flex-wrap: wrap;
        }
        [data-testid="stMain"] [data-testid="column"] {
            flex: 1 1 100% !important;
            width: 100% !important;
            min-width: 100% !important;
        }
        div[data-testid="stMetric"] {
            padding: 12px;
        }
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 初始化与缓存
# ==========================================
COMPONENTS_VERSION = "2026-07-15.3"


@st.cache_resource
def get_components(version: str):
    data_config = config.get("dataSources", {})
    analysis_config = config.get("analysis", {})
    news_config = config.get("news", {})
    backtest_engine = BacktestEngine(
        trading_days=int(analysis_config.get("tradingDaysPerYear", 244)),
        risk_free_rate=float(analysis_config.get("riskFreeRate", 0.02)),
    )
    return {
        "api": FundDataAPI(
            cache_dir=data_config.get("cachePath", "data/cache"),
            cache_ttl_hours=int(data_config.get("cacheTtlHours", 24)),
        ),
        "pm": PortfolioManager(),
        "analyzer": AnalysisEngine(),
        "backtest": backtest_engine,
        "walk_forward": WalkForwardOptimizer(backtest_engine),
        "optimizer": PortfolioOptimizer(),
        "ai": AIFundAnalyzer(),
        "news": NewsService(
            cache_dir=news_config.get("cachePath", "data/cache/news"),
            cache_ttl_minutes=int(news_config.get("cacheTtlMinutes", 30)),
        ),
    }

comps = get_components(COMPONENTS_VERSION)
api = comps["api"]
pm = comps["pm"]

# ==========================================
# 侧边栏导航
# ==========================================
with st.sidebar:
    st.markdown(
        """
        <div class="sidebar-brand">
            <div class="sidebar-brand-mark">FM</div>
            <div>
                <div class="sidebar-brand-name">FundMaster Pro</div>
                <div class="sidebar-brand-subtitle">个人量化资产工作台</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    holdings_count = len(pm.get_holdings())
    st.markdown(
        f"""
        <div class="sidebar-status">
            <div class="sidebar-status-left">
                <span class="sidebar-status-dot"></span>
                <span>数据服务就绪</span>
            </div>
            <span>{holdings_count} 项持仓</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    nav_groups = {
        "概览": ["📊 资产全景看板", "🔎 深度个基透视"],
        "策略与研究": ["🧪 量化回测实验室", "🧮 定投复利计算器", "⚖️ 智能资产配置", "📰 市场新闻检索"],
        "智能与系统": ["🤖 AI 智能诊断", "⚙️ 全局系统设置"],
    }
    if "active_page" not in st.session_state:
        st.session_state.active_page = "📊 资产全景看板"

    for group_name, group_pages in nav_groups.items():
        st.markdown(
            f'<div class="sidebar-group-label">{group_name}</div>',
            unsafe_allow_html=True,
        )
        for nav_page in group_pages:
            is_active = st.session_state.active_page == nav_page
            if st.button(
                nav_page,
                key=f"nav_{nav_page}",
                type="primary" if is_active else "secondary",
                width="stretch",
            ):
                st.session_state.active_page = nav_page
                st.rerun()

    page = st.session_state.active_page

    with st.expander("新增交易", expanded=False, icon="➕"):
        with st.form("trade_form", clear_on_submit=True):
            trade_code = st.text_input("基金代码", placeholder="例如: 510300")
            trade_action = st.selectbox(
                "交易方向",
                ["buy", "sell"],
                format_func=lambda value: "买入" if value == "buy" else "卖出",
            )
            trade_price = st.number_input(
                "成交净值", min_value=0.0001, step=0.1, format="%.4f"
            )
            trade_amount = st.number_input(
                "金额 / 份额", min_value=0.01, step=100.0,
                help="买入填写金额，卖出填写份额",
            )
            trade_fee = st.number_input("手续费", min_value=0.0, step=1.0)
            trade_date = st.date_input("交易日期", datetime.now())

            submitted = st.form_submit_button("保存交易", width="stretch")
            if submitted:
                if not trade_code.strip():
                    st.error("请输入基金代码")
                else:
                    pm.add_transaction(
                        trade_date.strftime("%Y-%m-%d"),
                        trade_code.strip(),
                        trade_action,
                        trade_amount,
                        trade_price,
                        trade_fee,
                    )
                    st.success("交易已保存")
                    st.rerun()

# ==========================================
# 页面路由逻辑
# ==========================================

# ----------------- 页面一：资产看板 -----------------
if page == "📊 资产全景看板":
    st.markdown('<div class="main-header">我的资产全景看板</div>', unsafe_allow_html=True)
    
    df = pm.get_holdings()
    
    if df.empty:
        st.info("👋 欢迎使用！请在左侧栏录入您的第一笔基金交易记录，即可点亮资产看板。")
    else:
        # 数据处理
        with st.spinner("正在同步最新净值数据..."):
            holdings_data = []
            total_cost = 0
            total_value = 0
            daily_profit = 0
            
            for _, row in df.iterrows():
                code = row['fund_code']
                nav_df = api.get_fund_nav(code)
                latest_nav = 0
                prev_nav = 0
                fund_info = api.get_fund_info(code)
                fund_name = fund_info.get("基金简称", "未知")
                
                if len(nav_df) >= 2:
                    latest_nav = float(nav_df.iloc[-1]['unit_nav'])
                    prev_nav = float(nav_df.iloc[-2]['unit_nav'])
                    
                current_value = row['shares'] * latest_nav
                profit = current_value - row['cost']
                profit_pct = (profit / row['cost'] * 100) if row['cost'] > 0 else 0
                
                # 计算单日盈亏
                if prev_nav > 0:
                    daily_profit += row['shares'] * (latest_nav - prev_nav)
                
                total_cost += row['cost']
                total_value += current_value
                
                holdings_data.append({
                    "代码": code,
                    "基金名称": fund_name,
                    "持有份额": row['shares'],
                    "持仓成本": row['cost'],
                    "最新净值": latest_nav,
                    "持仓市值": current_value,
                    "估算盈亏": profit,
                    "收益率(%)": profit_pct
                })
        
        # 1. 顶部核心指标区
        total_profit = total_value - total_cost
        total_profit_pct = (total_profit / total_cost * 100) if total_cost > 0 else 0
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("总资产", f"¥ {total_value:,.2f}", f"今日盈亏: {daily_profit:+.2f}")
        with col2:
            st.metric("累计投入", f"¥ {total_cost:,.2f}")
        with col3:
            st.metric("累计盈亏", f"¥ {total_profit:,.2f}", f"{total_profit_pct:+.2f}%")
        with col4:
            st.metric("持仓数量", f"{len(df)} 只")
            
        st.markdown("<br>", unsafe_allow_html=True)
            
        # 2. 图表可视化区
        if holdings_data:
            holdings_df = pd.DataFrame(holdings_data)
            
            c1, c2 = st.columns([1.2, 1])
            
            with c1:
                st.markdown("#### 🍩 资产分布情况")
                fig_pie = px.pie(
                    holdings_df, 
                    values='持仓市值', 
                    names='基金名称', 
                    hole=0.6,
                    color_discrete_sequence=px.colors.qualitative.Pastel
                )
                fig_pie.update_traces(textposition='inside', textinfo='percent+label',
                                    marker=dict(line=dict(color='#FFFFFF', width=2)))
                fig_pie.update_layout(margin=dict(t=20, b=20, l=20, r=20),
                                    showlegend=False,
                                    height=350)
                st.plotly_chart(fig_pie, width="stretch")
                
            with c2:
                st.markdown("#### 📈 各基盈亏贡献")
                # 按盈亏排序
                holdings_df = holdings_df.sort_values(by='估算盈亏')
                bar_colors = [
                    '#15803D' if value >= 0 else '#DC2626'
                    for value in holdings_df['估算盈亏']
                ]
                fig_bar = go.Figure(
                    go.Bar(
                        y=holdings_df['基金名称'],
                        x=holdings_df['估算盈亏'],
                        orientation='h',
                        marker_color=bar_colors,
                        text=[f"¥{value:,.0f}" for value in holdings_df['估算盈亏']],
                        textposition='outside',
                        cliponaxis=False,
                        hovertemplate='%{y}<br>盈亏 ¥%{x:,.2f}<extra></extra>'
                    )
                )
                fig_bar.update_layout(margin=dict(t=20, b=20, l=0, r=0),
                                    yaxis_title="",
                                    xaxis_title="盈亏金额 (元)",
                                    xaxis=dict(zeroline=True, zerolinecolor='#94A3B8'),
                                    height=350)
                st.plotly_chart(fig_bar, width="stretch")

            # 3. 数据表格区
            st.markdown("#### 📋 详细持仓清单")
            
            # 美化表格输出
            styled_df = holdings_df.copy()
            # 格式化
            format_dict = {
                '持有份额': '{:,.2f}',
                '持仓成本': '¥{:,.2f}',
                '最新净值': '{:.4f}',
                '持仓市值': '¥{:,.2f}',
                '估算盈亏': '¥{:,.2f}',
                '收益率(%)': '{:+.2f}%'
            }
            
            def color_profit(val):
                if pd.isna(val): return ''
                color = '#10B981' if float(val) > 0 else '#EF4444' if float(val) < 0 else 'gray'
                return f'color: {color}; font-weight: bold'
                
            st.dataframe(
                styled_df.style
                .format(format_dict)
                                .map(color_profit, subset=['估算盈亏', '收益率(%)'])
                .set_properties(**{'background-color': '#F9FAFB'}, subset=pd.IndexSlice[styled_df.index[::2], :]),
                width="stretch",
                height=400
            )

# ----------------- 页面二：个基透视 -----------------
elif page == "🔎 深度个基透视":
    st.markdown('<div class="main-header">深度个基透视仪</div>', unsafe_allow_html=True)
    st.markdown("全方位解析单只基金的历史表现、风险敞口与回撤特性。")
    
    col_search, _ = st.columns([1, 2])
    with col_search:
        fund_code = st.text_input("输入要分析的基金代码", value="510300", 
                               help="例如: 510300(沪深300ETF), 005827(易方达蓝筹)")
        
    if fund_code:
        with st.spinner('正在调取深度分析数据...'):
            info = api.get_fund_info(fund_code)
            nav_df = api.get_fund_nav(fund_code)
            
            if nav_df.empty:
                st.warning("⚠️ 未能获取到该基金的数据，请检查代码是否正确。")
            else:
                fund_name = info.get('基金简称', '未知基金')
                st.subheader(f"✨ {fund_name} ({fund_code})")
                
                analyzer = comps["analyzer"]
                metrics = analyzer.analyze_fund(fund_code)
                
                # 顶部卡片
                c1, c2, c3, c4 = st.columns(4)
                
                # 计算近1年收益作为展示
                one_year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
                recent_nav = nav_df[nav_df['净值日期'] >= one_year_ago]
                y1_ret = 0
                if len(recent_nav) >= 2:
                    y1_ret = (float(recent_nav.iloc[-1]['unit_nav']) / float(recent_nav.iloc[0]['unit_nav']) - 1) * 100
                
                c1.metric("近一年收益率", f"{y1_ret:+.2f}%")
                c2.metric("历史最大回撤", metrics.get("最大回撤", "0%"))
                c3.metric("历史夏普比率", metrics.get("夏普比率", "0"))
                c4.metric("最新净值 (元)", f"{nav_df.iloc[-1]['unit_nav']:.4f}")
                
                st.markdown("---")
                
                # 交互式K线图
                st.markdown("#### 📈 历史净值走势与回撤图")
                
                # 计算历史回撤曲线
                nav_df['max_here'] = nav_df['unit_nav'].cummax()
                nav_df['drawdown'] = (nav_df['unit_nav'] - nav_df['max_here']) / nav_df['max_here'] * 100
                
                fig = go.Figure()
                # 净值线
                fig.add_trace(go.Scatter(
                    x=nav_df['净值日期'], y=nav_df['unit_nav'], 
                    mode='lines', name='单位净值',
                    line=dict(color='#2563EB', width=2)
                ))
                # 回撤面积图 (放在副坐标轴)
                fig.add_trace(go.Scatter(
                    x=nav_df['净值日期'], y=nav_df['drawdown'], 
                    mode='lines', name='回撤幅度(%)',
                    fill='tozeroy',
                    yaxis='y2',
                    line=dict(color='rgba(239, 68, 68, 0.3)', width=1)
                ))
                
                fig.update_layout(
                    hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    margin=dict(l=0, r=0, t=30, b=0),
                    yaxis=dict(title="净值(元)", side="left"),
                    yaxis2=dict(title="回撤(%)", side="right", overlaying="y", showgrid=False, range=[-100, 5]),
                    height=450,
                    plot_bgcolor='white',
                    paper_bgcolor='white'
                )
                fig.update_xaxes(showgrid=True, gridcolor='rgba(0,0,0,0.05)')
                fig.update_yaxes(showgrid=True, gridcolor='rgba(0,0,0,0.05)')
                
                st.plotly_chart(fig, width="stretch")

# ----------------- 页面三：量化回测实验室 -----------------
elif page == "🧪 量化回测实验室":
    st.markdown('<div class="main-header">量化回测实验室</div>', unsafe_allow_html=True)
    quant_tab, optimize_tab, dca_tab = st.tabs(["策略择时", "自优化分析", "周期定投"])

    with quant_tab:
        strategy_options = {
            "买入并持有": "buy_hold",
            "双均线趋势": "ma_cross",
            "动量轮动": "momentum",
        }
        with st.form("quant_backtest_form"):
            strategy_label = st.segmented_control(
                "策略模型",
                list(strategy_options),
                default="双均线趋势",
                width="stretch",
            )
            q1, q2, q3, q4 = st.columns(4)
            with q1:
                quant_code = st.text_input("基金代码", value="510300", key="quant_code")
                initial_capital = st.number_input(
                    "初始资金", min_value=1000, value=100000, step=10000
                )
            with q2:
                quant_start = st.date_input("开始日期", datetime(2020, 1, 1), key="quant_start")
                quant_end = st.date_input("结束日期", datetime.now(), key="quant_end")
            with q3:
                commission_pct = st.number_input(
                    "单边手续费 (%)", min_value=0.0, max_value=5.0, value=0.15, step=0.05
                )
                slippage_pct = st.number_input(
                    "滑点 (%)", min_value=0.0, max_value=5.0, value=0.05, step=0.05
                )
            with q4:
                if strategy_label == "双均线趋势":
                    short_window = st.number_input("短均线", min_value=2, value=20, step=1)
                    long_window = st.number_input("长均线", min_value=3, value=60, step=1)
                    momentum_window = 60
                    momentum_threshold = 0.0
                elif strategy_label == "动量轮动":
                    momentum_window = st.number_input("动量观察期", min_value=2, value=60, step=5)
                    momentum_threshold = st.number_input(
                        "入场阈值 (%)", min_value=-50.0, max_value=50.0, value=0.0, step=0.5
                    ) / 100
                    short_window, long_window = 20, 60
                else:
                    short_window, long_window = 20, 60
                    momentum_window, momentum_threshold = 60, 0.0

            run_quant = st.form_submit_button("运行策略回测", type="primary", width="stretch")

        if run_quant:
            if quant_start >= quant_end:
                st.error("结束日期必须晚于开始日期")
            else:
                with st.spinner("正在计算策略信号、交易成本与风险指标..."):
                    quant_result = comps["backtest"].run_strategy(
                        quant_code,
                        quant_start.strftime("%Y-%m-%d"),
                        quant_end.strftime("%Y-%m-%d"),
                        strategy=strategy_options[strategy_label],
                        initial_capital=initial_capital,
                        commission_rate=commission_pct / 100,
                        slippage_rate=slippage_pct / 100,
                        short_window=short_window,
                        long_window=long_window,
                        momentum_window=momentum_window,
                        momentum_threshold=momentum_threshold,
                    )

                if "error" in quant_result:
                    st.error(quant_result["error"])
                else:
                    if quant_result.get("data_warning"):
                        st.warning(quant_result["data_warning"])
                    metrics = quant_result["metrics"]
                    m1, m2, m3, m4, m5, m6 = st.columns(6)
                    m1.metric("期末权益", f"¥{metrics['final_equity']:,.0f}")
                    m2.metric("累计收益", f"{metrics['total_return']:.2%}")
                    m3.metric("年化收益", f"{metrics['annual_return']:.2%}")
                    m4.metric("最大回撤", f"{metrics['max_drawdown']:.2%}")
                    m5.metric("夏普比率", f"{metrics['sharpe_ratio']:.2f}")
                    m6.metric("超额收益", f"{metrics['excess_return']:.2%}")

                    curve = pd.DataFrame(quant_result["equity_curve"])
                    curve["date"] = pd.to_datetime(curve["date"])
                    fig = go.Figure()
                    fig.add_trace(
                        go.Scatter(
                            x=curve["date"],
                            y=curve["equity"],
                            name="策略权益",
                            line=dict(color="#166534", width=2.4),
                        )
                    )
                    fig.add_trace(
                        go.Scatter(
                            x=curve["date"],
                            y=curve["benchmark_equity"],
                            name="买入持有基准",
                            line=dict(color="#64748B", width=1.5, dash="dot"),
                        )
                    )
                    fig.update_layout(
                        height=430,
                        hovermode="x unified",
                        margin=dict(l=0, r=0, t=35, b=0),
                        legend=dict(orientation="h", y=1.08),
                        yaxis_title="组合权益",
                        plot_bgcolor="white",
                        paper_bgcolor="white",
                    )
                    st.plotly_chart(fig, width="stretch")

                    details1, details2 = st.columns([1, 1.5])
                    with details1:
                        st.markdown("#### 风险与执行")
                        risk_table = pd.DataFrame(
                            [
                                ["年化波动", f"{metrics['annual_volatility']:.2%}"],
                                ["Calmar", f"{metrics['calmar_ratio']:.2f}"],
                                ["胜率", f"{metrics['win_rate']:.2%}"],
                                ["持仓暴露", f"{metrics['exposure']:.2%}"],
                                ["交易次数", str(metrics["trade_count"])],
                            ],
                            columns=["指标", "结果"],
                        )
                        st.dataframe(risk_table, hide_index=True, width="stretch")
                    with details2:
                        st.markdown("#### 交易流水")
                        trades = pd.DataFrame(quant_result["trades"])
                        if trades.empty:
                            st.info("回测区间内没有触发交易")
                        else:
                            trades["action"] = trades["action"].map(
                                {"buy": "买入", "sell": "卖出"}
                            )
                            trades = trades.rename(
                                columns={
                                    "date": "日期",
                                    "action": "方向",
                                    "price": "成交净值",
                                    "position_after": "交易后仓位",
                                    "estimated_cost": "估算成本",
                                }
                            )
                            st.dataframe(trades, hide_index=True, width="stretch", height=250)

    with optimize_tab:
        auto_strategy_options = {
            "双均线趋势": "ma_cross",
            "动量轮动": "momentum",
        }
        objective_options = {
            "稳健均衡": "balanced",
            "夏普优先": "sharpe",
            "收益优先": "return",
        }
        depth_options = {
            "快速": "fast",
            "标准": "standard",
            "深入": "deep",
        }
        train_options = {"1 年": 244, "2 年": 488, "3 年": 732}
        test_options = {"3 个月": 61, "6 个月": 122, "1 年": 244}

        with st.form("walk_forward_form"):
            auto_strategy_label = st.segmented_control(
                "优化策略",
                list(auto_strategy_options),
                default="双均线趋势",
                width="stretch",
            )
            a1, a2, a3, a4 = st.columns(4)
            with a1:
                auto_code = st.text_input("基金代码", value="510300", key="auto_code")
                auto_capital = st.number_input(
                    "初始资金", min_value=1000, value=100000, step=10000, key="auto_capital"
                )
            with a2:
                auto_start = st.date_input(
                    "分析开始", datetime(2018, 1, 1), key="auto_start"
                )
                auto_end = st.date_input("分析结束", datetime.now(), key="auto_end")
            with a3:
                train_label = st.selectbox("训练窗口", list(train_options), index=1)
                test_label = st.selectbox("验证窗口", list(test_options), index=1)
            with a4:
                objective_label = st.selectbox("优化目标", list(objective_options), index=0)
                search_depth_label = st.selectbox("搜索深度", list(depth_options), index=1)

            costs1, costs2 = st.columns(2)
            with costs1:
                auto_commission = st.number_input(
                    "单边手续费 (%)", 0.0, 5.0, 0.15, 0.05, key="auto_commission"
                )
            with costs2:
                auto_slippage = st.number_input(
                    "滑点 (%)", 0.0, 5.0, 0.05, 0.05, key="auto_slippage"
                )
            run_auto = st.form_submit_button(
                "运行 Walk-Forward 自优化", type="primary", width="stretch"
            )

        if run_auto:
            if auto_start >= auto_end:
                st.error("分析结束日期必须晚于开始日期")
            elif not auto_code.strip():
                st.error("请输入基金代码")
            else:
                with st.spinner("正在滚动训练参数并验证样本外表现..."):
                    auto_result = comps["walk_forward"].optimize(
                        auto_code.strip(),
                        auto_start.strftime("%Y-%m-%d"),
                        auto_end.strftime("%Y-%m-%d"),
                        strategy=auto_strategy_options[auto_strategy_label],
                        initial_capital=auto_capital,
                        commission_rate=auto_commission / 100,
                        slippage_rate=auto_slippage / 100,
                        train_days=train_options[train_label],
                        test_days=test_options[test_label],
                        objective=objective_options[objective_label],
                        search_space=depth_options[search_depth_label],
                    )

                if "error" in auto_result:
                    st.error(auto_result["error"])
                else:
                    if auto_result.get("data_warning"):
                        st.warning(auto_result["data_warning"])

                    auto_metrics = auto_result["oos_metrics"]
                    diagnostics = auto_result["diagnostics"]
                    st.markdown("### 样本外结论")
                    r1, r2, r3, r4, r5, r6 = st.columns(6)
                    r1.metric("推荐参数", auto_result["recommended_label"])
                    r2.metric(
                        "可靠性",
                        f"{diagnostics['reliability_score']:.0f}/100",
                        f"{diagnostics['grade']} · {diagnostics['verdict']}",
                        delta_color="off",
                    )
                    r3.metric("样本外收益", f"{auto_metrics['total_return']:.2%}")
                    r4.metric("超额收益", f"{auto_metrics['excess_return']:.2%}")
                    r5.metric("最大回撤", f"{auto_metrics['max_drawdown']:.2%}")
                    r6.metric("夏普比率", f"{auto_metrics['sharpe_ratio']:.2f}")

                    verdict_text = (
                        f"{auto_result['fold_count']} 个验证窗口 · "
                        f"{auto_result['candidate_count']} 组候选参数 · "
                        f"{auto_result['objective_name']}"
                    )
                    if diagnostics["grade"] in {"A", "B"}:
                        st.success(f"{diagnostics['verdict']} · {verdict_text}")
                    else:
                        st.warning(f"{diagnostics['verdict']} · {verdict_text}")

                    auto_curve = pd.DataFrame(auto_result["oos_curve"])
                    auto_curve["date"] = pd.to_datetime(auto_curve["date"])
                    auto_fig = go.Figure()
                    auto_fig.add_trace(
                        go.Scatter(
                            x=auto_curve["date"],
                            y=auto_curve["equity"],
                            name="自优化样本外权益",
                            line=dict(color="#166534", width=2.4),
                        )
                    )
                    auto_fig.add_trace(
                        go.Scatter(
                            x=auto_curve["date"],
                            y=auto_curve["benchmark_equity"],
                            name="买入持有基准",
                            line=dict(color="#64748B", width=1.5, dash="dot"),
                        )
                    )
                    auto_fig.update_layout(
                        height=430,
                        hovermode="x unified",
                        margin=dict(l=0, r=0, t=35, b=0),
                        legend=dict(orientation="h", y=1.08),
                        yaxis_title="样本外权益",
                        plot_bgcolor="white",
                        paper_bgcolor="white",
                    )
                    st.plotly_chart(auto_fig, width="stretch")

                    diag1, diag2, diag3, diag4 = st.columns(4)
                    diag1.metric("参数稳定度", f"{diagnostics['parameter_stability']:.0%}")
                    diag2.metric("正收益窗口", f"{diagnostics['positive_fold_rate']:.0%}")
                    diag3.metric("跑赢基准窗口", f"{diagnostics['outperform_fold_rate']:.0%}")
                    diag4.metric("训练-验证差距", f"{diagnostics['overfit_gap']:.2f}")

                    fold_tab, frequency_tab = st.tabs(["窗口验证", "参数稳定性"])
                    with fold_tab:
                        fold_table = pd.DataFrame(auto_result["folds"])
                        fold_table = fold_table[
                            [
                                "fold", "test_start", "test_end", "parameter_label",
                                "train_return", "test_return", "benchmark_return",
                                "test_sharpe", "test_max_drawdown", "trade_count",
                            ]
                        ].rename(
                            columns={
                                "fold": "窗口",
                                "test_start": "验证开始",
                                "test_end": "验证结束",
                                "parameter_label": "选中参数",
                                "train_return": "训练收益",
                                "test_return": "验证收益",
                                "benchmark_return": "基准收益",
                                "test_sharpe": "验证夏普",
                                "test_max_drawdown": "验证回撤",
                                "trade_count": "交易次数",
                            }
                        )
                        st.dataframe(
                            fold_table,
                            hide_index=True,
                            width="stretch",
                            column_config={
                                "训练收益": st.column_config.NumberColumn(format="percent"),
                                "验证收益": st.column_config.NumberColumn(format="percent"),
                                "基准收益": st.column_config.NumberColumn(format="percent"),
                                "验证夏普": st.column_config.NumberColumn(format="%.2f"),
                                "验证回撤": st.column_config.NumberColumn(format="percent"),
                            },
                        )
                    with frequency_tab:
                        frequency = pd.DataFrame(auto_result["parameter_frequency"])
                        frequency_fig = go.Figure(
                            go.Bar(
                                x=frequency["share"],
                                y=frequency["parameter_label"],
                                orientation="h",
                                marker_color="#2563EB",
                                text=[f"{value:.0%}" for value in frequency["share"]],
                                textposition="outside",
                                cliponaxis=False,
                            )
                        )
                        frequency_fig.update_layout(
                            height=max(260, 46 * len(frequency)),
                            margin=dict(l=0, r=50, t=20, b=20),
                            xaxis=dict(title="被选中比例", tickformat=".0%", range=[0, 1.05]),
                            yaxis_title="",
                            plot_bgcolor="white",
                            paper_bgcolor="white",
                        )
                        st.plotly_chart(frequency_fig, width="stretch")

    with dca_tab:
        with st.form("dca_backtest_form"):
            d1, d2, d3 = st.columns(3)
            with d1:
                fund_code = st.text_input("基金代码", value="510300", key="dca_code")
                mode = st.selectbox("定投模式", ["普通定投", "智能均线定投"])
            with d2:
                amount = st.number_input("单期投入", value=1000, min_value=100, step=100)
                freq = st.selectbox("定投频率", ["每月", "每周"])
            with d3:
                start_date = st.date_input("开始日期", datetime(2018, 1, 1), key="dca_start")
                ma_window = st.number_input(
                    "参考均线", value=250, min_value=10, step=10, disabled=mode != "智能均线定投"
                )
            run_dca = st.form_submit_button("运行定投回测", type="primary", width="stretch")

        if run_dca:
            result = comps["backtest"].run_dca(
                fund_code,
                start_date.strftime("%Y-%m-%d"),
                datetime.now().strftime("%Y-%m-%d"),
                amount,
                "M" if freq == "每月" else "W",
                "ma" if mode == "智能均线定投" else "normal",
                ma_window,
            )
            if "error" in result:
                st.error(result["error"])
            else:
                if result.get("data_warning"):
                    st.warning(result["data_warning"])
                cost = result["总投入"]
                value = result["期末市值"]
                dca1, dca2, dca3 = st.columns(3)
                dca1.metric("累计投入", f"¥{cost:,.2f}")
                dca2.metric("期末市值", f"¥{value:,.2f}")
                dca3.metric("累计收益率", result["总收益率"])

                history = pd.DataFrame(result["历史详情"])
                history["date"] = pd.to_datetime(history["date"])
                fig = go.Figure()
                fig.add_trace(
                    go.Scatter(
                        x=history["date"], y=history["total_cost"], name="累计本金",
                        line=dict(color="#64748B", dash="dot")
                    )
                )
                fig.add_trace(
                    go.Scatter(
                        x=history["date"], y=history["market_value"], name="持仓市值",
                        line=dict(color="#166534", width=2.4)
                    )
                )
                fig.update_layout(height=400, margin=dict(l=0, r=0, t=30, b=0))
                st.plotly_chart(fig, width="stretch")

# ----------------- 页面 3.5：定投复利计算器 -----------------
elif page == "🧮 定投复利计算器":
    st.markdown('<div class="main-header">🧮 定投复利计算器</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-text">"复利是世界第八大奇迹。知之者赚，不知之者被赚。" —— 测算你的定投目标与长线收益。</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([1, 2.5])
    
    with col1:
        st.subheader("⚙️ 设定定投计划")
        
        with st.form("calc_form"):
            initial_amount = st.number_input("初始本金 (元)", value=0, min_value=0, step=1000)
            periodic_amount = st.number_input("每期定投金额 (元)", value=2000, min_value=100, step=500)
            
            period_type = st.selectbox("定投频率", ["每月", "每周", "每年"])
            years = st.number_input("坚持投资年限 (年)", value=10, min_value=1, max_value=50, step=1)
            
            annual_rate = st.number_input("预期年化收益率 (%)", value=8.0, min_value=1.0, max_value=100.0, step=0.5)
            
            st.markdown("<br>", unsafe_allow_html=True)
            submitted = st.form_submit_button("💰 计算财富轨迹", width="stretch")
            
    with col2:
        st.subheader("📈 财富增长轨迹")
        
        # 将年化收益转换为对应周期的收益率
        periods_per_year = 12 if period_type == "每月" else (52 if period_type == "每周" else 1)
        total_periods = years * periods_per_year
        rate_per_period = annual_rate / 100 / periods_per_year
        
        # 计算每一期的数据
        data = []
        current_principal = initial_amount
        current_value = initial_amount
        
        for i in range(1, total_periods + 1):
            current_principal += periodic_amount
            # 简化计算：每期初投入，计算一期利息
            current_value = (current_value + periodic_amount) * (1 + rate_per_period)
            
            # 为了图表清晰，我们只记录每年的年底数据
            if i % periods_per_year == 0:
                year_num = i // periods_per_year
                data.append({
                    "年份": f"第 {year_num} 年",
                    "累计本金": round(current_principal, 2),
                    "累计利息": round(current_value - current_principal, 2),
                    "总资产": round(current_value, 2)
                })
                
        if not data:
             st.info("👈 请在左侧设定你的定投计划并点击计算")
        else:
            df = pd.DataFrame(data)
            
            # 顶部结果卡片
            final_data = data[-1]
            total_invested = final_data["累计本金"]
            final_wealth = final_data["总资产"]
            total_interest = final_data["累计利息"]
            profit_pct = (final_wealth / total_invested - 1) * 100 if total_invested > 0 else 0
            
            c1, c2, c3 = st.columns(3)
            c1.metric("累计投入本金", f"¥ {total_invested:,.0f}")
            c2.metric("累计获得利息", f"¥ {total_interest:,.0f}", f"总收益率: {profit_pct:.1f}%")
            c3.metric("期末最终总资产", f"¥ {final_wealth:,.0f}")
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # 绘制堆叠柱状图
            fig = go.Figure()
            
            fig.add_trace(go.Bar(
                x=df['年份'],
                y=df['累计本金'],
                name='投入本金',
                marker_color='#93C5FD' # 浅蓝色
            ))
            
            fig.add_trace(go.Bar(
                x=df['年份'],
                y=df['累计利息'],
                name='复利利息',
                marker_color='#FDE047' # 浅黄色
            ))
            
            fig.add_trace(go.Scatter(
                x=df['年份'],
                y=df['总资产'],
                mode='lines+markers',
                name='总资产趋势',
                line=dict(color='#2563EB', width=2),
                marker=dict(size=6)
            ))
            
            fig.update_layout(
                barmode='stack',
                hovermode="x unified",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                margin=dict(l=0, r=0, t=30, b=0),
                yaxis=dict(title="金额 (元)", side="left"),
                height=400,
                plot_bgcolor='white',
                paper_bgcolor='white'
            )
            fig.update_xaxes(showgrid=True, gridcolor='rgba(0,0,0,0.05)')
            fig.update_yaxes(showgrid=True, gridcolor='rgba(0,0,0,0.05)')
            
            st.plotly_chart(fig, width="stretch")
            
            # 显示详细表格
            with st.expander("查看每年详细数据"):
                # 格式化表格显示
                st.dataframe(
                    df.style.format({
                        '累计本金': '¥ {:,.2f}',
                        '累计利息': '¥ {:,.2f}',
                        '总资产': '¥ {:,.2f}'
                    }),
                    width="stretch"
                )

# ----------------- 页面四：资产配置 -----------------
elif page == "⚖️ 智能资产配置":
    st.markdown('<div class="main-header">AI 智能资产配置 (Risk Parity)</div>', unsafe_allow_html=True)
    st.markdown("不要把鸡蛋放在同一个篮子里。系统基于**桥水基金的风险平价理论**，自动为您计算不同资产的最佳配比，让波动互相抵消。")
    
    # 自动带入用户的持仓
    holdings_df = pm.get_holdings()
    default_codes = "510300, 511010, 513100, 518880" # 默认: 沪深300 + 国债 + 纳指 + 黄金
    
    user_has_holding = False
    if not holdings_df.empty and len(holdings_df) >= 2:
        default_codes = ", ".join(holdings_df['fund_code'].tolist())
        user_has_holding = True
        
    st.info("💡 提示：输入跨类别的资产（如：宽基股票+债券+黄金+海外）能获得最佳的平衡效果。")
    
    fund_codes_input = st.text_input("候选基金池 (代码间逗号分隔)", value=default_codes)
    
    if st.button("🧠 执行最优化模型计算", type="primary"):
        codes = [c.strip() for c in fund_codes_input.split(",") if c.strip()]
        
        if len(codes) < 2:
            st.error("至少需要2只基金才能进行资产配置！")
        else:
            with st.spinner("AI正在计算协方差矩阵与风险贡献..."):
                start_str = (datetime.now() - timedelta(days=365*2)).strftime("%Y-%m-%d")
                end_str = datetime.now().strftime("%Y-%m-%d")
                
                optimizer = comps["optimizer"]
                result = optimizer.optimize_risk_parity(codes, start_str, end_str)
                
                if "error" in result:
                    st.error(f"计算失败: {result['error']}")
                else:
                    st.markdown("### 🎯 目标配比建议")
                    
                    # 取数据
                    weights = result["权重分配"]
                    weight_df = pd.DataFrame([
                        {"代码": k, "名称": api.get_fund_info(k).get("基金简称", k), 
                         "目标仓位": v * 100} for k, v in weights.items()
                    ])
                    
                    c1, c2 = st.columns([1, 1])
                    
                    with c1:
                        fig = px.pie(weight_df, values='目标仓位', names='名称', hole=0.5,
                                   color_discrete_sequence=px.colors.qualitative.Set3)
                        fig.update_traces(textposition='inside', textinfo='percent+label')
                        fig.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=10))
                        st.plotly_chart(fig, width="stretch")
                        
                    with c2:
                        st.markdown("<br><br>", unsafe_allow_html=True)
                        st.metric("模型预期年化收益", result["预期年化收益"])
                        st.metric("模型预期年化波动率", result["预期年化波动率"], delta="极低波动", delta_color="normal")
                        st.caption("基于过去两年的历史数据推演。")
                        
                    # 动态调仓指南
                    if user_has_holding:
                        st.markdown("### 🔄 动态调仓操作指南")
                        st.markdown("基于您当前的实际持仓金额，要达到模型建议的比例，请执行以下操作：")
                        
                        # 重新计算当前总资产
                        total_assets = 0
                        current_dict = {}
                        for _, row in holdings_df.iterrows():
                            c = row['fund_code']
                            nav_df = api.get_fund_nav(c)
                            n = float(nav_df.iloc[-1]['unit_nav']) if not nav_df.empty else 1.0
                            val = row['shares'] * n
                            current_dict[c] = val
                            total_assets += val
                            
                        action_data = []
                        for code in codes:
                            target_w = weights.get(code, 0)
                            current_w = current_dict.get(code, 0) / total_assets if total_assets > 0 else 0
                            
                            target_amt = total_assets * target_w
                            current_amt = current_dict.get(code, 0)
                            diff_amt = target_amt - current_amt
                            
                            if abs(diff_amt) < 100:
                                action = "保持"
                            elif diff_amt > 0:
                                action = "🟢 买入"
                            else:
                                action = "🔴 卖出"
                                
                            action_data.append({
                                "基金名称": api.get_fund_info(code).get("基金简称", code),
                                "当前配比": f"{current_w*100:.1f}%",
                                "目标配比": f"{target_w*100:.1f}%",
                                "操作建议": action,
                                "交易金额": f"¥ {abs(diff_amt):,.0f}"
                            })
                            
                        st.dataframe(pd.DataFrame(action_data), width="stretch")
                    else:
                        st.info("📌 您目前没有录入持仓数据。建议您按上方饼图比例建仓。")

# ----------------- 页面五：新闻检索 -----------------
elif page == "📰 市场新闻检索":
    st.markdown('<div class="main-header">市场新闻检索</div>', unsafe_allow_html=True)

    with st.form("news_search_form"):
        n1, n2, n3 = st.columns([2.2, 1.2, 0.8])
        with n1:
            news_query = st.text_input("基金代码或关键词", value="510300")
        with n2:
            news_scope_label = st.segmented_control(
                "检索范围", ["个股与基金", "全球快讯"], default="个股与基金", width="stretch"
            )
        with n3:
            news_limit = st.number_input("结果数量", min_value=5, max_value=50, value=10, step=5)
        search_news = st.form_submit_button("检索新闻", type="primary", width="stretch")

    if search_news:
        scope = "keyword" if news_scope_label == "个股与基金" else "global"
        with st.spinner("正在同步新闻源..."):
            news_result = comps["news"].search(news_query, scope=scope, limit=news_limit)

        if news_result.warning:
            if news_result.stale:
                st.warning(news_result.warning)
            else:
                st.error(news_result.warning)

        if news_result.items.empty:
            st.info("没有找到匹配的新闻")
        else:
            cache_label = "缓存结果" if news_result.from_cache else "实时结果"
            st.caption(f"{cache_label} · {len(news_result.items)} 条")
            for _, news_item in news_result.items.iterrows():
                with st.container(border=True):
                    published_at = news_item["published_at"]
                    published = (
                        published_at.strftime("%Y-%m-%d %H:%M")
                        if pd.notna(published_at)
                        else "时间未知"
                    )
                    st.markdown(f"#### {news_item['title']}")
                    st.caption(f"{news_item['source'] or '来源未知'} · {published}")
                    if news_item["summary"]:
                        st.write(news_item["summary"])
                    url = str(news_item["url"])
                    if url.startswith(("http://", "https://")):
                        st.link_button("打开原文", url, width="content")

# ----------------- 页面六：AI 智能诊断 -----------------
elif page == "🤖 AI 智能诊断":
    st.markdown('<div class="main-header">🤖 AI 智能诊断中心</div>', unsafe_allow_html=True)
    st.markdown("接入大语言模型，为您的持仓进行深度体检，用自然语言为您解答专业数据。")
    
    ai = comps["ai"]
    
    if not ai.config.get("api_key") or not ai.config.get("model"):
        st.warning("请先前往『全局系统设置』配置 API Key 和 Model ID。")
    
    tab1, tab2 = st.tabs(["💼 整体持仓深度体检", "🔍 单只基金投资价值分析"])
    
    with tab1:
        st.subheader("为当前持仓生成专业诊断报告")
        if st.button("🚀 开始全局诊断", type="primary"):
            if not ai.config.get("api_key") or not ai.config.get("model"):
                st.error("请先配置模型接口。")
            else:
                with st.spinner("AI 正在深度剖析您的持仓架构，计算风险收益比... 请稍候片刻..."):
                    report = ai.generate_portfolio_diagnosis()
                    st.markdown("### 📋 诊断报告")
                    if report.startswith("AI 调用失败:"):
                        st.error(report)
                    else:
                        st.markdown(report)
                    
    with tab2:
        st.subheader("让 AI 帮你看透一只基金")
        col1, col2 = st.columns([1, 2])
        with col1:
            query_code = st.text_input("想让 AI 分析的基金代码", value="510300", key="ai_fund_code")
            analyze_btn = st.button("⚡ 开始透视这只基金")
            
        if analyze_btn:
            if not ai.config.get("api_key") or not ai.config.get("model"):
                st.error("请先配置模型接口。")
            else:
                with st.spinner(f"正在调取 {query_code} 的各项核心数据喂给大模型..."):
                    fund_report = ai.analyze_single_fund_prospect(query_code)
                    st.markdown("### 📊 分析报告")
                    if fund_report.startswith("AI 调用失败:"):
                        st.error(fund_report)
                    else:
                        st.markdown(fund_report)


# ----------------- 页面七：系统设置 -----------------
elif page == "⚙️ 全局系统设置":
    st.markdown('<div class="main-header">⚙️ 全局系统设置</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-text">配置数据源接口参数与大语言模型 (LLM) 参数。</div>', unsafe_allow_html=True)
    
    # ------------------ 状态初始化 ------------------
    if "llm_config" not in st.session_state:
        st.session_state.llm_config = dict(comps["ai"].config)
        
    if "data_config" not in st.session_state:
        st.session_state.data_config = {
            "data_source": "天天基金/东方财富 (默认)",
            "cache_hours": 24,
            "timeout_sec": 10
        }
        
    llm_conf = st.session_state.llm_config
    data_conf = st.session_state.data_config
    
    # ------------------ 设置面板 ------------------
    tab1, tab2 = st.tabs(["🤖 AI 模型接口设置", "📡 金融数据源设置"])
    
    with tab1:
        st.subheader("第三方模型接口")

        provider_keys = list(PROVIDER_LABELS)
        current_provider = llm_conf.get("provider", provider_keys[0])
        if current_provider not in provider_keys:
            current_provider = provider_keys[0]

        with st.form("llm_settings_form"):
            provider = st.selectbox(
                "接口协议",
                provider_keys,
                index=provider_keys.index(current_provider),
                format_func=lambda value: PROVIDER_LABELS[value],
            )
            c1, c2 = st.columns(2)
            with c1:
                base_url = st.text_input(
                    "API Base URL",
                    value=llm_conf.get("base_url", ""),
                    placeholder="https://gateway.example/v1",
                    help="留空使用 SDK 官方地址；第三方 Responses/Chat 地址通常需要包含 /v1。",
                )
                model = st.text_input(
                    "Model ID",
                    value=llm_conf.get("model", ""),
                    placeholder="填写第三方平台提供的模型 ID",
                )
            with c2:
                api_key = st.text_input(
                    "API Key", value=llm_conf.get("api_key", ""), type="password"
                )
                timeout_seconds = st.number_input(
                    "请求超时 (秒)",
                    min_value=5,
                    max_value=300,
                    value=int(llm_conf.get("timeout_seconds", 120)),
                    step=5,
                )
                max_tokens = st.number_input(
                    "最大输出 Tokens",
                    min_value=64,
                    max_value=8192,
                    value=int(llm_conf.get("max_tokens", 900)),
                    step=64,
                )

            b1, b2, b3 = st.columns(3)
            with b1:
                save_llm = st.form_submit_button("保存配置", type="primary", width="stretch")
            with b2:
                test_llm = st.form_submit_button("测试连接", width="stretch")
            with b3:
                discover_llm = st.form_submit_button("读取模型列表", width="stretch")

        if save_llm or test_llm or discover_llm:
            new_llm_config = {
                "provider": provider,
                "api_key": api_key,
                "base_url": base_url.strip(),
                "model": model.strip(),
                "timeout_seconds": timeout_seconds,
                "max_tokens": max_tokens,
                "temperature": float(llm_conf.get("temperature", 0.3)),
            }
            st.session_state.llm_config = new_llm_config
            comps["ai"].update_config(new_llm_config)

            if save_llm:
                st.success("模型配置已在当前会话生效。")
            if test_llm:
                try:
                    with st.spinner("正在测试接口..."):
                        test_response = comps["ai"].test_connection()
                    st.success(f"连接成功：{test_response[:120]}")
                except Exception as exc:
                    st.error(f"连接失败：{exc}")
            if discover_llm:
                try:
                    with st.spinner("正在读取模型列表..."):
                        st.session_state.llm_models = comps["ai"].list_models()
                    st.success(f"已读取 {len(st.session_state.llm_models)} 个模型。")
                except Exception as exc:
                    st.session_state.llm_models = []
                    st.error(f"模型列表读取失败：{exc}")

        if st.session_state.get("llm_models"):
            with st.expander("可用模型", expanded=True):
                st.dataframe(
                    pd.DataFrame({"Model ID": st.session_state.llm_models}),
                    hide_index=True,
                    width="stretch",
                    height=min(320, 38 * len(st.session_state.llm_models) + 38),
                )

        with st.expander("协议与环境变量"):
            protocol_table = pd.DataFrame(
                [
                    ["Codex / Responses", "CODEX_API_KEY", "CODEX_BASE_URL", "CODEX_MODEL"],
                    ["CC / Anthropic Messages", "CC_API_KEY", "CC_BASE_URL", "CC_MODEL"],
                    ["OpenAI Chat 兼容", "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL"],
                ],
                columns=["协议", "Key", "Base URL", "Model"],
            )
            st.dataframe(protocol_table, hide_index=True, width="stretch")

    with tab2:
        st.subheader("金融数据接口配置")
        st.caption("底层的净值、持仓和基础信息获取方式配置。")
        
        with st.container():
            data_source = st.selectbox("首选数据源", 
                                     ["天天基金/东方财富 (默认)", "雪球 (备用)"],
                                     index=0 if "天天" in data_conf["data_source"] else 1,
                                     help="底层均基于 AKShare 聚合封装。")
                                     
            c3, c4 = st.columns(2)
            with c3:
                cache_hours = st.number_input("本地缓存有效期 (小时)", 
                                            min_value=1, max_value=72, value=data_conf["cache_hours"],
                                            help="防止频繁调用导致IP被封禁。设置为 24 表示每天只拉取一次最新净值。")
            with c4:
                timeout_sec = st.number_input("网络请求超时 (秒)", 
                                            min_value=3, max_value=30, value=data_conf["timeout_sec"])
                                            
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("💾 保存数据源配置", type="primary", key="save_data"):
                st.session_state.data_config = {
                    "data_source": data_source,
                    "cache_hours": cache_hours,
                    "timeout_sec": timeout_sec
                }
                st.success("✅ 数据源配置已更新！（缓存时间将在下次拉取时生效）")
                
        st.markdown("---")
        st.warning("🚨 **防封禁提示**：本项目使用的 AKShare 数据属于公开网页爬取。请勿将缓存时间设置过低（建议大于 12 小时），否则可能导致您的机器 IP 被天天基金或东方财富的防火墙临时封禁。")
