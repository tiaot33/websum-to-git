import yaml

from websum_to_git.fetchers.defuddle import _parse_front_matter
from websum_to_git.fetchers.structs import PageContent
from websum_to_git.pipeline import _build_front_matter


def test_parse_front_matter_supports_multiline_yaml_scalars() -> None:
    markdown = """---
title: Example Title
author: Alice
description: |
  第一行
  第二行
---

正文
"""

    meta, body = _parse_front_matter(markdown)

    assert meta["title"] == "Example Title"
    assert meta["author"] == "Alice"
    assert meta["description"].splitlines() == ["第一行", "第二行"]
    assert body.strip() == "正文"


def test_build_front_matter_round_trips_multiline_metadata() -> None:
    page = PageContent(
        url="https://example.com/article",
        final_url="https://example.com/article",
        title="Example Title",
        text="body",
        markdown="body",
        raw_html="",
        article_html="",
        extra_meta={
            "author": "Alice",
            "description": "第一行\n第二行",
        },
    )

    front_matter = _build_front_matter(page, "2026.04.17. 10:00", ["web", "ai"])
    payload = front_matter.removeprefix("---\n").removesuffix("\n---\n")
    meta = yaml.safe_load(payload)

    assert meta == {
        "source": "https://example.com/article",
        "created_at": "2026.04.17. 10:00",
        "author": "Alice",
        "description": "第一行\n第二行",
        "tags": ["web", "ai"],
    }
