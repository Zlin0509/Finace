# FundMaster Pro

基金持仓、量化回测、新闻检索和第三方模型分析工具。提供 Streamlit 界面和 `fund` CLI。

## 功能

- 持仓记账、净值分析和风险指标
- 同花顺官方 A 股行情快照、历史日 K 与基金披露持仓贡献分析
- 买入持有、双均线、动量轮动及定投回测
- Walk-Forward 参数自优化、样本外验证、稳定性与过拟合诊断
- 手续费、滑点、基准权益、回撤和逐笔交易记录
- 基金/个股新闻与全球财经快讯检索，支持本地缓存降级
- Codex / OpenAI Responses、CC / Anthropic Messages、OpenAI Chat 兼容接口
- 自定义第三方 API Base URL、Model ID、API Key 和超时

完整界面说明、标注截图和推荐分析流程见 [产品解析与操作指南](docs/PRODUCT_GUIDE.md)。

## 启动

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
streamlit run src/ui/app.py
```

命令行入口：

```bash
fund --help
fund stock 600519.SH --days 365 --adjust forward
fund quant 510300 --start 2020-01-01 --end 2026-01-01 --strategy ma_cross
fund auto-optimize 510300 --start 2018-01-01 --end 2026-01-01 --strategy ma_cross
fund news 510300 --scope keyword --limit 10
```

## A 股行情接口

在同花顺金融数据服务后台创建 API Key，然后通过“全局系统设置 > A股行情接口”在当前会话中配置。也可以设置环境变量：

```bash
export HITHINK_FINANCE_API_KEY="your-api-key"
```

行情数据来自同花顺 Financial-API，当前接入最新行情快照和前复权/不复权/后复权历史日 K。基金持仓贡献基于基金公开披露的季度持仓，仅表示已披露 A 股对当日涨跌的估算贡献，不代表实时完整仓位或最终基金净值。

## 第三方模型接口

可以在“全局系统设置”页面中配置并测试连接。配置只在当前 Streamlit 会话中保存，不会写入仓库。

也可以复制 [.env.example](.env.example) 中的变量到本机环境。Codex 接口使用 OpenAI Responses 协议；CC 接口使用 Claude Code 底层对应的 Anthropic Messages 协议。第三方网关必须兼容所选协议，OpenAI 兼容地址通常需要包含 `/v1`。

环境变量优先级：

| 协议 | API Key | Base URL | Model |
| --- | --- | --- | --- |
| Codex / Responses | `CODEX_API_KEY` | `CODEX_BASE_URL` | `CODEX_MODEL` |
| CC / Messages | `CC_API_KEY` | `CC_BASE_URL` | `CC_MODEL` |
| OpenAI Chat | `OPENAI_API_KEY` | `OPENAI_BASE_URL` | `OPENAI_MODEL` |

## 回测约定

- 双均线和动量信号在收盘后生成，延迟到下一交易日生效，避免前视偏差。
- 当前执行模型为全仓基金或空仓，不支持做空。
- 每次仓位变化计入手续费和滑点，回测结束时强制平仓。
- 自优化只在滚动训练窗口中选择参数，并在紧随其后的未见数据上验证。
- 自优化主结果为所有样本外窗口串联后的权益，不以训练期最优收益作为结论。
- 结果只反映历史净值和设定规则，不构成投资建议。

## 测试

```bash
pytest -q
```

测试覆盖量化策略、交易成本、新闻缓存降级以及两类第三方模型协议适配。
