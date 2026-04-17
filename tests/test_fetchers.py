import websum_to_git.fetchers as fetchers
from websum_to_git.config import AppConfig, DefuddleConfig, GitHubConfig, HttpConfig, LLMConfig, TelegramConfig
from websum_to_git.fetchers import FetchError, PageContent


def _build_config(*, defuddle_enabled: bool) -> AppConfig:
    return AppConfig(
        telegram=TelegramConfig(bot_token="token"),
        llm=LLMConfig(provider="openai", api_key="key", model="model"),
        github=GitHubConfig(repo="owner/repo", pat="pat"),
        http=HttpConfig(),
        defuddle=DefuddleConfig(enabled=defuddle_enabled),
    )


def _build_page(url: str, final_url: str, markdown: str) -> PageContent:
    return PageContent(
        url=url,
        final_url=final_url,
        title="Title",
        text=markdown,
        markdown=markdown,
        raw_html="",
        article_html="",
    )


def test_fetch_page_skips_defuddle_when_disabled(monkeypatch) -> None:
    config = _build_config(defuddle_enabled=False)
    called = False

    def fake_headless(url: str, _: AppConfig) -> PageContent:
        return _build_page(url=url, final_url="https://example.com/article?id=42&utm_source=telegram", markdown="short")

    def fake_defuddle(url: str, _: AppConfig) -> PageContent:
        nonlocal called
        called = True
        return _build_page(url=url, final_url=url, markdown="x" * 600)

    monkeypatch.setattr(fetchers, "fetch_headless", fake_headless)
    monkeypatch.setattr(fetchers, "fetch_defuddle", fake_defuddle)

    result = fetchers.fetch_page("https://example.com/article?utm_source=telegram&id=42", config)

    assert called is False
    assert result.url == "https://example.com/article?id=42"
    assert result.final_url == "https://example.com/article?id=42"


def test_fetch_page_uses_defuddle_when_enabled(monkeypatch) -> None:
    config = _build_config(defuddle_enabled=True)
    calls: list[str] = []

    def fake_headless(url: str, _: AppConfig) -> PageContent:
        return _build_page(url=url, final_url=url, markdown="short")

    def fake_defuddle(url: str, _: AppConfig) -> PageContent:
        calls.append(url)
        return _build_page(
            url=url,
            final_url="https://example.com/article?id=42&fbclid=abc123",
            markdown="x" * 600,
        )

    monkeypatch.setattr(fetchers, "fetch_headless", fake_headless)
    monkeypatch.setattr(fetchers, "fetch_defuddle", fake_defuddle)

    result = fetchers.fetch_page("https://example.com/article?utm_source=telegram&id=42", config)

    assert calls == ["https://example.com/article?id=42"]
    assert result.final_url == "https://example.com/article?id=42"


def test_fetch_page_uses_defuddle_when_headless_fails(monkeypatch) -> None:
    config = _build_config(defuddle_enabled=True)
    calls: list[str] = []

    def fake_headless(_: str, __: AppConfig) -> PageContent:
        raise FetchError("Headless 抓取失败: 缺少 Camoufox bundle")

    def fake_defuddle(url: str, _: AppConfig) -> PageContent:
        calls.append(url)
        return _build_page(url=url, final_url=url, markdown="x" * 120)

    monkeypatch.setattr(fetchers, "fetch_headless", fake_headless)
    monkeypatch.setattr(fetchers, "fetch_defuddle", fake_defuddle)

    result = fetchers.fetch_page("https://example.com/article?utm_source=telegram&id=42", config)

    assert calls == ["https://example.com/article?id=42"]
    assert result.url == "https://example.com/article?id=42"
    assert result.final_url == "https://example.com/article?id=42"


def test_fetch_page_reraises_headless_error_when_fallback_unavailable(monkeypatch) -> None:
    config = _build_config(defuddle_enabled=False)

    def fake_headless(_: str, __: AppConfig) -> PageContent:
        raise FetchError("Headless 抓取失败: 缺少 Camoufox bundle")

    monkeypatch.setattr(fetchers, "fetch_headless", fake_headless)

    try:
        fetchers.fetch_page("https://example.com/article?id=42", config)
    except FetchError as exc:
        assert str(exc) == "Headless 抓取失败: 缺少 Camoufox bundle"
    else:
        raise AssertionError("预期抛出 FetchError")
