from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from readability import Document

DEFAULT_HEADERS = {
    # 模拟常见桌面浏览器，降低被简单反爬和 UA 黑名单拦截的概率
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}


class HeadlessFetchError(RuntimeError):
    """Headless 抓取过程中出现的异常。"""


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


def fetch_html(url: str, timeout: int = 15, verify: bool = True) -> Tuple[str, str]:
    """使用 requests 获取 HTML 内容。

    Returns:
        (html, final_url) 元组
    """
    resp = requests.get(
        url,
        timeout=timeout,
        verify=verify,
        headers=DEFAULT_HEADERS,
    )
    resp.raise_for_status()
    return resp.text, resp.url


def fetch_html_headless(url: str, timeout: int = 15) -> Tuple[str, str]:
    """使用 Playwright 抓取 HTML，返回 (html, final_url)。"""

    try:
        from playwright.sync_api import (  # type: ignore import-not-found
            TimeoutError as PlaywrightTimeoutError,
        )
        from playwright.sync_api import (
            sync_playwright,
        )
    except ModuleNotFoundError as exc:  # pragma: no cover - 运行期缺依赖
        raise HeadlessFetchError(
            "Playwright 未安装，请执行 `pip install playwright` 并运行 `playwright install chromium`"
        ) from exc

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            try:
                page.goto(
                    url,
                    timeout=max(timeout, 1) * 1000,
                    wait_until="networkidle",
                )
                html = page.content()
                final_url = page.url
            finally:
                context.close()
                browser.close()
    except PlaywrightTimeoutError as exc:
        raise HeadlessFetchError(f"Headless 抓取超时: {url}") from exc
    except Exception as exc:  # pragma: no cover - 多种底层异常
        raise HeadlessFetchError(f"Headless 抓取失败: {url}") from exc

    return html, final_url


def _extract_images(soup: BeautifulSoup, base_url: str) -> List[str]:
    """从 BeautifulSoup 对象中提取图片 URL 列表。"""
    image_urls: List[str] = []
    for img in soup.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        full = urljoin(base_url, src)
        if full not in image_urls:
            image_urls.append(full)
    return image_urls


def _html_to_markdown(html: str) -> str:
    """将 HTML 转换为 Markdown 格式。

    使用 markdownify 库进行转换，配置适合文章阅读的选项。
    """
    return md(
        html,
        heading_style="ATX",  # 使用 # 风格标题
        bullets="-",  # 使用 - 作为列表符号
        code_language="",  # 不猜测代码语言
        strip=["script", "style", "noscript"],  # 移除脚本和样式
    ).strip()


def parse_page(url: str, html: str, final_url: str | None = None) -> PageContent:
    """解析 HTML 页面，使用 Readability 提取正文并转换为 Markdown。

    Args:
        url: 原始请求 URL
        html: 完整的 HTML 内容
        final_url: 最终 URL（可能经过重定向）

    Returns:
        PageContent 对象，包含提取的内容和原始 HTML
    """
    final_url = final_url or url

    # 使用 readability-lxml 提取正文
    doc = Document(html)
    title = doc.title() or final_url
    article_html = doc.summary()
    # 转换为 Markdown
    markdown = _html_to_markdown(article_html)

    # 解析文章 HTML 获取纯文本和图片
    article_soup = BeautifulSoup(article_html, "html.parser")
    # 移除不需要的标签
    for tag in article_soup(["script", "style", "noscript"]):
        tag.decompose()
    # 提取纯文本（用于 LLM 摘要）
    text = article_soup.get_text(separator="\n", strip=True)

    return PageContent(
        url=url,
        final_url=final_url,
        title=title,
        text=text,
        markdown=markdown,
        raw_html=html,
        article_html=article_html
    )
