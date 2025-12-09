"""Firecrawl Fetcher 实现。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from firecrawl import Firecrawl

from websum_to_git.fetchers.structs import FetchError, PageContent

if TYPE_CHECKING:
    from websum_to_git.config import AppConfig

logger = logging.getLogger(__name__)


def fetch_firecrawl(url: str, config: AppConfig) -> PageContent:
    """使用 Firecrawl API 抓取网页并提取 Markdown。

    Args:
        url: 目标 URL。
        config: 应用配置。

    Returns:
        PageContent, 包含 Markdown 内容。

    Raises:
        FetchError: 当抓取失败或 API 返回错误时。
    """
    if not config.firecrawl:
        raise FetchError("未配置 Firecrawl API Key")

    try:
        firecrawl = Firecrawl(api_key=config.firecrawl.api_key)

        logger.info("正在使用 Firecrawl 抓取: %s", url)

        # Use cached data if it's less than 1 hour old (3600000 ms)
        scrape_result = firecrawl.scrape(
            url,
            formats=['markdown','html'],
            maxAge=172800000  # 2 days in milliseconds
        )

        markdown = scrape_result['markdown']
        html = scrape_result['html']
        metadata = scrape_result.get('metadata', {})

        return PageContent(
            url=url,
            title=str(metadata.get('title', 'No Title')),
            markdown=markdown,
            html=html,
            text=markdown
        )

    except Exception as e:
        logger.warning("Firecrawl 抓取异常: %s", e)
        raise FetchError(f"Firecrawl Error: {e}") from e
