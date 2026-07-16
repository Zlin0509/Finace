# FundMaster Pro 0.3.1 全量测试报告

测试日期：2026-07-16

平台：macOS 26.5.1 / Apple M3 Pro / arm64

运行时：Go 1.26.2、Node.js 25.9.0、Python 3.14.3

## 结论

`0.3.1` 发布门禁全部通过，没有发现阻断发布的问题。测试覆盖源码自动化、竞态、旧版兼容层、SQLite 数据安全、真实基金行情、桌面与移动端 UI 以及发布包完整性。

本报告中的“通过”只针对下列环境、数据和测试范围。第三方行情服务未来的可用性、网络状态和未覆盖输入仍属于外部风险，历史回测结果不构成投资建议。

## 自动化门禁

| 门禁 | 命令或范围 | 结果 |
| --- | --- | --- |
| Go 全量测试 | `go test -count=1 -shuffle=on ./...` | 通过 |
| Go 竞态检测 | `go test -race -count=1 ./...` | 通过 |
| Go 静态检查 | `go vet ./...` | 通过 |
| Go 格式 | `gofmt -l cmd internal` | 无未格式化文件 |
| Go 覆盖率 | `go test -coverprofile` | 总计 60.5%；量化 81.7%；持仓 81.1% |
| Python 兼容层 | `pytest -q` | 35 passed |
| Python 覆盖率 | `coverage run --source=src -m pytest` | 总计 56% |
| 前端脚本 | `node --check internal/server/static/app.js` | 通过 |
| 敏感信息 | 排除 `data/`、`dist/` 后扫描密钥模式 | 未发现真实密钥 |

Python 测试只有 `py_mini_racer` 针对 Python 3.19 的两条弃用预警；当前 Python 3.14.3 下不影响功能。

## 数据与 API

所有写入测试均使用 `/tmp/fundmaster-v031-test/` 下的隔离数据库，没有修改真实持仓。

- 旧 `portfolio.json` 成功迁移 1 条交易。
- 主数据库和两份备份的 `PRAGMA integrity_check` 均为 `ok`。
- 数据库、迁移前 JSON 和 SQLite 备份权限均为 `0600`。
- 健康、持仓、存储统计、导出和手动备份 API 返回成功。
- 持仓导出包含交易与派生持仓，不包含 API Key。
- 设置保存后读取结果为 `api_key: ""` 与 `api_key_saved: true`。
- 非 6 位基金代码返回 `400`。
- 未知 JSON 字段返回 `400`，未知设置命名空间返回 `404`。
- 首页包含 `nosniff`、`DENY` 和 `no-referrer` 安全响应头。

## 真实行情与量化

标的：510300

区间：2020-01-01 至 2026-07-16

- 返回 1,585 个净值点，首日 2020-01-02，末日 2026-07-15。
- 没有零值或负净值。
- 首次行情请求约 258 ms，缓存请求约 1.18 ms。
- 首次与缓存响应 SHA-256 相同。
- 双均线回测：累计收益 0.51%，最大回撤 -40.01%，超额收益 -16.00%，34 次交易。
- 标准 Walk-Forward：13 个窗口、29 组参数，样本外收益 -17.21%，可靠性 26/100（D）。

Apple M3 Pro 隔离基准：

| 路径 | 结果 |
| --- | ---: |
| 完整 10 年回测 | 55,526 ns/op |
| 仅计算指标 | 32,889 ns/op |
| 快速 Walk-Forward | 348,961 ns/op |

## 浏览器验收

测试地址：`http://127.0.0.1:8504/`

- 1440×900：欢迎页、资产页、交易弹窗、量化回测、Walk-Forward、设置页通过。
- 390×844：欢迎页、五项底栏、资产指标、环图图例和交易弹窗通过。
- 320×568：最小支持宽度无横向溢出，主按钮和底栏文字仍在容器内。
- 交易弹窗只打开和关闭，没有向真实数据库提交测试记录。
- 浏览器控制台没有 warning 或 error。

## 发布产物

| 文件 | SHA-256 |
| --- | --- |
| `fundmaster-go-darwin-arm64` | `97dbb76bebcbd039c6ca785f2f300fd9ae86a9eb71c6c12443bc152ab5423082` |
| `FundMaster-Pro-0.3.1-darwin-arm64.zip` | `0a19d9d425f1a72765aab8a0889cbff7bedc930d63f1089972387ae209b2004f` |

二进制版本输出：`FundMaster Pro 0.3.1 (Go)`。
