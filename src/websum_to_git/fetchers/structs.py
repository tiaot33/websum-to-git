"""通用数据结构定义。"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

# Defuddle 等 fetcher 可能返回的元数据字段名（按期望的 YAML 顺序排列）。
# 统一在这里声明，方便 pipeline 组装 front matter 时复用。
EXTRA_META_KEYS: tuple[str, ...] = (
    "author",
    "site",
    "domain",
    "published",
    "language",
    "description",
    "word_count",
)

if TYPE_CHECKING:
    from websum_to_git.config import AppConfig

logger = logging.getLogger(__name__)


class FetchError(RuntimeError):
    """抓取过程中出现的异常。"""


class ArticleData(BaseModel):
    """从 HTML 提取的文章数据。"""

    title: str = ""
    article_html: str = ""
    markdown: str = ""
    text: str = ""


class PageContent(BaseModel):
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

    model_config = ConfigDict(arbitrary_types_allowed=True)

    url: str
    final_url: str
    title: str
    text: str
    markdown: str
    raw_html: str
    article_html: str
    # 由 fetcher 额外提供的元数据（如 defuddle 返回的 author/site/published 等），
    # pipeline 在生成最终 front matter 时会按需合并。
    extra_meta: dict[str, str] = Field(default_factory=dict)


class HeadlessConfig(BaseModel):
    """Headless 浏览器抓取配置。"""

    timeout: int | None = Field(default=None, description="超时时间(秒)")
    wait_selector: str | None = Field(default=None, description="等待出现的 CSS 选择器")
    scroll: bool = Field(default=True, description="是否执行滚动操作")


def get_common_config(config: AppConfig) -> tuple[int, bool]:
    """提取通用 HTTP 配置。

    Args:
        config: 应用配置对象

    Returns:
        (timeout, verify_ssl)
    """
    return (30, config.http.verify_ssl)
