"""Fetcher 基类和通用数据结构。"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import urlparse

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


class BaseFetcher(ABC):
    """Fetcher 抽象基类。

    所有具体的 Fetcher 实现都应继承此类并实现 fetch 方法。
    """

    # 子类可以通过覆盖此属性声明自己支持的域名列表；
    # 留空表示作为兜底策略，由调用方控制优先级。
    SUPPORTED_DOMAINS: tuple[str, ...] = ()

    def __init__(self, timeout: int = 30, verify_ssl: bool = True) -> None:
        """初始化 Fetcher。

        Args:
            timeout: 请求超时时间（秒）
            verify_ssl: 是否验证 SSL 证书
        """
        self.timeout = timeout
        self.verify_ssl = verify_ssl

    @classmethod
    def can_handle(cls, url: str) -> bool:
        """判断当前 Fetcher 是否适合处理给定 URL。

        默认实现基于域名匹配，子类可以根据需要重写。
        """
        if not cls.SUPPORTED_DOMAINS:
            # 未声明域名时由调用方控制是否作为兜底使用
            return True

        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]

        return domain in cls.SUPPORTED_DOMAINS

    @abstractmethod
    def fetch(self, url: str) -> PageContent:
        """抓取并解析网页内容。

        Args:
            url: 要抓取的 URL

        Returns:
            PageContent 对象，包含提取的内容

        Raises:
            FetchError: 抓取失败时
        """
        ...
