from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .config import AppConfig
from .github_client import GitHubPublisher, PublishResult
from .html_processor import PageContent, fetch_html, fetch_html_headless, parse_page
from .llm_client import LLMClient
from .markdown_chunker import estimate_token_length, split_markdown_into_chunks

# 单次 LLM 请求最大输入 token 数
_MAX_INPUT_TOKENS = 10000

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
        self._fast_llm = LLMClient(config.fast_llm) if config.fast_llm else self._llm
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
        if estimate_token_length(text) <= _MAX_INPUT_TOKENS:
            user_content = (
                f"网页标题: {page.title}\n网页地址: {page.final_url}\n\n网页正文内容（已去除脚本等噪音标签）:\n{text}\n"
            )
            raw_output = self._llm.generate(
                system_prompt=_load_prompt("final_summary"),
                user_content=user_content,
            ).strip()
            return _parse_summary_result(raw_output)

        # 内容较长时，按 Markdown 块结构分 chunk，每个 chunk 独立生成完整总结后拼接
        chunks = split_markdown_into_chunks(text, _MAX_INPUT_TOKENS)

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

    def _generate_tags(self, title: str, summary_content: str) -> list[str]:
        """调用 AI 生成文章标签。"""
        user_content = f"文章标题: {title}\n\n文章摘要:\n{summary_content[:2000]}\n"
        raw_output = self._fast_llm.generate(
            system_prompt=_load_prompt("generate_tags"),
            user_content=user_content,
        ).strip()
        # 解析输出为标签列表，每行一个标签
        tags = [line.strip() for line in raw_output.split("\n") if line.strip()]
        return tags[:10]  # 最多返回 10 个标签

    def _is_chinese_text(self, text: str) -> bool:
        """检测文本是否主要为中文。"""
        # 统计中文字符数量
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        # 统计总字符数（排除空白和标点）
        total_chars = len(re.findall(r"[a-zA-Z\u4e00-\u9fff]", text))
        if total_chars == 0:
            return True  # 没有字母或中文时，默认认为是中文
        # 如果中文字符占比超过 30%，则认为是中文
        return chinese_chars / total_chars > 0.3

    def _translate_to_chinese(self, text: str) -> str:
        """将文本翻译为中文。"""
        # 对于超长文本，分块翻译
        if estimate_token_length(text) <= _MAX_INPUT_TOKENS:
            return self._fast_llm.generate(
                system_prompt=_load_prompt("translate_to_chinese"),
                user_content=text,
            ).strip()

        # 分块翻译
        chunks = split_markdown_into_chunks(text, _MAX_INPUT_TOKENS)
        translated_parts: list[str] = []
        for chunk in chunks:
            translated = self._fast_llm.generate(
                system_prompt=_load_prompt("translate_to_chinese"),
                user_content=chunk,
            ).strip()
            if translated:
                translated_parts.append(translated)
        return "\n\n".join(translated_parts)

    def _build_markdown(self, *, page: PageContent, summary_result: SummaryResult) -> str:
        now = datetime.now(UTC).isoformat()

        # 生成标签
        tags = self._generate_tags(summary_result.ai_title, summary_result.content)

        # YAML front matter 中保留原始网页标题
        front_matter_lines = [
            "---",
            f"source: {page.final_url}",
            f"created_at: {now}",
            f"title: {page.title}",
            "tags:",
        ]
        # tags 使用多行列表格式
        for tag in tags:
            front_matter_lines.append(f"  - {tag}")
        front_matter_lines.extend(["---", ""])

        # 正文使用 AI 生成的精炼标题
        body_lines: list[str] = []
        body_lines.append(f"# {summary_result.ai_title}")
        body_lines.append("")
        body_lines.append(summary_result.content.strip())
        body_lines.append("")

        # 附加页面原文
        original_markdown = page.markdown.strip()
        is_chinese = self._is_chinese_text(original_markdown)

        body_lines.append("---")
        body_lines.append("")

        if is_chinese:
            # 原文是中文，直接输出
            body_lines.append("## 原文")
            body_lines.append("")
            body_lines.append(original_markdown)
        else:
            # 原文非中文，先输出翻译，再保留原文
            translated = self._translate_to_chinese(original_markdown)
            body_lines.append("## 原文（中文翻译）")
            body_lines.append("")
            body_lines.append(translated)
            body_lines.append("")
            body_lines.append("---")
            body_lines.append("")
            body_lines.append("## 原文（原语言）")
            body_lines.append("")
            body_lines.append(original_markdown)

        body_lines.append("")

        return "\n".join(front_matter_lines + body_lines)
