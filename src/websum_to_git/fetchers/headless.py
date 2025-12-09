"""Headless 浏览器通用 Fetcher。

使用 Camoufox (基于 Firefox 的反指纹浏览器) 抓取需要 JavaScript 渲染的网页。
作为默认的后备 Fetcher，处理所有不被其他专用 Fetcher 匹配的 URL。
"""

from __future__ import annotations

import logging

from .base import BaseFetcher, PageContent
from .camoufox_helper import fetch_with_camoufox
from .factory import register_fetcher
from .html_utils import extract_article

logger = logging.getLogger(__name__)


@register_fetcher(priority=5)
class HeadlessFetcher(BaseFetcher):
    """Headless 浏览器抓取器，使用 Camoufox。"""

    def fetch(self, url: str) -> PageContent:
        logger.info("使用 HeadlessFetcher 抓取: %s (timeout=%d)", url, self.timeout)

        html, final_url, _ = fetch_with_camoufox(url, timeout=self.timeout, scroll=True)

        title, article_html, markdown, text = extract_article(html, final_url)

        return PageContent(
            url=url,
            final_url=final_url,
            title=title,
            text=text,
            markdown=markdown,
            raw_html=html,
            article_html=article_html,
        )
