"""Headless 浏览器通用 Fetcher。

使用 Camoufox (基于 Firefox 的反指纹浏览器) 抓取需要 JavaScript 渲染的网页。
作为默认的后备 Fetcher，处理所有不被其他专用 Fetcher 匹配的 URL。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .camoufox_helper import fetch_with_camoufox, remove_overlays
from .html_utils import extract_article
from .structs import PageContent, get_common_config

if TYPE_CHECKING:
    from websum_to_git.config import AppConfig

logger = logging.getLogger(__name__)


def fetch_headless(url: str, config: AppConfig) -> PageContent:
    """Headless 浏览器抓取器，使用 Camoufox。"""
    timeout, _ = get_common_config(config)
    logger.info("使用 HeadlessFetcher 抓取: %s (timeout=%d)", url, timeout)

    html, final_url, _ = fetch_with_camoufox(
        url, timeout=timeout, scroll=True, post_process=remove_overlays
    )

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
