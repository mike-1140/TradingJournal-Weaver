"""Prefix-Aufloesung ueber users.toml: fehlende Benutzer muessen zum Abbruch fuehren.

Hintergrund: Frueher lieferte config.py fuer einen Benutzer ohne users.toml-Eintrag
stillschweigend ein leeres Prefix — Import/Processing haetten dann unbemerkt in Tabellen
ohne Prefix (trades_raw statt anna_trades_raw) geschrieben. Seit users.toml lokal und nicht
mehr versioniert ist, fehlt die Datei z.B. nach einem git pull auf einem Zweitrechner.
"""
import pytest

from src import config


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    """Leeres Projektverzeichnis fuer users/accounts/pipeline.toml, Caches geleert."""
    monkeypatch.setattr(config, "ROOT_DIR", tmp_path)
    config.load_users.cache_clear()
    config.load_account_map.cache_clear()
    yield tmp_path
    config.load_users.cache_clear()
    config.load_account_map.cache_clear()


def _write(path, text):
    path.write_text(text, encoding="utf-8")


USERS = '[anna]\nprefix = "anna_"\n\n[tom]\nprefix = "tom_"\n'
ACCOUNTS = ('[1234]\nuser = "anna"\nenvironment = "money"\n\n'
            '[9012]\nuser = "tom"\nenvironment = "paper"\n')


class TestGetAccountConfig:
    def test_bekannter_benutzer_bekommt_prefix_aus_users_toml(self, config_dir):
        _write(config_dir / "users.toml", USERS)
        _write(config_dir / "accounts.toml", ACCOUNTS)

        cfg = config.get_account_config("U*****9012")

        assert cfg == {"user": "tom", "table_prefix": "tom_", "environment": "paper"}

    def test_unbekanntes_konto_bleibt_none(self, config_dir):
        _write(config_dir / "users.toml", USERS)
        _write(config_dir / "accounts.toml", ACCOUNTS)

        assert config.get_account_config("U*****5555") is None

    def test_benutzer_fehlt_in_users_toml_bricht_ab(self, config_dir):
        _write(config_dir / "users.toml", '[anna]\nprefix = "anna_"\n')
        _write(config_dir / "accounts.toml", ACCOUNTS)

        with pytest.raises(ValueError, match="'tom'.*accounts.toml.*users.toml"):
            config.get_account_config("U*****9012")

    def test_users_toml_fehlt_ganz_bricht_ab(self, config_dir):
        _write(config_dir / "accounts.toml", ACCOUNTS)

        with pytest.raises(ValueError, match="'anna'"):
            config.get_account_config("U*****1234")


class TestLoadActiveTargets:
    def test_prefix_kommt_aus_users_toml(self, config_dir):
        _write(config_dir / "users.toml", USERS)
        _write(config_dir / "pipeline.toml",
               '[users.anna]\nenvironments = ["money", "paper"]\n\n'
               '[users.tom]\nenvironments = ["paper"]\n')

        targets = config.load_active_targets()

        assert [(t["user"], t["environment"], t["prefix"]) for t in targets] == [
            ("anna", "money", "anna_"), ("anna", "paper", "anna_"), ("tom", "paper", "tom_"),
        ]

    def test_benutzer_fehlt_in_users_toml_bricht_ab(self, config_dir):
        _write(config_dir / "users.toml", '[anna]\nprefix = "anna_"\n')
        _write(config_dir / "pipeline.toml", '[users.tom]\nenvironments = ["paper"]\n')

        with pytest.raises(ValueError, match="'tom'.*pipeline.toml"):
            config.load_active_targets()

    def test_expliziter_prefix_in_pipeline_toml_braucht_keinen_eintrag(self, config_dir):
        _write(config_dir / "pipeline.toml",
               '[users.tom]\nprefix = "tom_"\nenvironments = ["paper"]\n')

        targets = config.load_active_targets()

        assert targets == [{"environment": "paper", "prefix": "tom_", "user": "tom"}]

    def test_test_eintrag_ohne_registrierten_benutzer_bricht_ab(self, config_dir):
        _write(config_dir / "users.toml", USERS)
        _write(config_dir / "pipeline.toml", '[[test]]\nuser = "unbekannt"\n')

        with pytest.raises(ValueError, match="'unbekannt'"):
            config.load_active_targets()
