from src import __version__
from src.utils.config import load_config


def test_packaged_config_is_available_outside_repository(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FUNDMASTER_CONFIG_PATH", raising=False)

    loaded = load_config()

    assert loaded["storage"]["databasePath"] == "data/fundmaster.db"
    assert loaded["analysis"]["tradingDaysPerYear"] == 244


def test_release_version_is_0_2_0():
    assert __version__ == "0.2.0"
