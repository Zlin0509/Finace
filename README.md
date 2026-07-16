# FundMaster Pro

基金持仓、量化回测、新闻检索和第三方模型分析工具。提供 Streamlit 界面和 `fund` CLI。当前版本：`0.2.0`。

## 功能

- 持仓记账、净值分析和风险指标
- 同花顺官方 A 股行情快照、历史日 K 与基金披露持仓贡献分析
- 买入持有、双均线、动量轮动及定投回测
- Walk-Forward 参数自优化、样本外验证、稳定性与过拟合诊断
- 手续费、滑点、基准权益、回撤和逐笔交易记录
- 基金/个股新闻与全球财经快讯检索，支持本地缓存降级
- Codex / OpenAI Responses、CC / Anthropic Messages、OpenAI Chat 兼容接口
- 自定义第三方 API Base URL、Model ID、API Key 和超时
- SQLite 本地持久化、旧 JSON 自动迁移、每日备份和无密钥数据导出

完整界面说明、标注截图和推荐分析流程见 [产品解析与操作指南](docs/PRODUCT_GUIDE.md)。

## 启动

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
streamlit run src/ui/app.py
# 安装后也可以直接运行：fund ui
```

命令行入口：

```bash
fund --help
fund stock 600519.SH --days 365 --adjust forward
fund quant 510300 --start 2020-01-01 --end 2026-01-01 --strategy ma_cross
fund auto-optimize 510300 --start 2018-01-01 --end 2026-01-01 --strategy ma_cross
fund news 510300 --scope keyword --limit 10
fund storage-info
fund backup
fund export-data --output data/export/portfolio.json
```

## A 股行情接口

在同花顺金融数据服务后台创建 API Key，然后通过“全局系统设置 > A股行情接口”保存到本机。也可以设置环境变量：

```bash
export HITHINK_FINANCE_API_KEY="your-api-key"
```

行情数据来自同花顺 Financial-API，当前接入最新行情快照和前复权/不复权/后复权历史日 K。基金持仓贡献基于基金公开披露的季度持仓，仅表示已披露 A 股对当日涨跌的估算贡献，不代表实时完整仓位或最终基金净值。

## 第三方模型接口

可以在“全局系统设置”页面中配置并测试连接。点击保存后，配置写入本机私有数据库，不会写入仓库。

也可以复制 [.env.example](.env.example) 中的变量到本机环境。Codex 接口使用 OpenAI Responses 协议；CC 接口使用 Claude Code 底层对应的 Anthropic Messages 协议。第三方网关必须兼容所选协议，OpenAI 兼容地址通常需要包含 `/v1`。

第一次运行时环境变量作为默认值；在 UI 中显式保存后，本地配置优先：

| 协议 | API Key | Base URL | Model |
| --- | --- | --- | --- |
| Codex / Responses | `CODEX_API_KEY` | `CODEX_BASE_URL` | `CODEX_MODEL` |
| CC / Messages | `CC_API_KEY` | `CC_BASE_URL` | `CC_MODEL` |
| OpenAI Chat | `OPENAI_API_KEY` | `OPENAI_BASE_URL` | `OPENAI_MODEL` |

## 本地数据与备份

- 默认数据库：`data/fundmaster.db`，包含交易流水、接口配置和存储元数据。
- 旧版 `data/portfolio.json` 会在首次启动时自动迁移，迁移前复制到 `data/backups/`，原文件不删除。
- 应用启动时默认每 24 小时创建一次完整 SQLite 备份，也可以在“全局系统设置 > 本地数据与备份”或 `fund backup` 手动执行。
- “导出持仓 JSON”和 `fund export-data` 只导出交易与持仓，不包含 API Key。
- 数据库及备份在 macOS/Linux 上使用 `0600` 文件权限，但内容未额外加密；完整备份应按密钥文件保管。

路径可通过环境变量覆盖：

```bash
export FUNDMASTER_DATABASE_PATH="$HOME/.fundmaster/fundmaster.db"
export FUNDMASTER_BACKUP_PATH="$HOME/.fundmaster/backups"
export FUNDMASTER_LEGACY_PORTFOLIO_PATH="data/portfolio.json"
export FUNDMASTER_AUTO_BACKUP_HOURS=24
```

恢复时先停止应用，再用备份数据库替换 `FUNDMASTER_DATABASE_PATH` 指向的文件；建议替换前保留当前数据库副本。

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

测试覆盖本地持久化与迁移、量化策略、交易成本、新闻缓存降级以及第三方模型协议适配。
