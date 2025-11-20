from __future__ import annotations

"""Fetch HTML and convert main content into Markdown while keeping links/images."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify as md


USER_AGENT = "WebSumToGitBot/0.1"


@dataclass
class HtmlContent:
    url: str
    title: Optional[str]
    markdown: str
    fetched_at: datetime


class HtmlFetchError(Exception):
    pass


def fetch_html(url: str, timeout: int = 15) -> str:
    if not url.startswith(("http://", "https://")):
        raise HtmlFetchError("URL must start with http:// or https://")
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(url, timeout=timeout, headers=headers)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise HtmlFetchError(f"Failed to fetch HTML: {exc}") from exc
    if not resp.text:
        raise HtmlFetchError("Empty response body")
    return resp.text


def _normalize_links(soup: BeautifulSoup, base_url: str) -> None:
    for tag in soup.find_all(href=True):
        tag["href"] = urljoin(base_url, tag["href"])
    for tag in soup.find_all(src=True):
        tag["src"] = urljoin(base_url, tag["src"])


def _pick_main_container(soup: BeautifulSoup) -> BeautifulSoup:
    for selector in ["article", "main", "div#content", "section"]:
        node = soup.select_one(selector)
        if node:
            return node
    return soup.body or soup


def _strip_noise(soup: BeautifulSoup) -> None:
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()


def extract_content(url: str, html: str) -> HtmlContent:
    soup = BeautifulSoup(html, "html.parser")
    _strip_noise(soup)
    _normalize_links(soup, url)
    main = _pick_main_container(soup)

    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    markdown = md(
        str(main),
        heading_style="ATX",
        strip=[]
    ).strip()

    fetched_at = datetime.now(timezone.utc)
    return HtmlContent(url=url, title=title, markdown=markdown, fetched_at=fetched_at)
