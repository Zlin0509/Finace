# Changelog

## 0.2.0 - 2026-07-16

### Added

- SQLite 本地数据库，持久化交易流水、模型配置和数据源配置。
- 旧 `data/portfolio.json` 自动迁移及迁移前备份。
- 每日自动备份、设置页手动备份和无密钥持仓 JSON 导出。
- `fund storage-info`、`fund backup`、`fund export-data` 和 `fund ui` 命令。
- 可随 wheel 安装的默认配置资源。

### Changed

- 持仓从交易流水实时重建，避免派生汇总与原始交易不一致。
- 卖出交易校验可用份额。
- 项目版本提升到 `0.2.0`。

### Security

- 本地数据库、WAL 文件与备份在 POSIX 系统上限制为 `0600`。
- 持仓导出不包含本地保存的 API Key。
- SQLite 内容未额外加密，完整数据库备份仍需按密钥文件保管。
