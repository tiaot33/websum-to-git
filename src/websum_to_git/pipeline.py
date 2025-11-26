from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import AppConfig
from .github_client import GitHubPublisher, PublishResult
from .html_processor import PageContent, fetch_html, fetch_html_headless, parse_page
from .llm_client import LLMClient
from .markdown_chunker import split_markdown_into_chunks

# 近似控制每次请求的输入规模（按字符近似 token，主要面向中文场景）
_MAX_SUMMARY_INPUT_CHARS = 10_000

# 提示词文件路径
_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_prompt(name: str) -> str:
    """从 prompts 目录加载提示词文件。"""
    return (_PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


@dataclass
class SummaryResult:
    """LLM 总结结果，包含精炼标题和正文内容。"""
    ai_title: str
    content: str


def _parse_summary_result(raw_output: str) -> SummaryResult:
    """从 LLM 输出中解析第一行作为标题，其余作为内容。"""
    raw_output = raw_output.strip()
    lines = raw_output.split("\n", 1)
    ai_title = lines[0].strip()
    content = lines[1].strip() if len(lines) > 1 else ""
    return SummaryResult(ai_title=ai_title, content=content)


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

        summary_result = self._summarize_page(page)

        full_markdown = self._build_markdown(
            page=page,
            summary_result=summary_result,
        )

        return self._publisher.publish_markdown(
            content=full_markdown,
            source=page.final_url,
            title=page.title,
        )

    def _summarize_page(self, page: PageContent) -> SummaryResult:
        """将网页正文内容转换为适合 Obsidian 的 Markdown 摘要。"""
        text = page.markdown.strip()
        if not text:
            return SummaryResult(ai_title=page.title, content="（页面中未提取到正文内容）")

        # 内容较短时，直接一次性总结
        if len(text) <= _MAX_SUMMARY_INPUT_CHARS:
            user_content = (
                f"网页标题: {page.title}\n网页地址: {page.final_url}\n\n网页正文内容（已去除脚本等噪音标签）:\n{text}\n"
            )
            raw_output = self._llm.generate(
                system_prompt=_load_prompt("final_summary"),
                user_content=user_content,
            ).strip()
            return _parse_summary_result(raw_output)

        # 内容较长时，按 Markdown 块结构分 chunk，每个 chunk 独立生成完整总结后拼接
        chunks = split_markdown_into_chunks(text, _MAX_SUMMARY_INPUT_CHARS)

        chunk_results: list[SummaryResult] = []
        total = len(chunks)
        for idx, chunk in enumerate(chunks, start=1):
            chunk_user_content = (
                f"网页标题: {page.title}\n"
                f"网页地址: {page.final_url}\n"
                f"当前片段: {idx}/{total}\n\n"
                f"片段正文内容:\n{chunk}\n"
            )
            raw_output = self._llm.generate(
                system_prompt=_load_prompt("final_summary"),
                user_content=chunk_user_content,
            ).strip()
            if raw_output:
                chunk_results.append(_parse_summary_result(raw_output))

        if not chunk_results:
            return SummaryResult(ai_title=page.title, content="（无法生成总结）")

        # 使用第一个 chunk 的标题作为整体标题
        ai_title = chunk_results[0].ai_title

        # 拼接所有 chunk 的总结内容
        merged_content_parts: list[str] = []
        for idx, result in enumerate(chunk_results, start=1):
            if len(chunk_results) > 1:
                merged_content_parts.append(f"## 第 {idx} 部分\n\n{result.content}")
            else:
                merged_content_parts.append(result.content)

        merged_content = "\n\n---\n\n".join(merged_content_parts)
        return SummaryResult(ai_title=ai_title, content=merged_content)

    def _build_markdown(self, *, page: PageContent, summary_result: SummaryResult) -> str:
        now = datetime.now(UTC).isoformat()
        # YAML front matter 中保留原始网页标题
        front_matter_lines = [
            "---",
            f"source: {page.final_url}",
            f"created_at: {now}",
            f"title: {page.title}",
            "---",
            "",
        ]

        # 正文使用 AI 生成的精炼标题
        body_lines: list[str] = []
        body_lines.append(f"# {summary_result.ai_title}")
        body_lines.append("")
        body_lines.append(summary_result.content.strip())
        body_lines.append("")

        # 附加页面原文
        body_lines.append("---")
        body_lines.append("")
        body_lines.append("## 原文")
        body_lines.append("")
        body_lines.append(page.markdown.strip())
        body_lines.append("")

        return "\n".join(front_matter_lines + body_lines)
