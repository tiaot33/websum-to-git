from __future__ import annotations

from dataclasses import dataclass, field
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
    # Bot 任务并发上限（正在执行的任务数）
    max_concurrent_jobs: int = 2
    # 全局 pending 队列上限（不含 running）
    max_queue_size: int = 50
    # 单个 Chat pending 队列上限（不含 running）
    max_queue_size_per_chat: int = 10


@dataclass
class HttpConfig:
    # 控制抓取网页时是否校验证书；正常情况下应保持为 True
    verify_ssl: bool = True


@dataclass
class DefuddleConfig:
    # 是否启用 Defuddle 作为短内容兜底抓取；默认开启，可按需显式关闭
    enabled: bool = True
    # Defuddle 代理服务地址；可替换为自托管实例
    base_url: str | None = None
    # 默认移除常见追踪参数，避免抓取和落库保留脏链接
    strip_tracking: bool = True


@dataclass
class AppConfig:
    telegram: TelegramConfig
    llm: LLMConfig
    github: GitHubConfig
    http: HttpConfig
    fast_llm: LLMConfig | None = None
    defuddle: DefuddleConfig = field(default_factory=DefuddleConfig)


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
    defuddle_raw = raw.get("defuddle", {}) or {}
    http_raw = raw.get("http", {}) or {}

    telegram = TelegramConfig(
        bot_token=_require(telegram_raw, "bot_token"),
        max_concurrent_jobs=int(telegram_raw.get("max_concurrent_jobs", 2)),
        max_queue_size=int(telegram_raw.get("max_queue_size", 50)),
        max_queue_size_per_chat=int(telegram_raw.get("max_queue_size_per_chat", 10)),
    )
    if telegram.max_concurrent_jobs <= 0:
        raise ValueError("配置非法: telegram.max_concurrent_jobs 必须 > 0")
    if telegram.max_queue_size <= 0:
        raise ValueError("配置非法: telegram.max_queue_size 必须 > 0")
    if telegram.max_queue_size_per_chat <= 0:
        raise ValueError("配置非法: telegram.max_queue_size_per_chat 必须 > 0")

    llm = _build_llm_config(llm_raw)
    fast_llm = _build_llm_config(llm_fast_raw) if llm_fast_raw else None

    github = GitHubConfig(
        repo=_require(github_raw, "repo"),
        branch=github_raw.get("branch", "main"),
        target_dir=github_raw.get("target_dir", "").rstrip("/"),
        pat=_require(github_raw, "pat"),
    )

    http = HttpConfig(
        verify_ssl=http_raw.get("verify_ssl", True),
    )

    defuddle = DefuddleConfig(
        enabled=bool(defuddle_raw.get("enabled", True)),
        base_url=defuddle_raw.get("base_url"),
        strip_tracking=bool(defuddle_raw.get("strip_tracking", True)),
    )

    return AppConfig(
        telegram=telegram,
        llm=llm,
        github=github,
        http=http,
        fast_llm=fast_llm,
        defuddle=defuddle,
    )
