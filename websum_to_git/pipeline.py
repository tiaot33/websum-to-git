from __future__ import annotations

from datetime import datetime, timezone

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


def _split_into_paragraphs(text: str) -> list[str]:
    """按空行切分为段落，保持实现简单且可读。"""
    lines = text.splitlines()
    paragraphs: list[str] = []
    current: list[str] = []

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        current.append(line)

    if current:
        paragraphs.append(" ".join(current))

    # 如果源文本几乎没有空行，退化为整体一个段落
    return paragraphs or [text.strip()]


def _build_chunks(paragraphs: list[str], max_chars: int) -> list[str]:
    """按段落拼接为多个 chunk，每个 chunk 的长度不超过 max_chars。"""
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # 如果单段本身就超过 max_chars，直接作为一个独立 chunk
        if len(para) >= max_chars:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            chunks.append(para[:max_chars])
            continue

        if current_len + len(para) + 2 > max_chars and current:
            chunks.append("\n\n".join(current))
            current = [para]
            current_len = len(para)
        else:
            current.append(para)
            current_len += len(para) + 2

    if current:
        chunks.append("\n\n".join(current))

    return chunks


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
            source_url=page.final_url,
            title=page.title,
        )

    def _summarize_page(self, page: PageContent) -> str:
        """将网页正文内容转换为适合 Obsidian 的 Markdown 摘要。"""
        text = page.text.strip()
        if not text:
            return "（页面中未提取到正文内容）"

        # 内容较短时，直接一次性总结
        if len(text) <= _MAX_SUMMARY_INPUT_CHARS:
            user_content = (
                f"网页标题: {page.title}\n"
                f"网页地址: {page.final_url}\n\n"
                f"网页正文内容（已去除脚本等噪音标签）:\n{text}\n"
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
                chunk_summaries.append(
                    f"片段 {idx}/{total} 的要点摘要：\n{chunk_summary}"
                )

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
        now = datetime.now(timezone.utc).isoformat()
        front_matter_lines = [
            "---",
            f"source_url: {page.final_url}",
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

        if page.image_urls:
            body_lines.append("## Images")
            body_lines.append("")
            for img in page.image_urls:
                body_lines.append(f"![]({img})")
            body_lines.append("")

        return "\n".join(front_matter_lines + body_lines)
