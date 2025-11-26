from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from typing import Literal

import tiktoken

from .config import AppConfig
from .github_client import GitHubPublisher, PublishResult
from .html_processor import PageContent, fetch_html, fetch_html_headless, parse_page
from .llm_client import LLMClient

# 近似控制每次请求的输入规模（按字符近似 token，主要面向中文场景）
_MAX_SUMMARY_INPUT_CHARS = 10_000

_CHUNK_SUMMARY_SYSTEM_PROMPT = (
    "你是一个网页内容分析助手，用于处理长文的单个片段。\n"
    "目标：将该片段中的核心信息提炼成简洁的要点，供后续对整篇文章进行汇总。\n"
    "请在内部按步骤思考，但最终只输出要点列表，不要输出任何思考过程或解释。\n"
    "约束：\n"
    "1. 只关注正文内容，忽略导航栏、侧边栏、页脚、评论区、推荐阅读、广告、Cookie 提示等与正文无关的噪音。\n"
    "2. 对示意图、流程图、步骤图、表格、代码示例等，如果有文字描述或关键结论，请保留这些信息，并在要点中用文字说明。\n"
    "3. 使用简洁的中文；优先使用无序列表，每条要点表达一个关键信息。\n"
    "4. 不要生成 Markdown 标题，不要生成 YAML front matter，不要生成图片链接或附件标记。\n"
)

_FINAL_SUMMARY_SYSTEM_PROMPT = (
    "你是一个知识管理助手，负责将网页内容整理为适合 Obsidian 的 Markdown 笔记。\n"
    "请在内部按步骤思考，但最终只输出符合要求的 Markdown，不要输出任何分析过程或解释。\n"
    "整体要求：\n"
    "1. 只总结网页中的正文内容，忽略导航栏、侧边栏、页脚、评论区、推荐阅读、广告、Cookie 提示等噪音。\n"
    "2. 对示意图、流程图、步骤图、表格、代码示例等，保留其核心含义和关键步骤，用文字形式表达出来。\n"
    "3. 使用简洁自然的中文。\n"
    "4. 输出结构清晰的 Markdown，从二级标题 (##) 开始，不要使用一级标题 (#)，也不要生成 YAML front matter。\n"
    "5. 不要包含任何图片链接或附件标记，图片会由系统自动附加。\n"
    "推荐结构：\n"
    "## 摘要\n"
    "- 用 3-5 句话概括全文的核心内容。\n"
    "## 关键观点\n"
    "- 列出文章中最重要的结论或观点，每点一行。\n"
    "## 重要细节\n"
    "- 按主题分组列出支撑关键观点的重要细节、示例或数据。\n"
    "## 可执行要点\n"
    "- 如果文章包含步骤、流程或实践建议，将其整理为清晰的操作要点；\n"
    "- 如果没有明确的行动建议，可以简单说明“此文主要为背景和概念介绍，没有明确可执行步骤”。\n"
)

ParagraphKind = Literal["heading", "code", "list", "quote", "table", "text"]


@dataclass(frozen=True)
class ParagraphBlock:
    text: str
    kind: ParagraphKind
    fence: str | None = None


_HEADING_LINE_RE = re.compile(r"^#{1,6}\s")
_LIST_LINE_RE = re.compile(r"^(\s*[-*+]\s+|\s*\d+\.\s+)")
_TABLE_LINE_RE = re.compile(r"^\s*\|.+\|\s*$")


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


def _build_chunks(paragraphs: list[ParagraphBlock], max_chars: int) -> list[str]:
    """按段落拼接为多个 chunk，基于 tiktoken 估算并保持 Markdown 完整性。"""
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    separator_tokens = _estimate_token_length("\n\n")

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

        para_len = _estimate_token_length(content)

        if para_len >= max_chars:
            flush_current()
            if para.kind == "code":
                chunks.extend(_split_code_block_chunks(para, max_chars))
            else:
                chunks.extend(
                    _split_plain_text_chunks(
                        content,
                        max_chars,
                        preserve_whitespace=para.kind in {"list", "quote", "table"},
                    )
                )
            continue

        if para.kind == "heading" and current:
            flush_current()

        extra = separator_tokens if current else 0
        if current and current_len + extra + para_len > max_chars:
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
    newline_tokens = _estimate_token_length("\n")
    parts: list[str] = []
    current_lines: list[str] = []
    current_len = 0

    for line in lines:
        line_tokens = _estimate_token_length(line)
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
        if _estimate_token_length(part) <= max_len:
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
    newline_tokens = _estimate_token_length("\n")
    fence_tokens = _estimate_token_length(start_line) + _estimate_token_length(end_line)
    allowed_tokens = max(max_len - fence_tokens, 1)

    if not body_lines:
        return ["\n".join([start_line, end_line]).strip()]

    chunks: list[str] = []
    current_lines: list[str] = []
    current_tokens = fence_tokens

    for line in body_lines:
        line_tokens = _estimate_token_length(line)
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


def _estimate_token_length(text: str) -> int:
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
    try:
        return tiktoken.encoding_for_model("gpt-4o-mini")
    except Exception:
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


class HtmlToObsidianPipeline:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._llm = LLMClient(config.llm)
        self._publisher = GitHubPublisher(config.github)

    def process_url(self, url: str) -> PublishResult:
        if self._config.http.fetch_mode == "headless":
            html, final_url = fetch_html_headless(url)
        else:
            html, final_url = fetch_html(
                url,
                verify=self._config.http.verify_ssl,
            )
        page = parse_page(url=url, html=html, final_url=final_url)

        summary_md = self._summarize_page(page)

        full_markdown = self._build_markdown(page=page, summary_markdown=summary_md)

        return self._publisher.publish_markdown(
            content=full_markdown,
            source=page.final_url,
            title=page.title,
        )

    def _summarize_page(self, page: PageContent) -> str:
        """将网页正文内容转换为适合 Obsidian 的 Markdown 摘要。"""
        text = page.markdown.strip()
        if not text:
            return "（页面中未提取到正文内容）"

        # 内容较短时，直接一次性总结
        if len(text) <= _MAX_SUMMARY_INPUT_CHARS:
            user_content = (
                f"网页标题: {page.title}\n网页地址: {page.final_url}\n\n网页正文内容（已去除脚本等噪音标签）:\n{text}\n"
            )
            return self._llm.generate(
                system_prompt=_FINAL_SUMMARY_SYSTEM_PROMPT,
                user_content=user_content,
            ).strip()

        # 内容较长时，按段落分块 + 分块总结 + 汇总
        paragraphs = _split_into_paragraphs(text)
        chunks = _build_chunks(paragraphs, _MAX_SUMMARY_INPUT_CHARS)

        chunk_summaries: list[str] = []
        total = len(chunks)
        for idx, chunk in enumerate(chunks, start=1):
            chunk_user_content = (
                f"网页标题: {page.title}\n"
                f"网页地址: {page.final_url}\n"
                f"当前片段: {idx}/{total}\n\n"
                f"片段正文内容:\n{chunk}\n"
            )
            chunk_summary = self._llm.generate(
                system_prompt=_CHUNK_SUMMARY_SYSTEM_PROMPT,
                user_content=chunk_user_content,
            ).strip()
            if chunk_summary:
                # 只在汇总输入中保留必要的标记信息，避免额外噪音
                chunk_summaries.append(f"片段 {idx}/{total} 的要点摘要：\n{chunk_summary}")

        merged_summary_input = "\n\n".join(chunk_summaries)

        final_user_content = (
            f"网页标题: {page.title}\n"
            f"网页地址: {page.final_url}\n\n"
            "下面是该网页按片段总结后的要点，请综合这些信息生成一份完整的 Markdown 笔记：\n\n"
            f"{merged_summary_input}\n"
        )

        return self._llm.generate(
            system_prompt=_FINAL_SUMMARY_SYSTEM_PROMPT,
            user_content=final_user_content,
        ).strip()

    def _build_markdown(self, *, page: PageContent, summary_markdown: str) -> str:
        now = datetime.now(UTC).isoformat()
        front_matter_lines = [
            "---",
            f"source: {page.final_url}",
            f"created_at: {now}",
            f"title: {page.title}",
            "---",
            "",
        ]

        body_lines: list[str] = []
        body_lines.append(f"# {page.title}")
        body_lines.append("")
        body_lines.append(summary_markdown.strip())
        body_lines.append("")

        return "\n".join(front_matter_lines + body_lines)
