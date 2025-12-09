"""通过公开镜像获取页面内容，作为兜底方案。"""

from __future__ import annotations

import logging
from urllib.parse import quote

import requests

from .base import BaseFetcher, FetchError, PageContent
from .factory import register_fetcher
from .html_headers import DEFAULT_HEADERS
from .html_utils import extract_article

logger = logging.getLogger(__name__)


@register_fetcher(priority=1)
class MirrorFetcher(BaseFetcher):
    """调用 `r.jina.ai` 镜像兜底抓取。"""

    def fetch(self, url: str) -> PageContent:
        logger.info("使用 MirrorFetcher 抓取: %s", url)

        encoded_url = quote(url, safe=":/?&=#%")
        mirror_url = f"https://r.jina.ai/{encoded_url}"

        try:
            resp = requests.get(
                mirror_url,
                timeout=self.timeout,
                verify=self.verify_ssl,
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
