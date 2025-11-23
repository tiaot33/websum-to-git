from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


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


@dataclass
class PageContent:
    url: str
    final_url: str
    title: str
    text: str
    image_urls: List[str]


def fetch_html(url: str, timeout: int = 15, verify: bool = True) -> Tuple[str, str]:
    resp = requests.get(
        url,
        timeout=timeout,
        verify=verify,
        headers=DEFAULT_HEADERS,
    )
    resp.raise_for_status()
    return resp.text, resp.url


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
