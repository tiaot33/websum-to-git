from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class LLMConfig:
    provider: str
    api_key: str
    model: str
    base_url: str | None = None
    # 是否启用模型的 thinking/reasoning 功能（目前仅 Gemini 支持）
    enable_thinking: bool = True
    # 单次 LLM 请求最大输入 token 数
    max_input_tokens: int = 10000


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
    # 控制抓取模式："requests" 或 "headless"
    fetch_mode: str = "requests"


@dataclass
class AppConfig:
    telegram: TelegramConfig
    llm: LLMConfig
    github: GitHubConfig
    http: HttpConfig
    fast_llm: LLMConfig | None = None


def _require(mapping: dict[str, Any], key: str) -> Any:
    if key not in mapping or mapping[key] in ("", None):
        raise ValueError(f"配置缺少必填字段: {key}")
    return mapping[key]


def _build_llm_config(llm_raw: dict[str, Any]) -> LLMConfig:
    provider = (llm_raw.get("provider") or "openai").lower()
    api_key = _require(llm_raw, "api_key")
    model = _require(llm_raw, "model")
    base_url = llm_raw.get("base_url")

    if provider in ("openai", "openai-response"):
        # 对于 OpenAI/兼容服务，如果未指定 base_url，则使用官方默认地址
        base_url = base_url or "https://api.openai.com"

    # enable_thinking 默认为 True，配置中可显式设为 false 关闭
    enable_thinking = llm_raw.get("enable_thinking", True)
    # max_input_tokens 默认为 10000
    max_input_tokens = llm_raw.get("max_input_tokens", 10000)

    return LLMConfig(
        provider=provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
        enable_thinking=bool(enable_thinking),
        max_input_tokens=int(max_input_tokens),
    )


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    telegram_raw = raw.get("telegram", {})
    llm_raw = raw.get("llm", {})
    llm_fast_raw = raw.get("llm_fast")
    github_raw = raw.get("github", {})
    http_raw = raw.get("http", {}) or {}

    telegram = TelegramConfig(bot_token=_require(telegram_raw, "bot_token"))

    llm = _build_llm_config(llm_raw)
    fast_llm = _build_llm_config(llm_fast_raw) if llm_fast_raw else None

    github = GitHubConfig(
        repo=_require(github_raw, "repo"),
        branch=github_raw.get("branch", "main"),
        target_dir=github_raw.get("target_dir", "").rstrip("/"),
        pat=_require(github_raw, "pat"),
    )

    fetch_mode = (http_raw.get("fetch_mode") or "requests").lower()
    if fetch_mode not in {"requests", "headless"}:
        raise ValueError("http.fetch_mode 必须为 'requests' 或 'headless'")

    http = HttpConfig(
        verify_ssl=http_raw.get("verify_ssl", True),
        fetch_mode=fetch_mode,
    )

    return AppConfig(telegram=telegram, llm=llm, github=github, http=http, fast_llm=fast_llm)
