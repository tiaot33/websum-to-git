"""基于 requests 的轻量抓取器。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import requests

if TYPE_CHECKING:  # pragma: no cover - 类型辅助
    from requests import Response

    from websum_to_git.config import AppConfig

from .html_headers import DEFAULT_HEADERS
from .html_utils import extract_article
from .structs import FetchError, PageContent, get_common_config

logger = logging.getLogger(__name__)


def fetch_requests(url: str, config: AppConfig) -> PageContent:
    """使用 requests 获取 HTML 并用 Readability 解析正文。"""
    timeout, verify_ssl = get_common_config(config)
    logger.info("使用 RequestsFetcher 抓取: %s (timeout=%d, verify_ssl=%s)", url, timeout, verify_ssl)

    try:
        resp: Response = requests.get(
            url,
            timeout=timeout,
            verify=verify_ssl,
            headers=DEFAULT_HEADERS,
        )
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - 捕获 requests 的多种异常
        raise FetchError(f"requests 抓取失败: {exc}") from exc

    html = resp.text
    final_url = resp.url
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
