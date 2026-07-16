import json

from click.testing import CliRunner

from src.cli.main import cli


def _configure_storage(monkeypatch, tmp_path):
    monkeypatch.setenv("FUNDMASTER_DATABASE_PATH", str(tmp_path / "fundmaster.db"))
    monkeypatch.setenv("FUNDMASTER_BACKUP_PATH", str(tmp_path / "backups"))
    monkeypatch.setenv(
        "FUNDMASTER_LEGACY_PORTFOLIO_PATH", str(tmp_path / "missing.json")
    )


def test_cli_reports_version():
    result = CliRunner().invoke(cli, ["--version"])

    assert result.exit_code == 0
    assert "0.2.0" in result.output


def test_cli_storage_backup_and_export(monkeypatch, tmp_path):
    _configure_storage(monkeypatch, tmp_path)
    runner = CliRunner()
    trade = runner.invoke(
        cli,
        [
            "trade",
            "--date",
            "2026-01-02",
            "--code",
            "510300",
            "--action",
            "buy",
            "--amount",
            "1000",
            "--price",
            "2",
        ],
    )
    info = runner.invoke(cli, ["storage-info"])
    backup = runner.invoke(cli, ["backup"])
    export_path = tmp_path / "portfolio-export.json"
    exported = runner.invoke(cli, ["export-data", "--output", str(export_path)])

    assert trade.exit_code == 0
    assert info.exit_code == 0
    assert "1" in info.output
    assert backup.exit_code == 0
    assert len(list((tmp_path / "backups").glob("fundmaster-*.db"))) == 1
    assert exported.exit_code == 0
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload["transactions"][0]["fund_code"] == "510300"
