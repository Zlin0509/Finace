# FundMaster Pro

本地优先的基金持仓与量化研究工作台。当前发布版本为 `0.3.1`；`0.3.0` 起默认运行时为 Go，前端、API 与静态资源打包进一个 macOS ARM64 二进制，不需要 Python 或 Streamlit。

![Go 欢迎首页](docs/images/07-go-welcome.png)

## 当前能力

- 交易流水记账，持仓与成本从 SQLite 流水实时重建
- 旧 `data/portfolio.json` 自动迁移、每日备份和无密钥 JSON 导出
- 东方财富基金历史净值读取与 6 小时进程内缓存
- 买入持有、双均线和动量策略回测
- 手续费、滑点、信号延迟、最终平仓、基准权益和回撤
- Walk-Forward 参数搜索、串联样本外权益、参数稳定性和过拟合评级
- 第三方模型网关配置的本地保存与 API Key 脱敏读取
- 桌面侧边栏、移动底栏和二次元欢迎首页

完整界面说明见 [产品解析与操作指南](docs/PRODUCT_GUIDE.md)，发布门禁结果见 [0.3.1 全量测试报告](docs/RELEASE_VALIDATION_0.3.1.md)。

## 快速启动

环境要求：macOS ARM64、Go `1.23+`、Xcode Command Line Tools。SQLite 驱动使用 CGO。

```bash
mkdir -p dist
GOCACHE=/tmp/fundmaster-go-cache CGO_ENABLED=1 go build \
  -trimpath -ldflags="-s -w" \
  -o dist/fundmaster-go-darwin-arm64 ./cmd/fundmaster

./dist/fundmaster-go-darwin-arm64 serve
```

默认地址：[http://127.0.0.1:8503/](http://127.0.0.1:8503/)。本仓库当前验收服务使用 `8504`，可通过参数覆盖：

```bash
./dist/fundmaster-go-darwin-arm64 serve -addr 127.0.0.1:8504
```

其他命令：

```bash
./dist/fundmaster-go-darwin-arm64 version
./dist/fundmaster-go-darwin-arm64 backup
./dist/fundmaster-go-darwin-arm64 backup -db data/fundmaster.db -backups data/backups
```

## 架构

```text
Browser UI (embedded HTML/CSS/JS)
        |
Go HTTP server and JSON API
        |
Portfolio service  |  Quant engine  |  Market client
        |                  |                  |
SQLite ledger      Backtest/Walk-Forward   EastMoney NAV
```

主要目录：

| 路径 | 职责 |
| --- | --- |
| `cmd/fundmaster` | `serve`、`backup`、`version` 命令 |
| `internal/server` | HTTP API、中间件和嵌入式前端 |
| `internal/storage` | SQLite、WAL、权限、迁移和备份 |
| `internal/portfolio` | 从交易流水重建持仓 |
| `internal/market` | 基金净值下载、解析和缓存 |
| `internal/quant` | 回测、指标和 Walk-Forward |

## 数据保存

- 默认数据库：`data/fundmaster.db`
- 默认备份目录：`data/backups/`
- 默认旧数据：`data/portfolio.json`
- 数据库、WAL 与备份在 POSIX 系统上限制为 `0600`
- 完整数据库包含本地接口凭据且未额外加密
- `/api/storage/export` 只导出交易与持仓，不包含 API Key

路径可通过参数或环境变量覆盖：

```bash
export FUNDMASTER_DATABASE_PATH="$HOME/.fundmaster/fundmaster.db"
export FUNDMASTER_BACKUP_PATH="$HOME/.fundmaster/backups"
export FUNDMASTER_LEGACY_PORTFOLIO_PATH="data/portfolio.json"
export FUNDMASTER_ADDR="127.0.0.1:8504"
```

不要提交 `data/` 下的数据库、备份或本机 API Key。本仓库的 `.gitignore` 已排除这些路径。

## 量化口径

- 双均线和动量信号在收盘后生成，下一交易日生效，避免前视偏差。
- 当前执行模型为全仓基金或空仓，不做空。
- 每次仓位变化计入手续费和滑点，结束时强制平仓。
- Walk-Forward 每折只使用滚动训练窗口选参，随后在未见数据上验证。
- 主结果将所有样本外日收益按时间串联，统一计算收益、基准、回撤、波动和夏普。
- 可靠性评级综合参数稳定性、正收益窗口、跑赢基准比例和训练验证差距。
- 历史结果不构成投资建议。

## 性能

Apple M3 Pro、Go `1.26.2`、约 10 年 2,440 个价格点：

| 路径 | 基准 |
| --- | ---: |
| 完整回测与权益曲线 | `55.5 us/op` |
| 仅计算指标 | `32.9 us/op` |
| 快速 Walk-Forward | `0.349 ms/op` |

`0.3.1` 真实 510300 验收中，净值首请求约 `258 ms`、缓存请求约 `1.18 ms`；缓存后的完整回测约 `1 ms`，标准 Walk-Forward 约 `185 ms`。网络时延与数据源状态会影响端到端结果。

## 测试

```bash
GOCACHE=/tmp/fundmaster-go-cache go test ./...
GOCACHE=/tmp/fundmaster-go-cache go vet ./...
node --check internal/server/static/app.js
```

运行量化基准：

```bash
GOCACHE=/tmp/fundmaster-go-cache go test ./internal/quant \
  -run '^$' -bench 'Benchmark(BacktestTenYears|MetricsTenYears|WalkForwardFast)$' \
  -benchmem -benchtime=1s
```

## HTTP API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康与版本 |
| `GET` | `/api/portfolio` | 持仓与交易快照 |
| `POST` | `/api/transactions` | 新增交易 |
| `GET` | `/api/funds/{code}/nav` | 基金历史净值 |
| `POST` | `/api/quant/backtest` | 策略回测 |
| `POST` | `/api/quant/optimize` | Walk-Forward |
| `POST` | `/api/storage/backup` | 创建数据库备份 |
| `GET` | `/api/storage/export` | 导出无密钥持仓 JSON |
| `GET/PUT` | `/api/settings/{namespace}` | 本地配置 |

## Python 旧版

`src/`、`tests/` 与 `pyproject.toml` 保留为 `0.2.x` 兼容实现，包含尚未迁移到 Go 的 A 股、新闻与模型分析功能。它不再是默认启动路径；新功能和性能优化优先进入 Go 版本。
