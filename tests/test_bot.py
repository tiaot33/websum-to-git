"""Telegram Bot 模块测试。

测试覆盖：
- URL 提取功能
- 消息处理逻辑
- /start 命令处理
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from websum_to_git.bot import TelegramBotApp, extract_first_url

if TYPE_CHECKING:
    from websum_to_git.config import AppConfig


# ============================================================
# URL 提取测试
# ============================================================


class TestExtractFirstUrl:
    """测试 URL 提取功能。"""

    def test_extract_http_url(self) -> None:
        """应正确提取 http:// 开头的 URL。"""
        text = "请看这篇文章 http://example.com/article"
        assert extract_first_url(text) == "http://example.com/article"

    def test_extract_https_url(self) -> None:
        """应正确提取 https:// 开头的 URL��"""
        text = "请看这篇文章 https://example.com/article"
        assert extract_first_url(text) == "https://example.com/article"

    def test_extract_first_of_multiple_urls(self) -> None:
        """存在多个 URL 时，应提取第一个。"""
        text = "第一个 https://first.com 第二个 https://second.com"
        assert extract_first_url(text) == "https://first.com"

    def test_extract_url_with_query_params(self) -> None:
        """应正确提取带查询参数的 URL。"""
        text = "链接 https://example.com/article?id=123&lang=zh"
        assert extract_first_url(text) == "https://example.com/article?id=123&lang=zh"

    def test_extract_url_with_fragment(self) -> None:
        """应正确提取带锚点的 URL。"""
        text = "链接 https://example.com/article#section1"
        assert extract_first_url(text) == "https://example.com/article#section1"

    def test_extract_url_with_path(self) -> None:
        """应正确提取带路径的 URL。"""
        text = "链接 https://example.com/path/to/article"
        assert extract_first_url(text) == "https://example.com/path/to/article"

    def test_no_url_returns_none(self) -> None:
        """文本中无 URL 时返回 None。"""
        text = "这是一段普通文本，没有链接"
        assert extract_first_url(text) is None

    def test_empty_string_returns_none(self) -> None:
        """空字符串返回 None。"""
        assert extract_first_url("") is None

    def test_url_at_start(self) -> None:
        """URL 在文本开头时应正确提取。"""
        text = "https://example.com/article 这是描述"
        assert extract_first_url(text) == "https://example.com/article"

    def test_url_at_end(self) -> None:
        """URL 在文本结尾时应正确提取。"""
        text = "描述在前面 https://example.com/article"
        assert extract_first_url(text) == "https://example.com/article"

    def test_url_case_insensitive(self) -> None:
        """URL 协议部分应不区分大小写。"""
        text = "链接 HTTPS://EXAMPLE.COM/article"
        result = extract_first_url(text)
        assert result is not None
        assert result.lower().startswith("https://")


# ============================================================
# TelegramBotApp 测试
# ============================================================


class TestTelegramBotApp:
    """测试 Telegram Bot 应用类。"""

    @pytest.fixture
    def bot_app(self, sample_app_config: AppConfig) -> TelegramBotApp:
        """创建测试用 Bot 应用实例。"""
        with patch("websum_to_git.bot.HtmlToObsidianPipeline"):
            return TelegramBotApp(sample_app_config)

    @pytest.mark.asyncio
    async def test_start_command(
        self, bot_app: TelegramBotApp, mock_telegram_update: MagicMock, mock_telegram_context: MagicMock
    ) -> None:
        """/start 命令应返回欢迎消息。"""
        await bot_app.start(mock_telegram_update, mock_telegram_context)

        mock_telegram_update.message.reply_text.assert_called_once()
        call_args = mock_telegram_update.message.reply_text.call_args[0][0]
        assert "请发送" in call_args
        assert "HTML" in call_args or "网页" in call_args

    @pytest.mark.asyncio
    async def test_handle_message_with_url(
        self, bot_app: TelegramBotApp, mock_telegram_update: MagicMock, mock_telegram_context: MagicMock
    ) -> None:
        """包含 URL 的消息应触发处理流程。"""
        mock_telegram_update.message.text = "请总结 https://example.com/article"

        with patch.object(bot_app, "_pipeline") as mock_pipeline:
            mock_result = MagicMock()
            mock_result.file_path = "notes/test.md"
            mock_result.commit_hash = "abc123"
            mock_pipeline.process_url.return_value = mock_result

            await bot_app.handle_message(mock_telegram_update, mock_telegram_context)

            # 应该调用 pipeline.process_url
            mock_pipeline.process_url.assert_called_once_with("https://example.com/article")

            # 应该回复成功消息
            assert mock_telegram_update.message.reply_text.call_count >= 2
            final_call = mock_telegram_update.message.reply_text.call_args_list[-1][0][0]
            assert "notes/test.md" in final_call

    @pytest.mark.asyncio
    async def test_handle_message_without_url(
        self, bot_app: TelegramBotApp, mock_telegram_update: MagicMock, mock_telegram_context: MagicMock
    ) -> None:
        """不包含 URL 的消息应返回提示。"""
        mock_telegram_update.message.text = "这是一段没有链接的文本"

        await bot_app.handle_message(mock_telegram_update, mock_telegram_context)

        mock_telegram_update.message.reply_text.assert_called_once()
        call_args = mock_telegram_update.message.reply_text.call_args[0][0]
        assert "未检测到" in call_args or "http" in call_args.lower()

    @pytest.mark.asyncio
    async def test_handle_message_empty_text(
        self, bot_app: TelegramBotApp, mock_telegram_update: MagicMock, mock_telegram_context: MagicMock
    ) -> None:
        """空消息应被忽略。"""
        mock_telegram_update.message.text = None

        await bot_app.handle_message(mock_telegram_update, mock_telegram_context)

        mock_telegram_update.message.reply_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_message_no_message(self, bot_app: TelegramBotApp, mock_telegram_context: MagicMock) -> None:
        """无消息对象时应被忽略。"""
        update = MagicMock()
        update.message = None

        await bot_app.handle_message(update, mock_telegram_context)
        # 不应抛出异常

    @pytest.mark.asyncio
    async def test_handle_message_pipeline_error(
        self, bot_app: TelegramBotApp, mock_telegram_update: MagicMock, mock_telegram_context: MagicMock
    ) -> None:
        """Pipeline 处理失败时应返回错误消息。"""
        mock_telegram_update.message.text = "请总结 https://example.com/article"

        with patch.object(bot_app, "_pipeline") as mock_pipeline:
            mock_pipeline.process_url.side_effect = Exception("网络连接失败")

            await bot_app.handle_message(mock_telegram_update, mock_telegram_context)

            # 应该回复错误消息
            final_call = mock_telegram_update.message.reply_text.call_args_list[-1][0][0]
            assert "失败" in final_call

    @pytest.mark.asyncio
    async def test_handle_message_result_without_commit_hash(
        self, bot_app: TelegramBotApp, mock_telegram_update: MagicMock, mock_telegram_context: MagicMock
    ) -> None:
        """处理结果无 commit hash 时应正常返回。"""
        mock_telegram_update.message.text = "请总结 https://example.com/article"

        with patch.object(bot_app, "_pipeline") as mock_pipeline:
            mock_result = MagicMock()
            mock_result.file_path = "notes/test.md"
            mock_result.commit_hash = None
            mock_pipeline.process_url.return_value = mock_result

            await bot_app.handle_message(mock_telegram_update, mock_telegram_context)

            final_call = mock_telegram_update.message.reply_text.call_args_list[-1][0][0]
            assert "notes/test.md" in final_call
            assert "Commit" not in final_call
