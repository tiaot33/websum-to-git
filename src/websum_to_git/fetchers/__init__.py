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

from ..url_utils import strip_tracking_params
from .camoufox_helper import get_camoufox_browser_version
from .defuddle import fetch_defuddle
from .github import fetch_github
from .headless import fetch_headless
from .screenshot import capture_screenshot

# 重新导出以保持向后兼容
from .structs import FetchError, PageContent

if TYPE_CHECKING:
    from websum_to_git.config import AppConfig

logger = logging.getLogger(__name__)

# 内容长度阈值
# MIN_CONTENT_FOR_RETRY: 低于此阈值会尝试使用 Defuddle 重新抓取
# MIN_CONTENT_FOR_SUMMARY: 低于此阈值会跳过 LLM 总结
MIN_CONTENT_FOR_RETRY = 500
MIN_CONTENT_FOR_SUMMARY = 500


# 显式路由表: (匹配函数, 处理函数)
# 顺序很重要：先匹配到的先执行。
ROUTERS: list[tuple[Callable[[str], bool], Callable[[str, AppConfig], PageContent]]] = [
    # 1. 专用 Fetchers (高优先级)
    (lambda u: "github.com" in u or "gist.github.com" in u, fetch_github),
    # Twitter 现在由 headless fetcher 的策略处理
    # 2. 兜底 Fetchers (如果在特定配置下需要优先使用某些通用 fetcher，可调整顺序)
    # 目前默认逻辑是：如果没有命中专用 fetcher，直接进入 fetch_page 的兜底逻辑。
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
    normalized_url = strip_tracking_params(url)
    if normalized_url != url:
        logger.info("已移除 URL 中的追踪参数: %s -> %s", url, normalized_url)

    # 1. 尝试匹配专用路由
    for matcher, handler in ROUTERS:
        if matcher(normalized_url):
            try:
                logger.debug("URL '%s' 匹配到专用 Fetcher: %s", normalized_url, handler.__name__)
                return _normalize_page_urls(handler(normalized_url, config))
            except Exception as exc:
                logger.warning("专用 Fetcher %s 失败: %s，尝试兜底...", handler.__name__, exc)
                # 专用 Fetcher 失败后，继续执行，尝试兜底逻辑
                break

    # 2. 使用默认 HeadlessFetcher 兜底抓取
    logger.info("使用默认 HeadlessFetcher 兜底抓取: %s", normalized_url)
    result = _normalize_page_urls(fetch_headless(normalized_url, config))

    # 3. 检查内容长度，如果过短且未显式关闭，则尝试 Defuddle 补充抓取
    if len(result.markdown.strip()) < MIN_CONTENT_FOR_RETRY and config.defuddle.enabled:
        logger.warning(
            "Headless 抓取内容过短 (%d 字符 < %d)，尝试使用 Defuddle 重新抓取",
            len(result.markdown.strip()),
            MIN_CONTENT_FOR_RETRY,
        )
        try:
            defuddle_result = _normalize_page_urls(fetch_defuddle(normalized_url, config))
            # 只有当 Defuddle 结果达到最小长度阈值时才使用
            if len(defuddle_result.markdown.strip()) >= MIN_CONTENT_FOR_RETRY:
                logger.info(
                    "Defuddle 抓取成功, 内容达到阈值 (%d 字符 >= %d)",
                    len(defuddle_result.markdown.strip()),
                    MIN_CONTENT_FOR_RETRY,
                )
                return defuddle_result
            logger.info(
                "Defuddle 抓取内容仍过短 (%d 字符 < %d)，使用原结果",
                len(defuddle_result.markdown.strip()),
                MIN_CONTENT_FOR_RETRY,
            )
        except Exception as exc:
            logger.warning("Defuddle 补充抓取失败: %s，使用 Headless 结果", exc)

    return result


def _normalize_page_urls(page: PageContent) -> PageContent:
    page.url = strip_tracking_params(page.url)
    page.final_url = strip_tracking_params(page.final_url)
    return page


__all__ = [
    "FetchError",
    "MIN_CONTENT_FOR_RETRY",
    "MIN_CONTENT_FOR_SUMMARY",
    "PageContent",
    "capture_screenshot",
    "fetch_page",
    "fetch_headless",
    "get_camoufox_browser_version",
]
