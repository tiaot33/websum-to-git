from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml


@dataclass
class LLMConfig:
    provider: str
    api_key: str
    model: str
    base_url: str | None = None


@dataclass
class GitHubConfig:
    repo: str  # e.g. "owner/repo"
    branch: str = "main"
    target_dir: str = ""
    pat: str = ""


@dataclass
class TelegramConfig:
    bot_token: str


@dataclass
class HttpConfig:
    # 控制抓取网页时是否校验证书；正常情况下应保持为 True
    verify_ssl: bool = True


@dataclass
class AppConfig:
    telegram: TelegramConfig
    llm: LLMConfig
    github: GitHubConfig
    http: HttpConfig


def _require(mapping: Dict[str, Any], key: str) -> Any:
    if key not in mapping or mapping[key] in ("", None):
        raise ValueError(f"配置缺少必填字段: {key}")
    return mapping[key]


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    telegram_raw = raw.get("telegram", {})
    llm_raw = raw.get("llm", {})
    github_raw = raw.get("github", {})
    http_raw = raw.get("http", {}) or {}

    telegram = TelegramConfig(bot_token=_require(telegram_raw, "bot_token"))

    provider = (llm_raw.get("provider") or "openai").lower()
    api_key = _require(llm_raw, "api_key")
    model = _require(llm_raw, "model")
    base_url = llm_raw.get("base_url")

    if provider == "openai":
        # 对于 OpenAI/兼容服务，如果未指定 base_url，则使用官方默认地址
        base_url = base_url or "https://api.openai.com"

    llm = LLMConfig(
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
    )

    github = GitHubConfig(
        repo=_require(github_raw, "repo"),
        branch=github_raw.get("branch", "main"),
        target_dir=github_raw.get("target_dir", "").rstrip("/"),
        pat=_require(github_raw, "pat"),
    )

    http = HttpConfig(
        verify_ssl=http_raw.get("verify_ssl", True),
    )

    return AppConfig(telegram=telegram, llm=llm, github=github, http=http)
