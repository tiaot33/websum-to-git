from datetime import datetime, timezone

from websum_bot.markdown_note import NoteMeta, build_frontmatter, build_note, slugify


def test_build_frontmatter_contains_metadata():
    meta = NoteMeta(
        title="My Article",
        source_url="https://example.com/page",
        created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        tags=["tag1", "tag2"],
        categories=["cat"],
        keywords=["kw"],
    )
    fm = build_frontmatter(meta)
    assert "title: My Article" in fm
    assert "source: https://example.com/page" in fm
    assert "created_at: 2024-01-01T00:00:00+00:00" in fm
    assert "tags:" in fm


def test_build_note_wraps_body_and_frontmatter():
    meta = NoteMeta(
        title=None,
        source_url="https://example.com",
        created_at=datetime.now(timezone.utc),
        tags=[],
        categories=[],
        keywords=[],
    )
    note = build_note(meta, "Body content")
    assert note.startswith("---\n")
    assert "Body content" in note


def test_slugify_fallback():
    assert slugify("!!!", fallback="note") == "note"
    assert slugify("Hello World") == "hello-world"

