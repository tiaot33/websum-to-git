"""HTML 处理器模块测试。

测试覆盖：
- HTML 抓取功能 (requests 模式)
- HTML 解析和正文提取
- Markdown 转换
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import requests
import responses

from websum_to_git.html_processor import (
    HeadlessFetchError,
    PageContent,
    fetch_html,
    parse_page,
)

if TYPE_CHECKING:
    pass


# ============================================================
# fetch_html 测试
# ============================================================


class TestFetchHtml:
    """测试 HTML 抓取功能。"""

    @responses.activate
    def test_fetch_html_success(self) -> None:
        """成功抓取 HTML 页面。"""
        url = "https://example.com/article"
        html_content = "<html><body><h1>Test</h1></body></html>"

        responses.add(responses.GET, url, body=html_content, status=200)

        html, final_url = fetch_html(url)

        assert html == html_content
        assert final_url == url

    @responses.activate
    def test_fetch_html_with_redirect(self) -> None:
        """处理重定向后返回最终 URL。"""
        original_url = "https://example.com/old"
        redirect_url = "https://example.com/new"
        html_content = "<html><body><h1>Test</h1></body></html>"

        responses.add(
            responses.GET,
            original_url,
            status=301,
            headers={"Location": redirect_url},
        )
        responses.add(responses.GET, redirect_url, body=html_content, status=200)

        html, final_url = fetch_html(original_url)

        assert html == html_content
        assert final_url == redirect_url

    @responses.activate
    def test_fetch_html_404_error(self) -> None:
        """404 错误应抛出异常。"""
        url = "https://example.com/notfound"

        responses.add(responses.GET, url, status=404)

        with pytest.raises(requests.HTTPError):
            fetch_html(url)

    @responses.activate
    def test_fetch_html_timeout(self) -> None:
        """超时应抛出异常。"""
        import requests

        url = "https://example.com/slow"

        responses.add(responses.GET, url, body=requests.exceptions.Timeout())

        with pytest.raises(requests.exceptions.Timeout):
            fetch_html(url, timeout=1)

    @responses.activate
    def test_fetch_html_connection_error(self) -> None:
        """连接错误应抛出异常。"""
        import requests

        url = "https://example.com/offline"

        responses.add(responses.GET, url, body=requests.exceptions.ConnectionError())

        with pytest.raises(requests.exceptions.ConnectionError):
            fetch_html(url)


# ============================================================
# parse_page 测试
# ============================================================


class TestParsePage:
    """测试页面解析功能。"""

    def test_parse_page_basic(self, sample_html: str) -> None:
        """基本页面解析。"""
        url = "https://example.com/python-guide"

        result = parse_page(url, sample_html)

        assert isinstance(result, PageContent)
        assert result.url == url
        assert result.final_url == url
        assert "Python" in result.title
        assert "Python" in result.text
        assert "Python" in result.markdown
        assert result.raw_html == sample_html
        assert len(result.article_html) > 0

    def test_parse_page_with_final_url(self, sample_html: str) -> None:
        """解析时指定最终 URL。"""
        original_url = "https://example.com/old"
        final_url = "https://example.com/new"

        result = parse_page(original_url, sample_html, final_url=final_url)

        assert result.url == original_url
        assert result.final_url == final_url

    def test_parse_page_extracts_title(self, sample_html: str) -> None:
        """应正确提取页面标题。"""
        result = parse_page("https://example.com", sample_html)

        assert "Python" in result.title
        assert "编程" in result.title or "入门" in result.title

    def test_parse_page_removes_scripts(self, sample_html: str) -> None:
        """解析结果应移除 script 标签。"""
        result = parse_page("https://example.com", sample_html)

        assert "console.log" not in result.text
        assert "<script>" not in result.markdown

    def test_parse_page_converts_to_markdown(self, sample_html: str) -> None:
        """应将 HTML 转换为 Markdown 格式。"""
        result = parse_page("https://example.com", sample_html)

        # 应包含 Markdown 标题格式
        assert "#" in result.markdown
        # 应包含列表
        assert "-" in result.markdown or "*" in result.markdown

    def test_parse_page_preserves_code_blocks(self) -> None:
        """代码块应被保留。"""
        html = """
        <html>
        <head><title>Code Example</title></head>
        <body>
        <article>
            <h1>Code Example</h1>
            <pre><code>def hello():
    print("Hello")</code></pre>
        </article>
        </body>
        </html>
        """
        result = parse_page("https://example.com", html)

        assert "def hello" in result.markdown or "print" in result.markdown

    def test_parse_page_handles_empty_html(self) -> None:
        """空 HTML 应返回空内容。"""
        html = "<html><head><title></title></head><body></body></html>"

        result = parse_page("https://example.com", html)

        assert result.title == "" or result.title is not None  # 标题可能为空
        assert result.text is not None

    def test_parse_page_handles_minimal_html(self) -> None:
        """最小 HTML 结构应能解析。"""
        html = "<html><body><p>Hello World</p></body></html>"

        result = parse_page("https://example.com", html)

        assert "Hello" in result.text

    def test_parse_page_extracts_lists(self, sample_html: str) -> None:
        """应正确提取列表内容。"""
        result = parse_page("https://example.com", sample_html)

        assert "int" in result.text or "整数" in result.text
        assert "float" in result.text or "浮点" in result.text

    def test_parse_page_english_content(self, sample_english_html: str) -> None:
        """应正确解析英文内容。"""
        result = parse_page("https://example.com", sample_english_html)

        assert "Python" in result.title
        assert "Python" in result.text
        assert "syntax" in result.text.lower() or "indentation" in result.text.lower()


# ============================================================
# PageContent 数据结构测试
# ============================================================


class TestPageContent:
    """测试 PageContent 数据类。"""

    def test_page_content_creation(self) -> None:
        """创建 PageContent 对象。"""
        content = PageContent(
            url="https://example.com",
            final_url="https://example.com",
            title="Test Title",
            text="Test text content",
            markdown="# Test\n\nContent",
            raw_html="<html></html>",
            article_html="<article></article>",
        )

        assert content.url == "https://example.com"
        assert content.title == "Test Title"
        assert content.text == "Test text content"

    def test_page_content_fields_accessible(self, sample_page_content: PageContent) -> None:
        """PageContent 所有字段应可访问。"""
        assert sample_page_content.url is not None
        assert sample_page_content.final_url is not None
        assert sample_page_content.title is not None
        assert sample_page_content.text is not None
        assert sample_page_content.markdown is not None
        assert sample_page_content.raw_html is not None
        assert sample_page_content.article_html is not None


# ============================================================
# HeadlessFetchError 测试
# ============================================================


class TestHeadlessFetchError:
    """测试 Headless 抓取异常。"""

    def test_error_is_runtime_error(self) -> None:
        """HeadlessFetchError 应继承自 RuntimeError。"""
        error = HeadlessFetchError("Test error")
        assert isinstance(error, RuntimeError)

    def test_error_message(self) -> None:
        """异常消息应正确传递。"""
        message = "Playwright 超时"
        error = HeadlessFetchError(message)
        assert str(error) == message

    def test_error_can_be_raised(self) -> None:
        """异常应能被正确抛出和捕获。"""
        with pytest.raises(HeadlessFetchError) as exc_info:
            raise HeadlessFetchError("测试异常")

        assert "测试异常" in str(exc_info.value)
