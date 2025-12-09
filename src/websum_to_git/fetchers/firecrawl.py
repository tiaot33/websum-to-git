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
            formats=["markdown", "html"],
            max_age=172800000,  # 2 days in milliseconds
        )

        # Firecrawl 的返回字段在类型上可能为 Optional[str]，这里统一做兜底处理
        markdown = scrape_result.markdown or ""
        html = scrape_result.html or ""
        raw_html = getattr(scrape_result, "raw_html", "") or html or markdown

        # Firecrawl 可能会返回重定向后的 URL, 如果没有则回退为原始 URL
        metadata = getattr(scrape_result, "metadata", None)
        final_url = url
        title = "No Title"
        if metadata is not None:
            meta_title = getattr(metadata, "title", None)
            if meta_title:
                title = str(meta_title)
            meta_url = getattr(metadata, "url", None) or getattr(metadata, "canonical_url", None)
            if meta_url:
                final_url = str(meta_url)

        return PageContent(
            url=url,
            final_url=final_url,
            title=title,
            text=markdown or html or raw_html,
            markdown=markdown,
            raw_html=raw_html,
            article_html=html or raw_html,
        )

    except Exception as e:
        logger.warning("Firecrawl 抓取异常: %s", e)
        raise FetchError(f"Firecrawl Error: {e}") from e
