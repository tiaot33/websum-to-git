"""URL 归一化工具。"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_QUERY_KEYS = frozenset(
    {
        "_ga",
        "_gl",
        "dclid",
        "fbclid",
        "gclid",
        "igshid",
        "mc_cid",
        "mc_eid",
        "mkt_tok",
        "msclkid",
        "si",
        "spm",
        "yclid",
        "s"
    }
)


def strip_tracking_params(url: str) -> str:
    """移除 URL 中常见的追踪参数，保留业务参数和片段。"""
    parsed = urlsplit(url)
    if not parsed.query:
        return url

    filtered_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_tracking_param(key)
    ]
    normalized_query = urlencode(filtered_items, doseq=True)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, normalized_query, parsed.fragment))


def _is_tracking_param(key: str) -> bool:
    normalized = key.lower()
    return normalized.startswith("utm_") or normalized in TRACKING_QUERY_KEYS
