from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


class HeadlessFetchError(RuntimeError):
    """Headless 抓取过程中出现的异常。"""


@dataclass
class PageContent:
    url: str
    final_url: str
    title: str
    text: str
    image_urls: List[str]


def fetch_html(url: str, timeout: int = 15, verify: bool = True) -> Tuple[str, str]:
    resp = requests.get(url, timeout=timeout, verify=verify)
    resp.raise_for_status()
    return resp.text, resp.url


def fetch_html_headless(url: str, timeout: int = 15) -> Tuple[str, str]:
    """使用 Playwright 抓取 HTML，返回 (html, final_url)。"""

    try:
        from playwright.sync_api import (  # type: ignore import-not-found
            TimeoutError as PlaywrightTimeoutError,
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


def parse_page(url: str, html: str, final_url: str | None = None) -> PageContent:
    final_url = final_url or url
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    title_tag = soup.find("title")
    title = (title_tag.get_text(strip=True) if title_tag else "").strip() or final_url

    body = soup.body or soup
    text = body.get_text(separator="\n", strip=True)

    image_urls: List[str] = []
    for img in body.find_all("img"):
        src = img.get("src")
        if not src:
            continue
        full = urljoin(final_url, src)
        if full not in image_urls:
            image_urls.append(full)

    return PageContent(
        url=url,
        final_url=final_url,
        title=title,
        text=text,
        image_urls=image_urls,
    )
