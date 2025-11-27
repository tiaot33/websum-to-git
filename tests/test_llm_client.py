"""LLM 客户端模块测试。

测试覆盖：
- 多厂商 LLM 初始化
- 生成请求处理
- 错误处理
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from websum_to_git.config import LLMConfig
from websum_to_git.llm_client import LLMClient

if TYPE_CHECKING:
    pass


# ============================================================
# LLMClient 初始化测试
# ============================================================


class TestLLMClientInit:
    """测试 LLM 客户端初始化。"""

    def test_init_openai_provider(self) -> None:
        """OpenAI provider 应正确初始化。"""
        config = LLMConfig(
            provider="openai",
            api_key="test-key",
            model="gpt-4o",
            base_url="https://api.openai.com",
        )

        with patch("websum_to_git.llm_client.OpenAI") as mock_openai:
            client = LLMClient(config)

            mock_openai.assert_called_once_with(api_key="test-key", base_url="https://api.openai.com")
            assert client._provider == "openai"

    def test_init_openai_response_provider(self) -> None:
        """OpenAI Response provider 应正确初始化。"""
        config = LLMConfig(
            provider="openai-response",
            api_key="test-key",
            model="gpt-4o",
            base_url="https://api.openai.com",
        )

        with patch("websum_to_git.llm_client.OpenAI") as mock_openai:
            client = LLMClient(config)

            mock_openai.assert_called_once()
            assert client._provider == "openai-response"

    def test_init_anthropic_provider(self) -> None:
        """Anthropic provider 应正确初始化。"""
        config = LLMConfig(
            provider="anthropic",
            api_key="test-key",
            model="claude-3-opus-20240229",
        )

        with patch("websum_to_git.llm_client.anthropic") as mock_anthropic:
            client = LLMClient(config)

            mock_anthropic.Anthropic.assert_called_once_with(api_key="test-key")
            assert client._provider == "anthropic"

    def test_init_anthropic_with_base_url(self) -> None:
        """Anthropic provider 自定义 base_url。"""
        config = LLMConfig(
            provider="anthropic",
            api_key="test-key",
            model="claude-3-opus-20240229",
            base_url="https://custom-anthropic.com",
        )

        with patch("websum_to_git.llm_client.anthropic") as mock_anthropic:
            LLMClient(config)

            mock_anthropic.Anthropic.assert_called_once_with(
                api_key="test-key",
                base_url="https://custom-anthropic.com",
            )

    def test_init_gemini_provider(self) -> None:
        """Gemini provider 应正确初始化。"""
        config = LLMConfig(
            provider="gemini",
            api_key="test-key",
            model="gemini-pro",
        )

        with patch("websum_to_git.llm_client.genai") as mock_genai:
            client = LLMClient(config)

            mock_genai.configure.assert_called_once_with(api_key="test-key")
            mock_genai.GenerativeModel.assert_called_once_with("gemini-pro")
            assert client._provider == "gemini"

    def test_init_unsupported_provider(self) -> None:
        """不支持的 provider 应抛出 ValueError。"""
        config = LLMConfig(
            provider="unsupported-provider",
            api_key="test-key",
            model="some-model",
        )

        with pytest.raises(ValueError) as exc_info:
            LLMClient(config)

        assert "不支持" in str(exc_info.value)

    def test_init_provider_case_insensitive(self) -> None:
        """Provider 名称应不区分大小写。"""
        config = LLMConfig(
            provider="OPENAI",
            api_key="test-key",
            model="gpt-4o",
            base_url="https://api.openai.com",
        )

        with patch("websum_to_git.llm_client.OpenAI"):
            client = LLMClient(config)
            assert client._provider == "openai"


# ============================================================
# OpenAI 生成测试
# ============================================================


class TestLLMClientOpenAI:
    """测试 OpenAI provider 的生成功能。"""

    @pytest.fixture
    def openai_client(self) -> LLMClient:
        """创建 OpenAI LLM 客户端。"""
        config = LLMConfig(
            provider="openai",
            api_key="test-key",
            model="gpt-4o",
            base_url="https://api.openai.com",
        )
        with patch("websum_to_git.llm_client.OpenAI"):
            return LLMClient(config)

    def test_generate_with_system_prompt(self, openai_client: LLMClient) -> None:
        """带系统提示词的生成。"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated response"

        openai_client._client.chat.completions.create = MagicMock(return_value=mock_response)

        result = openai_client.generate(
            system_prompt="You are a helpful assistant.",
            user_content="Hello",
        )

        assert result == "Generated response"

        # 验证调用参数
        call_args = openai_client._client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_generate_without_system_prompt(self, openai_client: LLMClient) -> None:
        """不带系统提示词的生成。"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Generated response"

        openai_client._client.chat.completions.create = MagicMock(return_value=mock_response)

        result = openai_client.generate(
            system_prompt=None,
            user_content="Hello",
        )

        assert result == "Generated response"

        # 验证只有一条消息
        call_args = openai_client._client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    def test_generate_empty_content_returns_empty(self, openai_client: LLMClient) -> None:
        """返回内容为空时返回空字符串。"""
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None

        openai_client._client.chat.completions.create = MagicMock(return_value=mock_response)

        result = openai_client.generate(
            system_prompt=None,
            user_content="Hello",
        )

        assert result == ""


# ============================================================
# Anthropic 生成测试
# ============================================================


class TestLLMClientAnthropic:
    """测试 Anthropic provider 的生成功能。"""

    @pytest.fixture
    def anthropic_client(self) -> LLMClient:
        """创建 Anthropic LLM 客户端。"""
        config = LLMConfig(
            provider="anthropic",
            api_key="test-key",
            model="claude-3-opus-20240229",
        )
        with patch("websum_to_git.llm_client.anthropic"):
            return LLMClient(config)

    def test_generate_with_system_prompt(self, anthropic_client: LLMClient) -> None:
        """带系统提示词的生成。"""
        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = "Generated response"

        mock_response = MagicMock()
        mock_response.content = [mock_block]

        anthropic_client._client.messages.create = MagicMock(return_value=mock_response)

        result = anthropic_client.generate(
            system_prompt="You are a helpful assistant.",
            user_content="Hello",
        )

        assert result == "Generated response"

        # 验证系统提示词作为 system 参数传递
        call_args = anthropic_client._client.messages.create.call_args
        assert "system" in call_args.kwargs
        assert call_args.kwargs["system"] == "You are a helpful assistant."

    def test_generate_anthropic_max_tokens(self, anthropic_client: LLMClient) -> None:
        """Anthropic 应设置 max_tokens。"""
        mock_response = MagicMock()
        mock_response.content = []

        anthropic_client._client.messages.create = MagicMock(return_value=mock_response)

        anthropic_client.generate(system_prompt=None, user_content="Hello")

        call_args = anthropic_client._client.messages.create.call_args
        assert call_args.kwargs["max_tokens"] == 4096


# ============================================================
# Gemini 生成测试
# ============================================================


class TestLLMClientGemini:
    """测试 Gemini provider 的生成功能。"""

    @pytest.fixture
    def gemini_client(self) -> LLMClient:
        """创建 Gemini LLM 客户端。"""
        config = LLMConfig(
            provider="gemini",
            api_key="test-key",
            model="gemini-pro",
        )
        with patch("websum_to_git.llm_client.genai") as mock_genai:
            mock_model = MagicMock()
            mock_genai.GenerativeModel.return_value = mock_model
            client = LLMClient(config)
            return client

    def test_generate_with_system_prompt(self, gemini_client: LLMClient) -> None:
        """Gemini 系统提示词应拼接到内容中。"""
        mock_response = MagicMock()
        mock_response.text = "Generated response"

        gemini_client._client.generate_content = MagicMock(return_value=mock_response)

        result = gemini_client.generate(
            system_prompt="You are a helpful assistant.",
            user_content="Hello",
        )

        assert result == "Generated response"

        # 验证内容拼接
        call_args = gemini_client._client.generate_content.call_args[0][0]
        assert len(call_args) == 2
        assert call_args[0] == "You are a helpful assistant."
        assert call_args[1] == "Hello"

    def test_generate_without_system_prompt(self, gemini_client: LLMClient) -> None:
        """不带系统提示词只传递用户内容。"""
        mock_response = MagicMock()
        mock_response.text = "Generated response"

        gemini_client._client.generate_content = MagicMock(return_value=mock_response)

        result = gemini_client.generate(
            system_prompt=None,
            user_content="Hello",
        )

        assert result == "Generated response"

        # 验证只有一个内容
        call_args = gemini_client._client.generate_content.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0] == "Hello"


# ============================================================
# 错误处理测试
# ============================================================


class TestLLMClientErrors:
    """测试 LLM 客户端错误处理。"""

    def test_generate_unknown_provider_runtime_error(self) -> None:
        """运行时遇到未知 provider 应抛出 RuntimeError。"""
        config = LLMConfig(
            provider="openai",
            api_key="test-key",
            model="gpt-4o",
            base_url="https://api.openai.com",
        )

        with patch("websum_to_git.llm_client.OpenAI"):
            client = LLMClient(config)
            # 强制修改 provider 到未知值
            client._provider = "unknown"

            with pytest.raises(RuntimeError) as exc_info:
                client.generate(system_prompt=None, user_content="Hello")

            assert "未知" in str(exc_info.value)
