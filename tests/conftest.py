"""共享测试 fixtures 和配置。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from websum_to_git.config import AppConfig, GitHubConfig, HttpConfig, LLMConfig, TelegramConfig
from websum_to_git.html_processor import PageContent

if TYPE_CHECKING:
    pass


# ============================================================
# 配置相关 Fixtures
# ============================================================


@pytest.fixture
def sample_llm_config() -> LLMConfig:
    """创建测试用 LLM 配置。"""
    return LLMConfig(
        provider="openai",
        api_key="test-api-key-12345",
        model="gpt-4o",
        base_url="https://api.openai.com",
    )


@pytest.fixture
def sample_github_config() -> GitHubConfig:
    """创建测试用 GitHub 配置。"""
    return GitHubConfig(
        repo="test-owner/test-repo",
        branch="main",
        target_dir="notes",
        pat="ghp_testtoken123456",
    )


@pytest.fixture
def sample_telegram_config() -> TelegramConfig:
    """创建测试用 Telegram 配置。"""
    return TelegramConfig(bot_token="123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")


@pytest.fixture
def sample_http_config() -> HttpConfig:
    """创建测试用 HTTP 配置。"""
    return HttpConfig(verify_ssl=True, fetch_mode="requests")


@pytest.fixture
def sample_app_config(
    sample_telegram_config: TelegramConfig,
    sample_llm_config: LLMConfig,
    sample_github_config: GitHubConfig,
    sample_http_config: HttpConfig,
) -> AppConfig:
    """创建完整的测试用应用配置。"""
    return AppConfig(
        telegram=sample_telegram_config,
        llm=sample_llm_config,
        github=sample_github_config,
        http=sample_http_config,
    )


# ============================================================
# HTML 和页面内容相关 Fixtures
# ============================================================


@pytest.fixture
def sample_html() -> str:
    """创建测试用 HTML 页面内容。"""
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>Python 编程入门指南</title>
</head>
<body>
    <header>
        <nav>导航栏</nav>
    </header>
    <article>
        <h1>Python 编程入门指南</h1>
        <p>Python 是一种广泛使用的高级编程语言，以其简洁易读的语法著称。</p>
        <h2>基础语法</h2>
        <p>Python 使用缩进来定义代码块，这使得代码更加整洁。</p>
        <pre><code>
def hello():
    print("Hello, World!")
        </code></pre>
        <h2>数据类型</h2>
        <p>Python 支持多种数据类型，包括整数、浮点数、字符串和列表。</p>
        <ul>
            <li>整数 (int)</li>
            <li>浮点数 (float)</li>
            <li>字符串 (str)</li>
            <li>列表 (list)</li>
        </ul>
    </article>
    <footer>
        <p>版权所有 © 2024</p>
    </footer>
    <script>console.log('test');</script>
</body>
</html>
"""


@pytest.fixture
def sample_english_html() -> str:
    """创建测试用英文 HTML 页面内容。"""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Getting Started with Python</title>
</head>
<body>
    <article>
        <h1>Getting Started with Python</h1>
        <p>Python is a widely used high-level programming language known for its clear syntax.</p>
        <h2>Basic Syntax</h2>
        <p>Python uses indentation to define code blocks, making the code cleaner.</p>
    </article>
</body>
</html>
"""


@pytest.fixture
def sample_page_content() -> PageContent:
    """创建测试用 PageContent 对象。"""
    return PageContent(
        url="https://example.com/python-guide",
        final_url="https://example.com/python-guide",
        title="Python 编程入门指南",
        text="Python 是一种广泛使用的高级编程语言，以其简洁易读的语法著称。Python 使用缩进来定义代码块。",
        markdown="""# Python 编程入门指南

Python 是一种广泛使用的高级编程语言，以其简洁易读的语法著称。

## 基础语法

Python 使用缩进来定义代码块，这使得代码更加整洁。

```
def hello():
    print("Hello, World!")
```

## 数据类型

Python 支持多种数据类型，包括整数、浮点数、字符串和列表。

- 整数 (int)
- 浮点数 (float)
- 字符串 (str)
- 列表 (list)
""",
        raw_html="<html>...</html>",
        article_html="<article>...</article>",
    )


@pytest.fixture
def sample_english_page_content() -> PageContent:
    """创建测试用英文 PageContent 对象。"""
    return PageContent(
        url="https://example.com/python-guide",
        final_url="https://example.com/python-guide",
        title="Getting Started with Python",
        text="Python is a widely used high-level programming language known for its clear syntax.",
        markdown="""# Getting Started with Python

Python is a widely used high-level programming language known for its clear syntax.

## Basic Syntax

Python uses indentation to define code blocks, making the code cleaner.
""",
        raw_html="<html>...</html>",
        article_html="<article>...</article>",
    )


# ============================================================
# Mock 对象 Fixtures
# ============================================================


@pytest.fixture
def mock_telegram_update() -> MagicMock:
    """创建模拟的 Telegram Update 对象。"""
    update = MagicMock()
    update.message = MagicMock()
    update.message.text = "请帮我总结这篇文章 https://example.com/article"
    update.message.reply_text = AsyncMock()
    update.message.reply_photo = AsyncMock()
    return update


@pytest.fixture
def mock_telegram_context() -> MagicMock:
    """创建模拟的 Telegram Context 对象。"""
    return MagicMock()


# ============================================================
# 路径相关 Fixtures
# ============================================================


@pytest.fixture
def fixtures_dir() -> Path:
    """返回 fixtures 目录路径。"""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_config_path(fixtures_dir: Path, tmp_path: Path) -> Path:
    """创建临时测试配置文件并返回路径。"""
    config_content = """
telegram:
  bot_token: "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"

llm:
  provider: openai
  api_key: "test-api-key-12345"
  model: "gpt-4o"

github:
  repo: "test-owner/test-repo"
  pat: "ghp_testtoken123456"
  branch: "main"
  target_dir: "notes"

http:
  fetch_mode: requests
  verify_ssl: true
"""
    config_path = tmp_path / "test_config.yaml"
    config_path.write_text(config_content, encoding="utf-8")
    return config_path


# ============================================================
# Pytest Hooks
# ============================================================


def pytest_addoption(parser: pytest.Parser) -> None:
    """注册 --run-functional 选项，用于控制真实功能测试执行。"""
    parser.addoption(
        "--run-functional",
        action="store_true",
        default=False,
        help="运行带 functional 标记的真实功能测试，默认跳过以避免调用外部服务",
    )


def pytest_configure(config: pytest.Config) -> None:
    """注册 pytest 标记。"""
    config.addinivalue_line(
        "markers",
        "functional: 需要外部服务（Telegram/LLM/GitHub 等）的真实功能测试",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """默认跳过 functional 测试，除非显式传入 --run-functional。"""
    if config.getoption("--run-functional"):
        return

    skip_marker = pytest.mark.skip(reason="缺少 --run-functional，因此跳过真实功能测试")
    for item in items:
        if "functional" in item.keywords:
            item.add_marker(skip_marker)
