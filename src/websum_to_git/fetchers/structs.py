"""通用数据结构定义。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from websum_to_git.config import AppConfig

logger = logging.getLogger(__name__)


class FetchError(RuntimeError):
    """抓取过程中出现的异常。"""


@dataclass
class PageContent:
    """网页内容数据结构。

    Attributes:
        url: 原始请求 URL
        final_url: 最终 URL（可能经过重定向）
        title: 网页标题
        text: 纯文本内容（用于 LLM 摘要）
        markdown: Markdown 格式的正文内容
        raw_html: 原始 HTML（完整网页）
        article_html: 提取后的文章 HTML（Readability 处理后）
    """

    url: str
    final_url: str
    title: str
    text: str
    markdown: str
    raw_html: str
    article_html: str


def get_common_config(config: AppConfig) -> tuple[int, bool]:
    """提取通用 HTTP 配置。

    Args:
        config: 应用配置对象

    Returns:
        (timeout, verify_ssl)
    """
    return (30, config.http.verify_ssl)
