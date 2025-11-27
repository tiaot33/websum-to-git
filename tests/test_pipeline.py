"""Pipeline 模块端到端测试。

测试覆盖：
- 完整的 URL 处理流程
- 短文本和长文本总结
- 中文检测和翻译
- Markdown 生成
- 标签生成
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast
from unittest.mock import MagicMock, patch

import pytest

from websum_to_git.github_client import PublishResult
from websum_to_git.html_processor import PageContent
from websum_to_git.pipeline import (
    HtmlToObsidianPipeline,
    SummaryResult,
    _load_prompt,
    _parse_summary_result,
)

if TYPE_CHECKING:
    from websum_to_git.config import AppConfig


def _get_llm_mock(pipeline: HtmlToObsidianPipeline) -> MagicMock:
    """返回绑定到 Pipeline 的 LLM MagicMock。"""
    return cast(MagicMock, pipeline._llm)


def _get_fast_llm_mock(pipeline: HtmlToObsidianPipeline) -> MagicMock:
    """返回绑定到 Pipeline 的 fast LLM MagicMock。"""
    return cast(MagicMock, pipeline._fast_llm)


def _get_publisher_mock(pipeline: HtmlToObsidianPipeline) -> MagicMock:
    """返回绑定到 Pipeline 的 GitHubPublisher MagicMock。"""
    return cast(MagicMock, pipeline._publisher)


# ============================================================
# _parse_summary_result 测试
# ============================================================


class TestParseSummaryResult:
    """测试 LLM 输出解析功能。"""

    def test_parse_title_and_content(self) -> None:
        """应正确解析标题和内容。"""
        raw = "精炼标题\n\n这是内容部分"
        result = _parse_summary_result(raw)

        assert result.ai_title == "精炼标题"
        assert result.content == "这是内容部分"

    def test_parse_multiline_content(self) -> None:
        """多行内容应完整保留。"""
        raw = "标题\n第一行\n第二行\n第三行"
        result = _parse_summary_result(raw)

        assert result.ai_title == "标题"
        assert "第一行" in result.content
        assert "第三行" in result.content

    def test_parse_title_only(self) -> None:
        """只有标题时，内容应为空。"""
        raw = "只有标题"
        result = _parse_summary_result(raw)

        assert result.ai_title == "只有标题"
        assert result.content == ""

    def test_parse_strips_whitespace(self) -> None:
        """应去除首尾空白。"""
        raw = "  标题  \n  内容  "
        result = _parse_summary_result(raw)

        assert result.ai_title == "标题"
        assert result.content == "内容"

    def test_parse_empty_string(self) -> None:
        """空字符串应返回空结果。"""
        result = _parse_summary_result("")

        assert result.ai_title == ""
        assert result.content == ""


# ============================================================
# _load_prompt 测试
# ============================================================


class TestLoadPrompt:
    """测试提示词加载功能。"""

    def test_load_final_summary_prompt(self) -> None:
        """应能加载 final_summary 提示词。"""
        prompt = _load_prompt("final_summary")

        assert len(prompt) > 0
        assert isinstance(prompt, str)

    def test_load_generate_tags_prompt(self) -> None:
        """应能加载 generate_tags 提示词。"""
        prompt = _load_prompt("generate_tags")

        assert len(prompt) > 0
        assert isinstance(prompt, str)

    def test_load_translate_prompt(self) -> None:
        """应能加载 translate_to_chinese 提示词。"""
        prompt = _load_prompt("translate_to_chinese")

        assert len(prompt) > 0
        assert isinstance(prompt, str)

    def test_load_nonexistent_prompt_raises(self) -> None:
        """加载不存在的提示词应抛出异常。"""
        with pytest.raises(FileNotFoundError):
            _load_prompt("nonexistent_prompt")


# ============================================================
# HtmlToObsidianPipeline 测试
# ============================================================


class TestHtmlToObsidianPipeline:
    """测试 HTML 到 Obsidian 的转换管道。"""

    @pytest.fixture
    def mock_pipeline(self, sample_app_config: AppConfig) -> HtmlToObsidianPipeline:
        """创建带 mock 依赖的 Pipeline。"""
        with (
            patch("websum_to_git.pipeline.LLMClient") as mock_llm_cls,
            patch("websum_to_git.pipeline.GitHubPublisher") as mock_publisher_cls,
        ):
            mock_llm = MagicMock()
            mock_llm.generate.return_value = "精炼标题\n\n摘要内容..."
            mock_llm_cls.return_value = mock_llm

            mock_publisher = MagicMock()
            mock_publisher.publish_markdown.return_value = PublishResult(
                file_path="notes/test.md",
                commit_hash="abc123",
            )
            mock_publisher_cls.return_value = mock_publisher

            pipeline = HtmlToObsidianPipeline(sample_app_config)
            pipeline._llm = mock_llm
            pipeline._fast_llm = mock_llm
            pipeline._publisher = mock_publisher

            return pipeline

    # --------------------------------------------------------
    # process_url 端到端测试
    # --------------------------------------------------------

    def test_process_url_full_flow(
        self, mock_pipeline: HtmlToObsidianPipeline, sample_html: str
    ) -> None:
        """完整的 URL 处理流程。"""
        with patch("websum_to_git.pipeline.fetch_html") as mock_fetch:
            mock_fetch.return_value = (sample_html, "https://example.com/python")

            with patch("websum_to_git.pipeline.parse_page") as mock_parse:
                mock_parse.return_value = PageContent(
                    url="https://example.com/python",
                    final_url="https://example.com/python",
                    title="Python 入门",
                    text="Python 是一种编程语言...",
                    markdown="# Python 入门\n\nPython 是一种编程语言...",
                    raw_html=sample_html,
                    article_html="<article>...</article>",
                )

                # 模拟 LLM 返回
                _get_llm_mock(mock_pipeline).generate.return_value = (
                    "Python 入门指南\n\n> Python 是现代编程的基础...\n\n## 核心概念"
                )
                _get_fast_llm_mock(mock_pipeline).generate.return_value = (
                    "Python\nProgramming\nTutorial"
                )

                result = mock_pipeline.process_url("https://example.com/python")

                assert result.file_path == "notes/test.md"
                assert result.commit_hash == "abc123"

                # 验证 publish_markdown 被调用
                _get_publisher_mock(mock_pipeline).publish_markdown.assert_called_once()

    def test_process_url_with_headless_mode(
        self, sample_app_config: AppConfig, sample_html: str
    ) -> None:
        """使用 headless 模式抓取。"""
        sample_app_config.http.fetch_mode = "headless"

        with (
            patch("websum_to_git.pipeline.LLMClient"),
            patch("websum_to_git.pipeline.GitHubPublisher") as mock_publisher_cls,
            patch("websum_to_git.pipeline.fetch_html_headless") as mock_fetch,
            patch("websum_to_git.pipeline.parse_page") as mock_parse,
        ):
            mock_publisher = MagicMock()
            mock_publisher.publish_markdown.return_value = PublishResult(
                file_path="notes/test.md", commit_hash="abc123"
            )
            mock_publisher_cls.return_value = mock_publisher

            mock_fetch.return_value = (sample_html, "https://example.com")
            mock_parse.return_value = PageContent(
                url="https://example.com",
                final_url="https://example.com",
                title="Test",
                text="Test content",
                markdown="# Test\n\nTest content",
                raw_html=sample_html,
                article_html="<article>...</article>",
            )

            pipeline = HtmlToObsidianPipeline(sample_app_config)
            _get_llm_mock(pipeline).generate.return_value = "标题\n内容"

            pipeline.process_url("https://example.com")

            mock_fetch.assert_called_once()

    # --------------------------------------------------------
    # _summarize_page 测试
    # --------------------------------------------------------

    def test_summarize_short_text(
        self, mock_pipeline: HtmlToObsidianPipeline, sample_page_content: PageContent
    ) -> None:
        """短文本应一次性总结。"""
        _get_llm_mock(mock_pipeline).generate.return_value = "精炼标题\n\n摘要内容..."

        result = mock_pipeline._summarize_page(sample_page_content)

        assert result.ai_title == "精炼标题"
        assert "摘要" in result.content

        # 验证只调用了一次 LLM
        assert _get_llm_mock(mock_pipeline).generate.call_count == 1

    def test_summarize_empty_markdown(
        self, mock_pipeline: HtmlToObsidianPipeline
    ) -> None:
        """空内容应返回默认提示。"""
        page = PageContent(
            url="https://example.com",
            final_url="https://example.com",
            title="Empty Page",
            text="",
            markdown="",
            raw_html="<html></html>",
            article_html="",
        )

        result = mock_pipeline._summarize_page(page)

        assert result.ai_title == "Empty Page"
        assert "未提取到" in result.content

    def test_summarize_long_text_chunked(
        self, mock_pipeline: HtmlToObsidianPipeline
    ) -> None:
        """长文本应分块总结。"""
        # 创建超长内容
        long_markdown = "# 长文章\n\n" + ("这是很长的内容。" * 5000)
        page = PageContent(
            url="https://example.com",
            final_url="https://example.com",
            title="Long Article",
            text="长内容...",
            markdown=long_markdown,
            raw_html="<html>...</html>",
            article_html="<article>...</article>",
        )

        # 模拟多次 LLM 调用
        _get_llm_mock(mock_pipeline).generate.side_effect = [
            "第一部分标题\n\n第一部分内容",
            "第二部分标题\n\n第二部分内容",
            "第三部分标题\n\n第三部分内容",
        ] * 10  # 确保足够多的响应

        result = mock_pipeline._summarize_page(page)

        # 应使用第一个 chunk 的标题
        assert result.ai_title == "第一部分标题"
        # 应包含多个部分
        assert "第 1 部分" in result.content or "第一部分" in result.content

    # --------------------------------------------------------
    # _generate_tags 测试
    # --------------------------------------------------------

    def test_generate_tags(self, mock_pipeline: HtmlToObsidianPipeline) -> None:
        """应正确生成标签列表。"""
        _get_fast_llm_mock(mock_pipeline).generate.return_value = "Python\nProgramming\nTutorial"

        tags = mock_pipeline._generate_tags("Python 入门", "Python 编程教程...")

        assert len(tags) == 3
        assert "Python" in tags
        assert "Programming" in tags

    def test_generate_tags_max_10(self, mock_pipeline: HtmlToObsidianPipeline) -> None:
        """标签最多返回 10 个。"""
        _get_fast_llm_mock(mock_pipeline).generate.return_value = "\n".join([f"Tag{i}" for i in range(20)])

        tags = mock_pipeline._generate_tags("Title", "Content...")

        assert len(tags) <= 10

    def test_generate_tags_empty_lines_filtered(
        self, mock_pipeline: HtmlToObsidianPipeline
    ) -> None:
        """空行应被过滤。"""
        _get_fast_llm_mock(mock_pipeline).generate.return_value = "Tag1\n\n\nTag2\n  \nTag3"

        tags = mock_pipeline._generate_tags("Title", "Content...")

        assert len(tags) == 3

    # --------------------------------------------------------
    # _is_chinese_text 测试
    # --------------------------------------------------------

    def test_is_chinese_text_chinese(
        self, mock_pipeline: HtmlToObsidianPipeline
    ) -> None:
        """中文文本应返回 True。"""
        assert mock_pipeline._is_chinese_text("这是一段中文文本，包含一些内容。")

    def test_is_chinese_text_english(
        self, mock_pipeline: HtmlToObsidianPipeline
    ) -> None:
        """英文文本应返回 False。"""
        assert not mock_pipeline._is_chinese_text("This is an English text with no Chinese.")

    def test_is_chinese_text_mixed_mostly_chinese(
        self, mock_pipeline: HtmlToObsidianPipeline
    ) -> None:
        """中英混合但中文为主应返回 True。"""
        text = "这是一段中文文本，包含少量 English 单词。"
        assert mock_pipeline._is_chinese_text(text)

    def test_is_chinese_text_mixed_mostly_english(
        self, mock_pipeline: HtmlToObsidianPipeline
    ) -> None:
        """中英混合但英文为主应返回 False。"""
        text = "This is mostly English text with just a few 中文 characters."
        assert not mock_pipeline._is_chinese_text(text)

    def test_is_chinese_text_empty(
        self, mock_pipeline: HtmlToObsidianPipeline
    ) -> None:
        """空文本或纯符号默认为中文。"""
        assert mock_pipeline._is_chinese_text("")
        assert mock_pipeline._is_chinese_text("123 !@# $%^")

    # --------------------------------------------------------
    # _translate_to_chinese 测试
    # --------------------------------------------------------

    def test_translate_to_chinese(
        self, mock_pipeline: HtmlToObsidianPipeline
    ) -> None:
        """应调用 LLM 进行翻译。"""
        fast_llm = _get_fast_llm_mock(mock_pipeline)
        fast_llm.generate.return_value = "这是翻译后的中文内容"

        result = mock_pipeline._translate_to_chinese("This is English content")

        assert result == "这是翻译后的中文内容"
        fast_llm.generate.assert_called()

    def test_translate_long_text_chunked(
        self, mock_pipeline: HtmlToObsidianPipeline
    ) -> None:
        """长文本翻译应分块处理。"""
        long_text = "This is long content. " * 5000

        _get_fast_llm_mock(mock_pipeline).generate.side_effect = [
            "第一部分翻译",
            "第二部分翻译",
        ] * 10

        result = mock_pipeline._translate_to_chinese(long_text)

        # 结果应包含多次翻译的拼接
        assert "翻译" in result

    # --------------------------------------------------------
    # _build_markdown 测试
    # --------------------------------------------------------

    def test_build_markdown_chinese_content(
        self, mock_pipeline: HtmlToObsidianPipeline, sample_page_content: PageContent
    ) -> None:
        """中文内容构建 Markdown。"""
        summary = SummaryResult(ai_title="精炼标题", content="摘要内容...")

        # Mock 标签生成
        _get_fast_llm_mock(mock_pipeline).generate.return_value = "Python\nTutorial"

        result = mock_pipeline._build_markdown(page=sample_page_content, summary_result=summary)

        # 应包含 YAML front matter
        assert result.startswith("---")
        assert "source:" in result
        assert "created_at:" in result
        assert "title:" in result
        assert "tags:" in result

        # 应包含 AI 标题
        assert "# 精炼标题" in result

        # 应包含原文（中文直接显示）
        assert "## 原文" in result

    def test_build_markdown_english_content(
        self, mock_pipeline: HtmlToObsidianPipeline, sample_english_page_content: PageContent
    ) -> None:
        """英文内容构建 Markdown（需翻译）。"""
        summary = SummaryResult(ai_title="Refined Title", content="Summary...")

        # Mock 标签生成和翻译
        fast_mock = _get_fast_llm_mock(mock_pipeline)
        fast_mock.generate.side_effect = [
            "Python\nTutorial",  # 标签
            "翻译后的中文内容",  # 翻译
        ]

        result = mock_pipeline._build_markdown(
            page=sample_english_page_content, summary_result=summary
        )

        # 应包含翻译版本
        assert "## 原文（中文翻译）" in result
        # 应保留原语言版本
        assert "## 原文（原语言）" in result

    def test_build_markdown_front_matter_format(
        self, mock_pipeline: HtmlToObsidianPipeline, sample_page_content: PageContent
    ) -> None:
        """YAML front matter 格式正确。"""
        summary = SummaryResult(ai_title="标题", content="内容")
        _get_fast_llm_mock(mock_pipeline).generate.return_value = "Tag1\nTag2"

        result = mock_pipeline._build_markdown(page=sample_page_content, summary_result=summary)

        lines = result.split("\n")
        assert lines[0] == "---"

        # 找到第二个 ---
        end_idx = None
        for i, line in enumerate(lines[1:], 1):
            if line == "---":
                end_idx = i
                break

        assert end_idx is not None
        front_matter = "\n".join(lines[1:end_idx])

        assert "source:" in front_matter
        assert "tags:" in front_matter


# ============================================================
# SummaryResult 数据结构测试
# ============================================================


class TestSummaryResult:
    """测试 SummaryResult 数据类。"""

    def test_creation(self) -> None:
        """创建 SummaryResult 对象。"""
        result = SummaryResult(ai_title="标题", content="内容")

        assert result.ai_title == "标题"
        assert result.content == "内容"

    def test_empty_values(self) -> None:
        """允许空值。"""
        result = SummaryResult(ai_title="", content="")

        assert result.ai_title == ""
        assert result.content == ""
