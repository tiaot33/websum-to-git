from __future__ import annotations

import logging
from typing import Any

import anthropic
from google import genai
from google.genai import types
from openai import OpenAI

from .config import LLMConfig

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        provider = (config.provider or "openai").lower()
        self._provider = provider
        self._client: Any

        # 延迟导入对应 SDK，避免不必要依赖
        if provider in ("openai", "openai-response"):
            self._client = OpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
                timeout=600.0,  # 10 分钟超时，适应长文本生成
            )
        elif provider == "anthropic":
            client_kwargs: dict[str, Any] = {"api_key": config.api_key}
            if config.base_url:
                client_kwargs["base_url"] = config.base_url
            self._client = anthropic.Anthropic(**client_kwargs)
        elif provider == "gemini":
            client = genai.Client(api_key=config.api_key, http_options=types.HttpOptions(base_url=config.base_url))
            self._client = client
        else:
            raise ValueError(f"不支持的 LLM provider: {config.provider}")

    def generate(self, *, system_prompt: str | None, user_content: str) -> str:
        """
        调用底层 LLM 完成一次通用生成请求。

        - system_prompt 用于提供系统级指令（可为空）
        - user_content 为用户输入内容（必填）
        """
        logger.info(
            "LLM 生成请求, provider: %s, model: %s, system_prompt 长度: %d, user_content 长度: %d",
            self._provider,
            self._config.model,
            len(system_prompt) if system_prompt else 0,
            len(user_content),
        )

        if self._provider == "openai":
            result = self._generate_with_openai(system_prompt, user_content)
        elif self._provider == "openai-response":
            result = self._generate_with_openai_response(system_prompt, user_content)
        elif self._provider == "anthropic":
            result = self._generate_with_anthropic(system_prompt, user_content)
        elif self._provider == "gemini":
            result = self._generate_with_gemini(system_prompt, user_content)
        else:
            raise RuntimeError(f"未知的 LLM provider: {self._provider}")

        logger.info("LLM 生成完成, 响应长度: %d", len(result))
        return result

    def _generate_with_openai(self, system_prompt: str | None, user_content: str) -> str:
        # OpenAI / OpenAI 兼容 API，使用官方 SDK 的 chat.completions
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_content})
        kwargs: dict[str, Any] = {}
        if self._config.enable_thinking:
            kwargs: dict[str, Any] = {
                "extra_body": {
                    "google": {"thinking_config": {"thinking_budget": 19660, "include_thoughts": "true"}},
                    "thinking": {
                        "type": "enabled",
                    },
                    "reasoning_effort": "high",
                }
            }
        resp = self._client.chat.completions.create(
            model=self._config.model,
            messages=messages,
            temperature=1.0,
            **kwargs,
        )
        return resp.choices[0].message.content or ""

    def _generate_with_openai_response(self, system_prompt: str | None, user_content: str) -> str:
        # OpenAI Responses API，支持新一代统一输入输出格式
        # 对于兼容 Responses 的服务，可配置 provider=openai-response
        input_segments: list[dict[str, Any]] = []
        if system_prompt:
            input_segments.append({"role": "system", "content": system_prompt})
        input_segments.append({"role": "user", "content": user_content})
        resp = self._client.responses.create(
            model=self._config.model,
            input=input_segments,
            reasoning={"effort": "high" if self._config.enable_thinking else "none"},
            temperature=1.0,
        )
        if hasattr(resp, "output_text") and resp.output_text:
            return resp.output_text

        parts: list[str] = []
        for item in getattr(resp, "output", []) or []:
            for content in getattr(item, "content", []) or []:
                text = getattr(content, "text", None)
                if text:
                    parts.append(text)

        text = "".join(parts).strip()
        if not text:
            # 兜底：有些兼容服务可能直接返回 text 字段
            direct_text = getattr(resp, "text", None)
            if isinstance(direct_text, str) and direct_text.strip():
                return direct_text.strip()
            text = str(resp)
        return text

    def _generate_with_anthropic(self, system_prompt: str | None, user_content: str) -> str:
        # Anthropic 原生 SDK，使用 messages API
        kwargs: dict[str, Any] = {
            "model": self._config.model,
            "max_token": 32000,
            "messages": [{"role": "user", "content": user_content}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt
        if self._config.enable_thinking:
            kwargs["thinking"] = True
        resp = self._client.messages.create(**kwargs)

        parts: list[str] = []
        for block in getattr(resp, "content", []) or []:
            if getattr(block, "type", None) == "text":
                parts.append(getattr(block, "text", ""))
        text = "".join(parts).strip()
        if not text and hasattr(resp, "content"):
            # 兜底：尝试直接 str()
            text = str(resp)
        return text

    def _generate_with_gemini(self, system_prompt: str | None, user_content: str) -> str:
        # Gemini (Google Generative AI) SDK
        # 通过将 system_prompt + user_content 作为多段输入，引导模型输出
        contents: list[str] = []
        if system_prompt:
            contents.append(system_prompt)
        contents.append(user_content)

        model_name = self._config.model or ""
        thinking_config: types.ThinkingConfig | None = None
        # 仅在 enable_thinking=True 时启用 thinking 功能
        if self._config.enable_thinking:
            if model_name.startswith("gemini-2.5-pro"):
                thinking_config = types.ThinkingConfig(thinking_budget=32768)
            elif model_name.startswith("gemini-2.5-flash"):
                thinking_config = types.ThinkingConfig(thinking_budget=19660)
            elif model_name.startswith("gemini-3-pro"):
                thinking_config = types.ThinkingConfig(thinking_level=types.ThinkingLevel.HIGH)
        else:
            thinking_config = types.ThinkingConfig(thinking_budget=0)
        generate_kwargs: dict[str, Any] = {
            "model": model_name,
            "contents": contents,
        }
        if thinking_config is not None:
            generate_kwargs["config"] = types.GenerateContentConfig(thinking_config=thinking_config)
        resp = self._client.models.generate_content(**generate_kwargs)
        text = getattr(resp, "text", None)
        if text:
            return text
        # 某些情况下，内容可能在 candidates 中
        candidates = getattr(resp, "candidates", None) or []
        for cand in candidates:
            content = getattr(cand, "content", None)
            if not content:
                continue
            parts = getattr(content, "parts", None) or []
            for part in parts:
                if hasattr(part, "text") and part.text:
                    return part.text
        return ""
