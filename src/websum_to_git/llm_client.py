from __future__ import annotations

from typing import Any

from .config import LLMConfig


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        provider = (config.provider or "openai").lower()
        self._provider = provider

        # 延迟导入对应 SDK，避免不必要依赖
        if provider in ("openai", "openai-response"):
            from openai import OpenAI

            self._client = OpenAI(api_key=config.api_key, base_url=config.base_url)
        elif provider == "anthropic":
            import anthropic

            client_kwargs: dict[str, Any] = {"api_key": config.api_key}
            if config.base_url:
                client_kwargs["base_url"] = config.base_url
            self._client = anthropic.Anthropic(**client_kwargs)
        elif provider == "gemini":
            import google.generativeai as genai

            client_kwargs: dict[str, Any] = {"api_key": config.api_key}
            if config.base_url:
                # 部分 Gemini 兼容服务通过自定义 api_endpoint 暴露
                client_kwargs["client_options"] = {"api_endpoint": config.base_url}
            genai.configure(**client_kwargs)
            # 对于 Gemini，我们直接在构造阶段创建模型实例
            self._client = genai.GenerativeModel(config.model)
        else:
            raise ValueError(f"不支持的 LLM provider: {config.provider}")

    def generate(self, *, system_prompt: str | None, user_content: str) -> str:
        """
        调用底层 LLM 完成一次通用生成请求。

        - system_prompt 用于提供系统级指令（可为空）
        - user_content 为用户输入内容（必填）
        """
        if self._provider == "openai":
            return self._generate_with_openai(system_prompt, user_content)
        if self._provider == "openai-response":
            return self._generate_with_openai_response(system_prompt, user_content)
        if self._provider == "anthropic":
            return self._generate_with_anthropic(system_prompt, user_content)
        if self._provider == "gemini":
            return self._generate_with_gemini(system_prompt, user_content)

        raise RuntimeError(f"未知的 LLM provider: {self._provider}")

    def _generate_with_openai(self, system_prompt: str | None, user_content: str) -> str:
        # OpenAI / OpenAI 兼容 API，使用官方 SDK 的 chat.completions
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_content})

        resp = self._client.chat.completions.create(
            model=self._config.model,
            messages=messages,
            temperature=0.2,
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
            temperature=0.2,
        )

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
            "max_tokens": 4096,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": user_content}],
        }
        if system_prompt:
            kwargs["system"] = system_prompt

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

        resp = self._client.generate_content(contents)
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
