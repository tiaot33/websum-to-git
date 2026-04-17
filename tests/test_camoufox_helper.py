from types import SimpleNamespace

from websum_to_git.fetchers.camoufox_helper import get_camoufox_browser_version


def test_get_camoufox_browser_version_returns_active_browser(monkeypatch) -> None:
    installed_versions = [
        SimpleNamespace(is_active=False, version=SimpleNamespace(full_string="145.0.0-beta.1")),
        SimpleNamespace(is_active=True, version=SimpleNamespace(full_string="146.0.1-alpha.50")),
    ]

    monkeypatch.setattr("camoufox.multiversion.list_installed", lambda: installed_versions)

    assert get_camoufox_browser_version() == "146.0.1-alpha.50"


def test_get_camoufox_browser_version_returns_not_installed_when_no_active(monkeypatch) -> None:
    monkeypatch.setattr("camoufox.multiversion.list_installed", lambda: [])

    assert get_camoufox_browser_version() == "未安装"
