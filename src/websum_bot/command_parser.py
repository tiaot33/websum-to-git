from __future__ import annotations

"""Parse Telegram command arguments into structured options."""

import re
from dataclasses import dataclass
from typing import List

from .config import BotConfig


@dataclass
class CommandOptions:
    url: str
    repo: str
    branch: str
    filename: str | None
    author_name: str | None
    author_email: str | None
    tags: List[str]
    categories: List[str]
    keywords: List[str]


def _split_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "-", name)
    if "/" in cleaned or "\\" in cleaned:
        cleaned = cleaned.replace("/", "-").replace("\\", "-")
    if not cleaned.endswith(".md"):
        cleaned = f"{cleaned}.md"
    return cleaned


def parse_command_args(args: list[str], config: BotConfig) -> CommandOptions:
    if not args:
        raise ValueError("URL is required")

    url = args[0]
    options: dict[str, str] = {}
    for token in args[1:]:
        if "=" not in token:
            raise ValueError(f"Invalid argument '{token}', expected key=value")
        key, value = token.split("=", 1)
        options[key.strip().lower()] = value.strip()

    repo = options.get("repo", config.github.default_repo)
    branch = options.get("branch", config.github.default_branch)
    filename = options.get("filename")
    if filename:
        filename = _sanitize_filename(filename)

    author_name = options.get("author_name")
    author_email = options.get("author_email")

    tags = _split_list(options.get("tags"))
    categories = _split_list(options.get("categories"))
    keywords = _split_list(options.get("keywords"))

    return CommandOptions(
        url=url,
        repo=repo,
        branch=branch,
        filename=filename,
        author_name=author_name,
        author_email=author_email,
        tags=tags,
        categories=categories,
        keywords=keywords,
    )
