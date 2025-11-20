from __future__ import annotations

"""Thin OpenAI-compatible chat completions client."""

import json
from dataclasses import dataclass
from typing import Optional

import requests

from .config import LLMConfig


class LLMError(Exception):
    pass


PROMPT = (
    "You are a summarizer that rewrites provided Markdown content into a clear note. "
    "Keep all useful information, preserve images and hyperlinks, and improve readability. "
    "Do not invent facts. Output Markdown body only (no YAML frontmatter)."
)


@dataclass
class LLMClient:
    config: LLMConfig

    def summarize_markdown(self, markdown_content: str, title: Optional[str] = None) -> str:
        if not markdown_content.strip():
            raise LLMError("No content to summarize")

        messages = [
            {"role": "system", "content": PROMPT},
            {
                "role": "user",
                "content": (
                    f"Title: {title}\n\n" if title else ""
                )
                + "Content:" + "\n" + markdown_content,
            },
        ]

        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0.2,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config.api_key}",
        }

        try:
            resp = requests.post(
                f"{self.config.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                data=json.dumps(payload),
                timeout=60,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return content.strip()
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMError(f"Unexpected LLM response format: {exc}") from exc
        except requests.RequestException as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc
