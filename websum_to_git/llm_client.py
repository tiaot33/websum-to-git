from __future__ import annotations

from typing import Any, Dict, List

from .config import LLMConfig


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        provider = (config.provider or "openai").lower()
        self._provider = provider

        # 延迟导入对应 SDK，避免不必要依赖
        if provider == "openai":
            from openai import OpenAI

            self._client = OpenAI(api_key=config.api_key, base_url=config.base_url)
        elif provider == "anthropic":
            import anthropic

            self._client = anthropic.Anthropic(api_key=config.api_key)
        elif provider == "gemini":
            import google.generativeai as genai

            genai.configure(api_key=config.api_key)
            # 对于 Gemini，我们直接在构造阶段创建模型实例
            self._client = genai.GenerativeModel(config.model)
        else:
            raise ValueError(f"不支持的 LLM provider: {config.provider}")

    def summarize_page(self, *, title: str, url: str, body_text: str, max_chars: int = 8000) -> str:
        text = body_text.strip()
        if len(text) > max_chars:
            text = text[:max_chars]

        system_prompt = (
            "你是一个知识管理助手，负责将网页内容整理为适合 Obsidian 的 Markdown 笔记。\n"
            "要求：\n"
            "- 输出结构清晰的 Markdown，使用合适的标题和列表。\n"
            "- 用简洁中文总结主要观点和层次结构。\n"
            "- 不需要生成 YAML front matter。\n"
            "- 不需要包含图片链接，图片会由系统自动附加。\n"
        )

        user_content = (
            f"网页标题: {title}\n"
            f"网页地址: {url}\n\n"
            f"正文内容:\n{text}\n"
        )

        if self._provider == "openai":
            return self._summarize_with_openai(system_prompt, user_content)
        if self._provider == "anthropic":
            return self._summarize_with_anthropic(system_prompt, user_content)
        if self._provider == "gemini":
            return self._summarize_with_gemini(system_prompt, user_content)

        raise RuntimeError(f"未知的 LLM provider: {self._provider}")

    def _summarize_with_openai(self, system_prompt: str, user_content: str) -> str:
        # OpenAI / OpenAI 兼容 API，使用官方 SDK
        resp = self._client.chat.completions.create(
            model=self._config.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content or ""

    def _summarize_with_anthropic(self, system_prompt: str, user_content: str) -> str:
        # Anthropic 原生 SDK，使用 messages API
        resp = self._client.messages.create(
            model=self._config.model,
            max_tokens=4096,
            temperature=0.2,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}],
        )

        parts: List[str] = []
        for block in getattr(resp, "content", []) or []:
            if getattr(block, "type", None) == "text":
                parts.append(getattr(block, "text", ""))
        text = "".join(parts).strip()
        if not text and hasattr(resp, "content"):
            # 兜底：尝试直接 str()
            text = str(resp)
        return text

    def _summarize_with_gemini(self, system_prompt: str, user_content: str) -> str:
        # Gemini (Google Generative AI) SDK
        # 通过将 system_prompt + user_content 作为多段输入，引导模型输出 Markdown 总结
        resp = self._client.generate_content(
            [system_prompt, user_content],
        )
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
