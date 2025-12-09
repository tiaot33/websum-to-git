"""Fetchers 包 - 网页抓取与 Markdown 提取。

本包提供统一的网页抓取接口，采用显式路由模式将 URL 分发给具体的 Fetcher 实现。

推荐用法::

    from websum_to_git.config import load_config
    from websum_to_git.fetchers import fetch_page

    config = load_config("./config.yaml")
    page = fetch_page("https://example.com", config)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from .github import fetch_github
from .headless import fetch_headless

# 重新导出以保持向后兼容
from .structs import FetchError, PageContent
from .twitter import fetch_twitter

if TYPE_CHECKING:
    from websum_to_git.config import AppConfig

logger = logging.getLogger(__name__)


# 显式路由表: (匹配函数, 处理函数)
# 顺序很重要：先匹配到的先执行。
ROUTERS: list[tuple[Callable[[str], bool], Callable[[str, AppConfig], PageContent]]] = [
    # 1. 专用 Fetchers (高优先级)
    (lambda u: "github.com" in u or "gist.github.com" in u, fetch_github),
    (lambda u: "twitter.com" in u or "x.com" in u, fetch_twitter),
    # 2. 兜底 Fetchers (如果在特定配置下需要优先使用某些通用 fetcher，可调整顺序)
    # 目前默认逻辑是：如果没有命中专用 fetcher，直接进入 fetch_page 的兜底逻辑。
    # 如果未来有 requests_fetcher 的特定匹配需求，可以在这里添加。
]


def fetch_page(url: str, config: AppConfig) -> PageContent:
    """根据配置抓取并解析单个 URL。

    Args:
        url: 目标 URL
        config: 应用全局配置

    Returns:
        PageContent, 包含解析后的 Markdown 和元数据。

    Raises:
        FetchError: 当抓取失败时。
    """
    # 1. 尝试匹配专用路由
    for matcher, handler in ROUTERS:
        if matcher(url):
            try:
                logger.debug("URL '%s' 匹配到专用 Fetcher: %s", url, handler.__name__)
                return handler(url, config)
            except Exception as exc:
                logger.warning("专用 Fetcher %s 失败: %s，尝试兜底...", handler.__name__, exc)
                # 专用 Fetcher 失败后，继续执行，尝试兜底逻辑
                break

    # 2. 兜底逻辑：优先尝试 Headless，其次 Requests（或者根据需求调整）
    # 目前保持简单，统一使用 HeadlessFetcher 作为强力兜底
    # 也可以引入一个配置项来决定兜底策略
    logger.info("使用默认 HeadlessFetcher 兜底抓取: %s", url)
    return fetch_headless(url, config)


__all__ = [
    "FetchError",
    "PageContent",
    "fetch_page",
]
