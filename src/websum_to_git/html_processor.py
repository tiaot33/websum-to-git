from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, urljoin, urlparse

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

_HEADLESS_EXTRA_HEADERS = {
    key: value for key, value in DEFAULT_HEADERS.items() if key.lower() not in {"user-agent", "connection"}
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


def fetch_html(url: str, timeout: int = 15, verify: bool = True) -> tuple[str, str]:
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


def fetch_html_headless(url: str, timeout: int = 15) -> tuple[str, str]:
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
            # 默认使用有头浏览器，配合 Docker 中的 Xvfb 或宿主机 X Server 使用
            browser = p.chromium.launch(headless=False, args=["--disable-blink-features=AutomationControlled"])
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=DEFAULT_HEADERS["User-Agent"],
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
                permissions=["geolocation"],
                extra_http_headers=_HEADLESS_EXTRA_HEADERS,
            )
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
            try:
                from playwright_stealth import (  # type: ignore import-not-found
                    stealth_sync,
                )
            except ModuleNotFoundError:
                stealth_sync = None  # type: ignore[assignment]

            page = context.new_page()
            if stealth_sync is not None:
                stealth_sync(page)

            try:
                response = page.goto(
                    url,
                    timeout=max(timeout, 1) * 1000,
                    wait_until="domcontentloaded",
                )
                # 继续等待页面完成主要资源加载，给懒加载内容留出时间
                try:  # noqa: SIM105
                    page.wait_for_load_state("load")
                except PlaywrightTimeoutError:
                    pass
                try:  # noqa: SIM105
                    page.wait_for_load_state("networkidle", timeout=8000)
                except PlaywrightTimeoutError:
                    pass
                page.wait_for_timeout(3000)
                # 缓慢滚动至页面底部，触发懒加载图片/内容
                page.evaluate(
                    """
(() => {
    return new Promise((resolve) => {
        const scrollingElement = document.scrollingElement || document.documentElement;
        const viewport = window.innerHeight || document.documentElement.clientHeight || 800;
        const step = Math.max(Math.floor(viewport * 0.75), 300);
        const delay = 250;

        const scroll = () => {
            const { scrollTop, scrollHeight, clientHeight } = scrollingElement;
            if (scrollTop + clientHeight >= scrollHeight) {
                resolve();
                return;
            }
            window.scrollBy(0, step);
            setTimeout(scroll, delay);
        };

        scroll();
    });
})()
"""
                )
                page.wait_for_timeout(5000)
                if response and response.status >= 400:
                    status_text = getattr(response, "status_text", "") or ""
                    raise HeadlessFetchError(f"Headless 抓取失败: HTTP {response.status} {status_text}".strip())
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


def fetch_html_via_mirror(url: str, timeout: int = 15) -> tuple[str, str]:
    """通过公开镜像服务获取 HTML，用于应对被封禁/403 的站点。"""

    encoded_url = quote(url, safe=":/?&=#%")
    mirror_url = f"https://r.jina.ai/{encoded_url}"
    resp = requests.get(
        mirror_url,
        timeout=timeout,
        headers=DEFAULT_HEADERS,
    )
    resp.raise_for_status()
    return resp.text, url


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


def _make_links_absolute(html: str, base_url: str) -> str:
    """将 HTML 中的相对链接转换为绝对链接。

    处理 <a href> 和 <img src> 等属性中的相对 URL。

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
            # 相对链接，转换为绝对链接
            tag["href"] = urljoin(base_url, href)

    # 处理 <img> 标签的 src 属性
    for tag in soup.find_all("img", src=True):
        src = str(tag["src"])
        if src and not urlparse(src).scheme:
            tag["src"] = urljoin(base_url, src)

    return str(soup)


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
    title = doc.title() or ""
    article_html = doc.summary()
    # 将相对链接转换为绝对链接，确保 Markdown 中的链接可正确访问
    article_html = _make_links_absolute(article_html, final_url)
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
        article_html=article_html,
    )
