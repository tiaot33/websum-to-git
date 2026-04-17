"""Defuddle Fetcher 实现。

Defuddle 是一个零配置的网页正文提纯代理：直接访问
``https://defuddle.md/<原始 URL>`` 即可得到带 YAML front matter 的 Markdown。
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import requests
import yaml

from websum_to_git.fetchers.structs import EXTRA_META_KEYS, FetchError, PageContent, get_common_config
from websum_to_git.url_utils import strip_tracking_params

if TYPE_CHECKING:
    from websum_to_git.config import AppConfig

logger = logging.getLogger(__name__)

DEFUDDLE_ENDPOINT = "https://defuddle.md/"
_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def _build_proxy_url(url: str, config: AppConfig) -> str:
    """构造 Defuddle 代理 URL。

    Defuddle 直接把目标 URL 拼接在服务域名之后，例如
    ``https://defuddle.md/example.com/article``。这里会去掉原始 URL 的
    协议头，避免双斜杠影响解析。
    """
    if not config.defuddle.enabled:
        raise FetchError("未启用 Defuddle 兜底抓取")

    request_url = strip_tracking_params(url) if config.defuddle.strip_tracking else url
    base_url = (config.defuddle.base_url or DEFUDDLE_ENDPOINT).rstrip("/") + "/"
    # 去掉协议头（如 "https://"），避免双斜杠影响解析
    parsed = urlparse(request_url)
    stripped = request_url.split("://", 1)[1] if parsed.scheme else request_url
    return base_url + stripped


def _parse_front_matter(markdown: str) -> tuple[dict[str, str], str]:
    """从 Markdown 中解析出 front matter 字段和正文。

    只做简单 key: "value" 解析，不引入 YAML 依赖，避免过度设计 (YAGNI)。
    """
    match = _FRONT_MATTER_RE.match(markdown)
    if not match:
        return {}, markdown

    body = markdown[match.end() :]
    try:
        parsed_meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        logger.warning("Defuddle front matter 解析失败: %s", exc)
        return {}, markdown

    if not isinstance(parsed_meta, dict):
        logger.warning("Defuddle front matter 不是对象结构，忽略元数据")
        return {}, body

    meta = {str(key): "" if value is None else str(value) for key, value in parsed_meta.items()}
    return meta, body


def fetch_defuddle(url: str, config: AppConfig) -> PageContent:
    """使用 Defuddle 代理抓取网页并提取 Markdown。

    Args:
        url: 目标 URL。
        config: 应用配置（复用 http.verify_ssl 与超时设置）。

    Returns:
        PageContent, 包含 Markdown 内容。

    Raises:
        FetchError: 当请求失败或内容为空时。
    """
    proxy_url = _build_proxy_url(url, config)
    timeout, verify_ssl = get_common_config(config)

    logger.info("正在使用 Defuddle 抓取: %s", proxy_url)
    try:
        response = requests.get(
            proxy_url,
            timeout=timeout,
            verify=verify_ssl,
            headers={"Accept": "text/markdown, text/plain, */*"},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Defuddle 请求异常: %s", exc)
        raise FetchError(f"Defuddle Error: {exc}") from exc

    raw_markdown = response.text or ""
    if not raw_markdown.strip():
        raise FetchError("Defuddle 返回内容为空")

    # 剥离 front matter：title/source 用于填充 PageContent 主字段，其余
    # (author/site/published 等) 放入 extra_meta 供 pipeline 合并到最终 front matter。
    # 正文只保留纯 Markdown，避免下游重复写入 YAML。
    meta, body = _parse_front_matter(raw_markdown)
    title = meta.get("title") or "No Title"
    final_url = meta.get("source") or url
    if config.defuddle.strip_tracking:
        final_url = strip_tracking_params(final_url)
    body = body.lstrip("\n")

    extra_meta = {key: meta[key] for key in EXTRA_META_KEYS if meta.get(key)}

    return PageContent(
        url=url,
        final_url=final_url,
        title=title,
        text=body,
        markdown=body,
        raw_html="",
        article_html="",
        extra_meta=extra_meta,
    )
