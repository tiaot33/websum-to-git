"""Environment-backed configuration for bot, GitHub, and LLM."""

import os
from dataclasses import dataclass


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    return value.strip() if isinstance(value, str) else value


@dataclass
class GithubConfig:
    token: str
    default_repo: str
    default_branch: str
    default_author_name: str | None = None
    default_author_email: str | None = None


@dataclass
class LLMConfig:
    api_key: str
    base_url: str
    model: str


@dataclass
class BotConfig:
    telegram_token: str
    llm: LLMConfig
    github: GithubConfig

    @classmethod
    def load(cls) -> "BotConfig":
        telegram_token = _env("TELEGRAM_BOT_TOKEN")
        if not telegram_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")

        gh_token = _env("GITHUB_TOKEN")
        gh_repo = _env("DEFAULT_GITHUB_REPO")
        gh_branch = _env("DEFAULT_BRANCH", "main")
        if not gh_token or not gh_repo:
            raise ValueError("GITHUB_TOKEN and DEFAULT_GITHUB_REPO are required")

        llm_api_key = _env("OPENAI_API_KEY")
        if not llm_api_key:
            raise ValueError("OPENAI_API_KEY is required for external LLM calls")

        llm_base = _env("OPENAI_BASE_URL", "https://api.openai.com/v1")
        llm_model = _env("OPENAI_MODEL", "gpt-4o-mini")

        github = GithubConfig(
            token=gh_token,
            default_repo=gh_repo,
            default_branch=gh_branch,
            default_author_name=_env("DEFAULT_AUTHOR_NAME"),
            default_author_email=_env("DEFAULT_AUTHOR_EMAIL"),
        )
        llm = LLMConfig(api_key=llm_api_key, base_url=llm_base, model=llm_model)
        return cls(telegram_token=telegram_token, llm=llm, github=github)
