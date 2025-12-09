"""HTML 处理工具函数。"""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from markdownify import markdownify as md
from readability import Document

logger = logging.getLogger(__name__)


def html_to_markdown(html: str) -> str:
    """将 HTML 转换为 Markdown 格式。

    Args:
        html: HTML 内容

    Returns:
        Markdown 格式的文本
    """
    return md(
        html,
        heading_style="ATX",  # 使用 # 风格标题
        bullets="-",  # 使用 - 作为列表符号
        code_language="",  # 不猜测代码语言
        strip=["script", "style", "noscript"],  # 移除脚本和样式
    ).strip()


def make_links_absolute(html: str, base_url: str) -> str:
    """将 HTML 中的相对链接转换为绝对链接。

    Args:
        html: 需要处理的 HTML 内容
        base_url: 用于解析相对链接的基础 URL

    Returns:
        处理后的 HTML，所有相对链接已转换为绝对链接
    """
    soup = BeautifulSoup(html, "html.parser")

    # 处理 <a> 标签的 href 属性
    for tag in soup.find_all("a", href=True):
        href = str(tag["href"])
        if href and not urlparse(href).scheme:
            tag["href"] = urljoin(base_url, href)

    # 处理 <img> 标签的 src 属性
    for tag in soup.find_all("img", src=True):
        src = str(tag["src"])
        if src and not urlparse(src).scheme:
            tag["src"] = urljoin(base_url, src)

    return str(soup)


def extract_article(html: str, base_url: str) -> tuple[str, str, str, str]:
    """使用 Readability 从 HTML 提取文章内容。

    Args:
        html: 完整的 HTML 内容
        base_url: 用于解析相对链接的基础 URL

    Returns:
        (title, article_html, markdown, text) 元组
    """
    logger.info("使用 Readability 提取正文, HTML 长度: %d", len(html))

    doc = Document(html)
    title = doc.title() or ""
    article_html = doc.summary()
    logger.info("Readability 提取完成, 标题: %s, 文章 HTML 长度: %d", title, len(article_html))

    # 将相对链接转换为绝对链接
    article_html = make_links_absolute(article_html, base_url)

    # 转换为 Markdown
    markdown = html_to_markdown(article_html)
    logger.info("Markdown 转换完成, 长度: %d", len(markdown))

    # 提取纯文本
    article_soup = BeautifulSoup(article_html, "html.parser")
    for tag in article_soup(["script", "style", "noscript"]):
        tag.decompose()
    text = article_soup.get_text(separator="\n", strip=True)
    logger.info("纯文本提取完成, 长度: %d", len(text))

    return title, article_html, markdown, text
