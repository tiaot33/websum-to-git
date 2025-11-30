"""markdown_chunker 分块行为测试。"""

from __future__ import annotations

import math
from pathlib import Path

from websum_to_git.markdown_chunker import estimate_token_length, split_markdown_into_chunks


def _load_sample_markdown(fixtures_dir: Path) -> str:
    """从 fixtures 目录加载示例 Markdown 文本。"""
    # path = fixtures_dir / "sample_markdown.md"
    path = fixtures_dir / "test.md"
    return path.read_text(encoding="utf-8")


def test_split_markdown_chunks_respect_max_tokens(fixtures_dir: Path) -> None:
    """所有分块的 token 数都不应超过 max_tokens。"""
    text = _load_sample_markdown(fixtures_dir)
    max_tokens = 400

    chunks = split_markdown_into_chunks(text, max_tokens)

    assert chunks, "应至少生成一个 chunk"

    for chunk in chunks:
        assert estimate_token_length(chunk) <= max_tokens


def test_split_markdown_chunks_are_compact(fixtures_dir: Path) -> None:
    """除最后一个外，其余 chunk 应较为“饱满”，避免出现大量小块。"""
    text = _load_sample_markdown(fixtures_dir)

    # 使用较小的 max_tokens 强制生成多个 chunk
    max_tokens = 300
    chunks = split_markdown_into_chunks(text, max_tokens)

    assert len(chunks) >= 2, "示例 Markdown 应被拆分为多个 chunk"

    token_lengths = [estimate_token_length(chunk) for chunk in chunks]

    # 所有 chunk 必须满足上限约束
    assert all(t <= max_tokens for t in token_lengths)

    # 除最后一个外，其余 chunk 的 token 数应至少达到上限的一半
    if len(token_lengths) > 1:
        filled_chunks = token_lengths[:-1]
        assert all(
            t >= max_tokens * 0.5 for t in filled_chunks
        ), f"非最后一个 chunk 利用率过低: {filled_chunks}"


def test_split_markdown_chunk_count_not_fragmented(fixtures_dir: Path) -> None:
    """实际 chunk 数应接近理论最小值，防止分块过于零碎。"""
    text = _load_sample_markdown(fixtures_dir)

    max_tokens = 1000
    total_tokens = estimate_token_length(text)
    theoretical_min = math.ceil(total_tokens / max_tokens)

    chunks = split_markdown_into_chunks(text, max_tokens)

    # 至少不能比理论最小值多出太多块（留 1 块冗余给结构边界）
    assert len(chunks) <= theoretical_min + 1, (
        f"chunk 数量过多，理论最小值为 {theoretical_min}，实际为 {len(chunks)}"
    )
