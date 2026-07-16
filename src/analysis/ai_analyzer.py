import json
from typing import Optional

from src.data.fund_api import FundDataAPI
from src.analysis.engine import AnalysisEngine
from src.integrations.llm_gateway import LLMConfig, LLMGateway
from src.portfolio.manager import PortfolioManager

class AIFundAnalyzer:
    def __init__(
        self,
        llm_config: Optional[LLMConfig] = None,
        portfolio_manager: Optional[PortfolioManager] = None,
    ):
        self.gateway = LLMGateway(llm_config or LLMConfig.from_env())
        self.config = self.gateway.config.to_dict()
        self.api = FundDataAPI()
        self.engine = AnalysisEngine()
        self.pm = portfolio_manager or PortfolioManager()
        
    def update_config(self, config_dict: dict):
        """更新模型配置"""
        self.gateway.update_config(config_dict)
        self.config = self.gateway.config.to_dict()

    def test_connection(self) -> str:
        """发送最小请求以验证当前第三方 API 配置。"""
        return self.gateway.test_connection()

    def list_models(self):
        """读取当前第三方接口可用的模型 ID。"""
        return self.gateway.list_models()
        
    def _call_llm(self, prompt: str, system_prompt: str = "") -> str:
        """统一的 LLM 调用接口"""
        if not self.config.get("api_key") or not self.config.get("model"):
            return "请先在『系统设置』页面配置 API Key 和 Model ID"

        try:
            return self.gateway.generate(prompt, system_prompt)
        except Exception as e:
            return f"AI 调用失败: {str(e)}"

        
    def generate_portfolio_diagnosis(self) -> str:
        """生成整体持仓诊断报告"""
        holdings = self.pm.get_holdings()
        if holdings.empty:
            return "当前无持仓数据，无法进行诊断。"
            
        # 收集持仓信息用于喂给 AI
        portfolio_info = []
        for _, row in holdings.iterrows():
            code = row['fund_code']
            info = self.api.get_fund_info(code)
            metrics = self.engine.analyze_fund(code)
            
            nav_df = self.api.get_fund_nav(code)
            latest_nav = float(nav_df.iloc[-1]['unit_nav']) if not nav_df.empty else 0
            current_value = row['shares'] * latest_nav
            profit = current_value - row['cost']
            
            portfolio_info.append({
                "基金名称": info.get("基金简称", code),
                "代码": code,
                "持仓金额": round(current_value, 2),
                "持仓盈亏": round(profit, 2),
                "历史最大回撤": metrics.get("最大回撤", "未知"),
                "历史年化收益": metrics.get("年化收益", "未知"),
                "夏普比率": metrics.get("夏普比率", "未知")
            })
            
        # 构建给 AI 的 prompt
        prompt = f"""
        你是一位专业的金融理财规划师和基金分析师。请根据用户以下的基金持仓情况，给出一份专业的诊断报告。
        
        【用户当前持仓数据】：
        {json.dumps(portfolio_info, ensure_ascii=False, indent=2)}
        
        请从以下几个维度进行深度分析：
        1. 整体资产配置评价（是否过于集中在某个赛道，风险是否分散）
        2. 收益与风险性价比诊断（基于夏普比率和最大回撤）
        3. 针对亏损/盈利情况的专业建议（止盈/加仓/调仓策略）
        
        要求：
        - 语言专业但不晦涩，使用 Markdown 格式排版
        - 突出重点，如果有非常差的标的要明确指出来
        - 不要写免责声明中的套话，直接给出干货建议
        """
        
        system_prompt = "你是一个专业的基金量化分析师，擅长资产配置和持仓诊断。"
        return self._call_llm(prompt, system_prompt)
            
    def analyze_single_fund_prospect(self, fund_code: str) -> str:
        """分析单只基金的投资价值"""
        info = self.api.get_fund_info(fund_code)
        metrics = self.engine.analyze_fund(fund_code)
        
        prompt = f"""
        请深度评测这只基金的投资价值：
        
        基金名称：{info.get('基金简称', '未知')}
        基金代码：{fund_code}
        历史年化收益：{metrics.get('年化收益', '未知')}
        历史最大回撤：{metrics.get('最大回撤', '未知')}
        夏普比率：{metrics.get('夏普比率', '未知')}
        
        请分析：
        1. 该基金的风险收益特征属于什么类型？
        2. 基于它的最大回撤和收益率，它的持有体验如何？
        3. 这只基金适合什么样风险偏好的投资者？适合定投还是网格交易？
        
        使用 Markdown 格式输出。
        """
        
        return self._call_llm(prompt)
