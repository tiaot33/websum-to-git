"""通过公开镜像获取页面内容，作为兜底方案。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from urllib.parse import quote

import requests

from .html_headers import DEFAULT_HEADERS
from .html_utils import extract_article
from .structs import FetchError, PageContent, get_common_config

if TYPE_CHECKING:
    from websum_to_git.config import AppConfig

logger = logging.getLogger(__name__)


def fetch_mirror(url: str, config: AppConfig) -> PageContent:
    """调用 `r.jina.ai` 镜像兜底抓取。"""
    timeout, verify_ssl = get_common_config(config)
    logger.info("使用 MirrorFetcher 抓取: %s", url)

    encoded_url = quote(url, safe=":/?&=#%")
    mirror_url = f"https://r.jina.ai/{encoded_url}"

    try:
        resp = requests.get(
            mirror_url,
            timeout=timeout,
            verify=verify_ssl,
            headers=DEFAULT_HEADERS,
        )
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise FetchError(f"镜像抓取失败: {exc}") from exc

    html = resp.text
    # 镜像返回的是 Markdown 兼容 HTML，但仍用 extract_article 保持结构一致
    title, article_html, markdown, text = extract_article(html, url)

    return PageContent(
        url=url,
        final_url=url,
        title=title,
        text=text,
        markdown=markdown,
        raw_html=html,
        article_html=article_html,
    )
