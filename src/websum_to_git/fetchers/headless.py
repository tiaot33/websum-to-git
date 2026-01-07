"""Headless 浏览器通用 Fetcher。

使用 Camoufox (基于 Firefox 的反指纹浏览器) 抓取需要 JavaScript 渲染的网页。
作为默认的后备 Fetcher，处理所有不被其他专用 Fetcher 匹配的 URL。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .camoufox_helper import fetch_with_camoufox, remove_overlays
from .headless_strategies.registry import get_route
from .html_utils import extract_article
from .structs import PageContent, get_common_config

if TYPE_CHECKING:
    from websum_to_git.config import AppConfig

logger = logging.getLogger(__name__)


def fetch_headless(url: str, config: AppConfig) -> PageContent:
    """Headless 浏览器抓取器，使用 Camoufox 和策略注册表。"""

    # 1. 查找路由策略
    route = get_route(url)

    # 2. 确定配置 (默认 vs 策略)
    base_timeout, _ = get_common_config(config)
    timeout = base_timeout
    scroll = True
    wait_selector = None
    post_process = remove_overlays  # 默认通用处理
    extract = None

    if route:
        logger.info("Headless Strategy 命中: %s pattern: %s", url, route.matcher)
        cfg = route.config
        if cfg.timeout:
            timeout = cfg.timeout
        if cfg.wait_selector:
            wait_selector = cfg.wait_selector
        scroll = cfg.scroll

        # 如果策略定义了处理函数，则覆盖默认的 post_process
        if route.process_page:
            post_process = route.process_page

        extract = route.extract

    logger.info("使用 HeadlessFetcher 抓取: %s (timeout=%d)", url, timeout)

    # 3. 执行抓取
    html, final_url, data = fetch_with_camoufox(
        url,
        timeout=timeout,
        wait_selector=wait_selector,
        scroll=scroll,
        post_process=post_process,
        extract=extract,
    )

    # 4. 构建返回结果
    if route and route.build_content:
        logger.debug("使用策略自定义构建内容")
        return route.build_content(url, final_url, html, data)

    # 默认构建流程 (Readability)
    article_data = extract_article(html, final_url)

    return PageContent(
        url=url,
        final_url=final_url,
        title=article_data.title,
        text=article_data.text,
        markdown=article_data.markdown,
        raw_html=html,
        article_html=article_data.article_html,
    )
