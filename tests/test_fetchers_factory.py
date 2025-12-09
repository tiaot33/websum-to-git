from __future__ import annotations

import pytest

from websum_to_git.config import HttpConfig
from websum_to_git.fetchers.base import BaseFetcher, FetchError, PageContent
from websum_to_git.fetchers.factory import _default_fetchers, fetch
from websum_to_git.fetchers.github import GitHubFetcher
from websum_to_git.fetchers.headless import HeadlessFetcher
from websum_to_git.fetchers.mirror import MirrorFetcher
from websum_to_git.fetchers.requests_fetcher import RequestsFetcher
from websum_to_git.fetchers.twitter import TwitterFetcher


def test_default_fetchers_order(sample_app_config) -> None:
    """默认 Fetcher 顺序应固定。"""
    order_requests = _default_fetchers(sample_app_config)

    assert order_requests[:2] == (TwitterFetcher, GitHubFetcher)
    assert order_requests[2:] == (RequestsFetcher, HeadlessFetcher, MirrorFetcher)


def test_fetch_fallback_to_next_fetcher(sample_app_config) -> None:
    """前一个 Fetcher 失败时应尝试下一位。"""

    called: list[str] = []

    class FailFetcher(BaseFetcher):
        def fetch(self, url: str) -> PageContent:  # type: ignore[override]
            called.append("fail")
            raise FetchError("boom")

    class OkFetcher(BaseFetcher):
        def fetch(self, url: str) -> PageContent:  # type: ignore[override]
            called.append("ok")
            return PageContent(
                url=url,
                final_url=url,
                title="ok",
                text="",
                markdown="",
                raw_html="",
                article_html="",
            )

    result = fetch("https://example.com", sample_app_config, fetchers=(FailFetcher, OkFetcher))

    assert result.title == "ok"
    assert called == ["fail", "ok"]


def test_fetch_all_fail_raise(sample_app_config) -> None:
    """所有 Fetcher 失败时抛出 FetchError。"""

    class FailFetcher(BaseFetcher):
        def fetch(self, url: str) -> PageContent:  # type: ignore[override]
            raise FetchError("boom")

    sample_app_config.http = HttpConfig(verify_ssl=True)

    with pytest.raises(FetchError):
        fetch("https://example.com", sample_app_config, fetchers=(FailFetcher,))
