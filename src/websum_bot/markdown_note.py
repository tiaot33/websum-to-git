from __future__ import annotations

"""Build YAML frontmatter + Markdown note from structured metadata."""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List

import yaml


@dataclass
class NoteMeta:
    title: str | None
    source_url: str
    created_at: datetime
    tags: List[str]
    categories: List[str]
    keywords: List[str]


def slugify(value: str, fallback: str = "note") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or fallback


def _listize(items: Iterable[str] | None) -> list[str]:
    return [i for i in (items or []) if i]


def build_frontmatter(meta: NoteMeta) -> str:
    data = {
        "title": meta.title,
        "source": meta.source_url,
        "created_at": meta.created_at.astimezone(timezone.utc).isoformat(),
        "tags": _listize(meta.tags),
        "categories": _listize(meta.categories),
        "keywords": _listize(meta.keywords),
    }
    yaml_block = yaml.safe_dump(data, sort_keys=False, allow_unicode=False).strip()
    return f"---\n{yaml_block}\n---\n"


def build_note(meta: NoteMeta, body_markdown: str) -> str:
    frontmatter = build_frontmatter(meta)
    body = body_markdown.strip()
    return f"{frontmatter}\n{body}\n"
