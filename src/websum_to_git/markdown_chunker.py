from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import tiktoken

ParagraphKind = Literal["heading", "code", "list", "quote", "table", "text"]


@dataclass(frozen=True)
class ParagraphBlock:
    text: str
    kind: ParagraphKind
    fence: str | None = None


_HEADING_LINE_RE = re.compile(r"^#{1,6}\s")
_LIST_LINE_RE = re.compile(r"^(\s*[-*+]\s+|\s*\d+\.\s+)")
_TABLE_LINE_RE = re.compile(r"^\s*\|.+\|\s*$")


def split_markdown_into_chunks(text: str, max_tokens: int) -> list[str]:
    """将 Markdown 文本拆分为适合 LLM 处理的 chunk 列表。"""
    paragraphs = _split_into_paragraphs(text)
    return _build_chunks(paragraphs, max_tokens)


def _split_into_paragraphs(text: str) -> list[ParagraphBlock]:
    """按 Markdown 块结构切分段落，保持语义边界与原始格式。"""
    lines = text.splitlines()
    paragraphs: list[ParagraphBlock] = []
    current: list[str] = []
    current_kind: ParagraphKind = "text"
    current_fence: str | None = None
    in_code_block = False
    active_fence: str | None = None

    def flush_current() -> None:
        nonlocal current, current_kind, current_fence
        if not current:
            return
        paragraph_text = "\n".join(current)
        if current_kind != "code":
            paragraph_text = paragraph_text.strip("\n")
        paragraphs.append(
            ParagraphBlock(text=paragraph_text, kind=current_kind, fence=current_fence)
        )
        current = []
        current_kind = "text"
        current_fence = None

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()
        fence = _detect_code_fence_marker(stripped)

        if in_code_block:
            current.append(line)
            if fence and active_fence and fence == active_fence:
                in_code_block = False
                active_fence = None
                flush_current()
            continue

        if fence:
            flush_current()
            in_code_block = True
            active_fence = fence
            current_kind = "code"
            current_fence = fence
            current.append(line)
            continue

        if not stripped:
            flush_current()
            continue

        if _HEADING_LINE_RE.match(stripped):
            flush_current()
            paragraphs.append(ParagraphBlock(text=stripped, kind="heading"))
            continue

        line_kind = _classify_structural_line(stripped)
        if not current:
            current_kind = line_kind
        elif current_kind != line_kind:
            flush_current()
            current_kind = line_kind

        current.append(line)

    if current:
        flush_current()

    if not paragraphs:
        return [ParagraphBlock(text=text.strip(), kind="text")]

    return paragraphs


def _build_chunks(paragraphs: list[ParagraphBlock], max_tokens: int) -> list[str]:
    """按段落拼接为多个 chunk，基于 tiktoken 估算并保持 Markdown 完整性。"""
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    separator_tokens = estimate_token_length("\n\n")

    def flush_current() -> None:
        nonlocal current, current_len
        if not current:
            return
        chunks.append("\n\n".join(current).strip("\n"))
        current = []
        current_len = 0

    for para in paragraphs:
        content = para.text.rstrip() if para.kind == "code" else para.text.strip("\n")
        if not content:
            continue

        para_len = estimate_token_length(content)

        if para_len >= max_tokens:
            flush_current()
            if para.kind == "code":
                chunks.extend(_split_code_block_chunks(para, max_tokens))
            else:
                chunks.extend(
                    _split_plain_text_chunks(
                        content,
                        max_tokens,
                        preserve_whitespace=para.kind in {"list", "quote", "table"},
                    )
                )
            continue

        if para.kind == "heading" and current:
            flush_current()

        extra = separator_tokens if current else 0
        if current and current_len + extra + para_len > max_tokens:
            flush_current()

        current.append(content)
        current_len = current_len + extra + para_len if current_len else para_len

    flush_current()

    return chunks


def _split_plain_text_chunks(
    text: str, max_len: int, *, preserve_whitespace: bool = False
) -> list[str]:
    if max_len <= 0:
        return [text]

    lines = text.splitlines()
    newline_tokens = estimate_token_length("\n")
    parts: list[str] = []
    current_lines: list[str] = []
    current_len = 0

    for line in lines:
        line_tokens = estimate_token_length(line)
        if not current_lines:
            current_lines.append(line)
            current_len = line_tokens
            continue

        sep = newline_tokens
        if current_len + sep + line_tokens > max_len:
            chunk = "\n".join(current_lines)
            chunk = chunk.rstrip("\n") if preserve_whitespace else chunk.strip("\n")
            if chunk:
                parts.append(chunk)
            current_lines = [line]
            current_len = line_tokens
        else:
            current_lines.append(line)
            current_len += sep + line_tokens

    if current_lines:
        chunk = "\n".join(current_lines)
        chunk = chunk.rstrip("\n") if preserve_whitespace else chunk.strip("\n")
        if chunk:
            parts.append(chunk)

    result: list[str] = []
    for part in parts or [text.rstrip("\n") if preserve_whitespace else text.strip()]:
        if estimate_token_length(part) <= max_len:
            result.append(part)
        else:
            result.extend(
                _hard_split_by_tokens(
                    part,
                    max_len,
                    preserve_whitespace=preserve_whitespace,
                )
            )

    return [item for item in result if item]


def _split_code_block_chunks(paragraph: ParagraphBlock, max_len: int) -> list[str]:
    if max_len <= 0:
        return [paragraph.text]

    fence_marker = paragraph.fence or "```"
    lines = paragraph.text.splitlines()
    if not lines:
        return []

    start_line = lines[0] if _is_code_fence_line(lines[0]) else fence_marker
    end_line = lines[-1] if _is_code_fence_line(lines[-1]) else fence_marker

    body_start = 1 if _is_code_fence_line(lines[0]) else 0
    body_end = len(lines) - 1 if _is_code_fence_line(lines[-1]) else len(lines)
    body_lines = lines[body_start:body_end]
    if not body_lines and not _is_code_fence_line(lines[0]):
        body_lines = lines

    return _split_code_body_lines(start_line, end_line, body_lines, max_len, fence_marker)


def _split_code_body_lines(
    start_line: str,
    end_line: str,
    body_lines: list[str],
    max_len: int,
    fence_marker: str,
) -> list[str]:
    newline_tokens = estimate_token_length("\n")
    fence_tokens = estimate_token_length(start_line) + estimate_token_length(end_line)
    allowed_tokens = max(max_len - fence_tokens, 1)

    if not body_lines:
        return ["\n".join([start_line, end_line]).strip()]

    chunks: list[str] = []
    current_lines: list[str] = []
    current_tokens = fence_tokens

    for line in body_lines:
        line_tokens = estimate_token_length(line)
        sep = newline_tokens if current_lines else 0

        if current_lines and current_tokens + sep + line_tokens > max_len:
            chunks.append("\n".join([start_line] + current_lines + [end_line]).rstrip())
            current_lines = []
            current_tokens = fence_tokens
            sep = 0

        if not current_lines and fence_tokens + line_tokens > max_len:
            pieces = _hard_split_by_tokens(
                line,
                allowed_tokens,
                preserve_whitespace=True,
            )
            for piece in pieces:
                chunks.append("\n".join([start_line, piece, end_line]).rstrip())
            continue

        current_lines.append(line)
        if len(current_lines) == 1:
            current_tokens = fence_tokens + line_tokens
        else:
            current_tokens += sep + line_tokens

    if current_lines:
        chunks.append("\n".join([start_line] + current_lines + [end_line]).rstrip())

    return chunks or ["\n".join([fence_marker, fence_marker]).strip()]


def estimate_token_length(text: str) -> int:
    """估算文本的 token 长度（使用 tiktoken cl100k_base 编码）。"""
    if not text:
        return 0
    encoder = _get_token_encoder()
    return len(encoder.encode(text, disallowed_special=()))


def _hard_split_by_tokens(
    text: str, max_len: int, *, preserve_whitespace: bool = False
) -> list[str]:
    if max_len <= 0:
        return [text]

    encoder = _get_token_encoder()
    tokens = encoder.encode(text, disallowed_special=())
    if not tokens:
        cleaned = text if preserve_whitespace else text.strip()
        return [cleaned] if cleaned else []

    pieces: list[str] = []
    start = 0
    total = len(tokens)
    while start < total:
        end = min(start + max_len, total)
        piece = encoder.decode(tokens[start:end])
        piece = piece if preserve_whitespace else piece.strip()
        if piece:
            pieces.append(piece)
        start = end

    if pieces:
        return pieces

    cleaned = text if preserve_whitespace else text.strip()
    return [cleaned] if cleaned else []


@lru_cache(maxsize=1)
def _get_token_encoder() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def _classify_structural_line(line: str) -> ParagraphKind:
    if _LIST_LINE_RE.match(line):
        return "list"
    if line.startswith(">"):
        return "quote"
    if _TABLE_LINE_RE.match(line):
        return "table"
    return "text"


def _detect_code_fence_marker(line: str) -> str | None:
    if not line:
        return None
    if line.startswith("```"):
        return "```"
    if line.startswith("~~~"):
        return "~~~"
    return None


def _is_code_fence_line(line: str) -> bool:
    return bool(_detect_code_fence_marker(line.strip()))

