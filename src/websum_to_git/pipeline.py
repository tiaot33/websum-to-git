from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import AppConfig
from .github_client import GitHubPublisher
from .html_processor import PageContent, fetch_html, fetch_html_headless, parse_page
from .llm_client import LLMClient
from .markdown_chunker import estimate_token_length, split_markdown_into_chunks
from .telegraph_client import TelegraphClient

logger = logging.getLogger(__name__)

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


@dataclass
class PipelineResult:
    """完整处理流程的结果。"""

    file_path: str  # GitHub 文件路径
    commit_hash: str | None  # Git commit hash
    github_url: str | None  # GitHub 文件 Web 链接
    telegraph_url: str | None  # Telegraph 预览链接


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
        self._telegraph = TelegraphClient()

    def process_url(self, url: str) -> PipelineResult:
        logger.info("开始处理 URL: %s", url)

        # 步骤 1: 抓取网页
        logger.info("步骤 1/5: 抓取网页内容 (模式: %s)", self._config.http.fetch_mode)
        if self._config.http.fetch_mode == "headless":
            html, final_url = fetch_html_headless(url)
        else:
            html, final_url = fetch_html(
                url,
                verify=self._config.http.verify_ssl,
            )
        logger.info("抓取完成, HTML 长度: %d, 最终 URL: %s", len(html), final_url)

        # 步骤 2: 解析页面
        logger.info("步骤 2/5: 解析页面内容")
        page = parse_page(url=url, html=html, final_url=final_url)
        logger.info("解析完成, 标题: %s, Markdown 长度: %d", page.title, len(page.markdown))

        # 步骤 3: LLM 总结
        logger.info("步骤 3/5: 调用 LLM 生成摘要")
        summary_result = self._summarize_page(page)
        logger.info("摘要生成完成, AI 标题: %s", summary_result.ai_title)

        # 步骤 4: 构建 Markdown 并发布到 GitHub
        logger.info("步骤 4/5: 构建 Markdown 并发布到 GitHub")
        full_markdown = self._build_markdown(
            page=page,
            summary_result=summary_result,
        )
        logger.info("Markdown 构建完成, 总长度: %d", len(full_markdown))

        github_result = self._publisher.publish_markdown(
            content=full_markdown,
            source=page.final_url,
            title=summary_result.ai_title,
        )
        logger.info("GitHub 发布成功, 文件路径: %s, commit: %s", github_result.file_path, github_result.commit_hash)

        # 步骤 5: 上传到 Telegraph
        logger.info("步骤 5/5: 上传到 Telegraph")
        telegraph_url: str | None = None
        try:
            telegraph_result = self._telegraph.publish_markdown(
                title=summary_result.ai_title,
                content=full_markdown,
            )
            telegraph_url = telegraph_result.url
            logger.info("Telegraph 发布成功: %s", telegraph_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Telegraph 发布失败 (非致命): %s", exc)

        return PipelineResult(
            file_path=github_result.file_path,
            commit_hash=github_result.commit_hash,
            github_url=github_result.web_url,
            telegraph_url=telegraph_url,
        )

    def _summarize_page(self, page: PageContent) -> SummaryResult:
        """将网页正文内容转换为适合 Obsidian 的 Markdown 摘要。"""
        text = page.markdown.strip()
        if not text:
            logger.warning("页面未提取到正文内容, 使用原始标题")
            return SummaryResult(ai_title=page.title, content="（页面中未提取到正文内容）")

        max_tokens = self._config.llm.max_input_tokens
        token_count = estimate_token_length(text)
        logger.info("正文 token 估算: %d (阈值: %d)", token_count, max_tokens)

        # 内容较短时，直接一次性总结
        if token_count <= max_tokens:
            logger.info("内容较短, 执行单次总结")
            user_content = (
                f"网页标题: {page.title}\n网页地址: {page.final_url}\n\n网页正文内容（已去除脚本等噪音标签）:\n{text}\n"
            )
            raw_output = self._llm.generate(
                system_prompt=_load_prompt("final_summary"),
                user_content=user_content,
            ).strip()
            return _parse_summary_result(raw_output)

        # 内容较长时，按 Markdown 块结构分 chunk，每个 chunk 独立生成完整总结后拼接
        chunks = split_markdown_into_chunks(text, max_tokens)
        total = len(chunks)
        logger.info("内容较长, 分割为 %d 个片段进行总结", total)

        chunk_results: list[SummaryResult] = []
        for idx, chunk in enumerate(chunks, start=1):
            logger.info("处理片段 %d/%d, 长度: %d", idx, total, len(chunk))
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
            logger.warning("所有片段总结失败, 返回默认结果")
            return SummaryResult(ai_title=page.title, content="（无法生成总结）")

        logger.info("成功总结 %d 个片段", len(chunk_results))

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
        logger.info("生成标签, 标题: %s", title)
        user_content = f"文章标题: {title}\n\n文章摘要:\n{summary_content[:2000]}\n"
        raw_output = self._fast_llm.generate(
            system_prompt=_load_prompt("generate_tags"),
            user_content=user_content,
        ).strip()
        # 解析输出为标签列表，每行一个标签，并去除标签内的空格
        tags = [line.strip().replace(" ", "") for line in raw_output.split("\n") if line.strip()]
        logger.info("生成标签完成, 数量: %d, 标签: %s", len(tags), tags)
        return tags  # 最多返回 10 个标签

    def _is_chinese_text(self, text: str) -> bool:
        """检测文本是否主要为中文。"""
        # 统计中文字符数量
        chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
        # 统计总字符数（排除空白和标点）
        total_chars = len(re.findall(r"[a-zA-Z\u4e00-\u9fff]", text))
        # 如果中文字符绝对数量超过 45，则认为是中文（避免少量英文混入时误判为需翻译）
        if chinese_chars > 45:
            return True
        if total_chars == 0:
            return True  # 没有字母或中文时，默认认为是中文
        # 如果中文字符占比超过 30%，则认为是中文
        return chinese_chars / total_chars > 0.3

    def _translate_to_chinese(self, text: str) -> str:
        """将文本翻译为中文。"""
        # 翻译使用 fast_llm 的配置，如果未配置则使用主 llm 的配置
        max_tokens = (
            self._config.fast_llm.max_input_tokens
            if self._config.fast_llm
            else self._config.llm.max_input_tokens
        )
        token_count = estimate_token_length(text)
        logger.info("翻译文本, 长度: %d, token 估算: %d", len(text), token_count)

        # 对于超长文本，分块翻译
        if token_count <= max_tokens:
            logger.info("文本较短, 执行单次翻译")
            return self._fast_llm.generate(
                system_prompt=_load_prompt("translate_to_chinese"),
                user_content=text,
            ).strip()

        # 分块翻译
        chunks = split_markdown_into_chunks(text, max_tokens)
        logger.info("文本较长, 分割为 %d 个片段进行翻译", len(chunks))

        translated_parts: list[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            logger.info("翻译片段 %d/%d, 长度: %d", idx, len(chunks), len(chunk))
            translated = self._fast_llm.generate(
                system_prompt=_load_prompt("translate_to_chinese"),
                user_content=chunk,
            ).strip()
            if translated:
                translated_parts.append(translated)

        logger.info("翻译完成, 成功片段数: %d", len(translated_parts))
        return "\n\n".join(translated_parts)

    def _build_markdown(self, *, page: PageContent, summary_result: SummaryResult) -> str:
        logger.info("构建最终 Markdown 文档")
        now = datetime.now().strftime("%Y.%m.%d. %H:%M")

        # 生成标签
        tags = self._generate_tags(summary_result.ai_title, summary_result.content)

        # YAML front matter 中保留原始网页标题
        front_matter_lines = [
            "---",
            f"source: {page.final_url}",
            f"created_at: {now}",
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
        logger.info("原文语言检测: %s", "中文" if is_chinese else "非中文")

        body_lines.append("---")
        body_lines.append("")

        if is_chinese:
            # 原文是中文，直接输出
            logger.info("原文为中文, 直接附加")
            body_lines.append("# 原文")
            body_lines.append("")
            body_lines.append(original_markdown)
        else:
            # 原文非中文，先输出翻译，再保留原文
            logger.info("原文非中文, 执行翻译")
            translated = self._translate_to_chinese(original_markdown)
            body_lines.append("# 原文（中文翻译）")
            body_lines.append("")
            body_lines.append(translated)
            body_lines.append("")
            body_lines.append("---")
            body_lines.append("")
            body_lines.append("# 原文（原语言）")
            body_lines.append("")
            body_lines.append(original_markdown)

        body_lines.append("")

        logger.info("Markdown 文档构建完成")
        return "\n".join(front_matter_lines + body_lines)
