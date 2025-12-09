"""Fetchers 包 - 网页抓取与 Markdown 提取。

本包提供统一的网页抓取接口，支持不同类型网站的定制化抓取策略。
所有的 Fetcher 实现都通过 `@register_fetcher` 自动注册。

推荐用法（简单入口）::

    from websum_to_git.config import load_config
    from websum_to_git.fetchers import fetch_page

    config = load_config("./config.yaml")
    page = fetch_page("https://example.com", config)

如需自定义或复用底层 Fetcher 实例，可直接使用 :class:`FetcherFactory`。
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from .base import BaseFetcher, FetchError, PageContent
from .factory import FetcherFactory, fetch as _fetch

# 导入所有 Fetcher 模块以触发注册
from . import github, headless, mirror, requests_fetcher, twitter


if TYPE_CHECKING:
    from websum_to_git.config import AppConfig


def fetch_page(url: str, config: AppConfig) -> PageContent:
    """根据配置抓取并解析单个 URL。

    推荐使用的高层入口，内部会根据 URL 自动选择最合适的 Fetcher。
    """
    return _fetch(url, config)


__all__ = [
    "BaseFetcher",
    "FetchError",
    "FetcherFactory",
    "PageContent",
    "fetch_page",
]
