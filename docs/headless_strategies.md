# Headless Fetcher 策略指南

WebSum-To-Git 支持使用基于 Camoufox (Headless Firefox) 的浏览器抓取方案。为了灵活应对不同网站的特殊反爬虫机制、弹窗干扰或动态加载逻辑，我们引入了 **Headless Strategy 注册表**。

本文档将指导开发者如何为特定网站添加自定义抓取策略。

## 架构概览

- **HeadlessFetcher**: 通用入口，负责启动浏览器、管理上下文。
- **Registry (`headless_strategies`)**: 维护域名与策略的映射关系。
- **Strategy**: 包含特定网站的配置（如超时、等待选择器）和生命周期钩子（预处理、提取、构建）。

## 快速上手：添加新策略

所有策略代码位于 `src/websum_to_git/fetchers/headless_strategies/` 目录下。

### 1. 创建策略文件

在 `src/websum_to_git/fetchers/headless_strategies/` 中创建一个新文件，例如 `example.py`。

### 2. 使用 `@route` 装饰器

你可以通过 `@route` 装饰器注册一个策略。支持两种模式：**函数模式**（简单预处理）和 **类模式**（完全控制）。

#### 简单模式：仅参数配置与预处理

适用于只需调整超时、等待元素或点击某个按钮（如接受 Cookie）的场景。

```python
from .registry import route

# 注册 url 包含 "example.com" 的请求
# 配置：等待 #content 元素出现，超时 60秒，禁用滚动
@route("example.com", wait_selector="#content", timeout=60, scroll=False)
def process_example(page):
    """
    可选的预处理函数。
    page 是 Playwright 的 Page 对象。
    """
    # 例如：点击同意按钮
    try:
        page.click("#accept-cookies-btn", timeout=2000)
    except Exception:
        pass
```

#### 高级模式：完全控制

适用于需要自定义数据提取逻辑（非通用 Readability 提取）或自定义 Markdown 构建逻辑的复杂场景（如 Twitter/X）。

```python
from typing import Any
from websum_to_git.fetchers.structs import PageContent
from .registry import route

@route("complex-site.com")
class ComplexStrategy:
    
    @staticmethod
    def process(page):
        """1. 预处理：移除遮罩、滚动加载等"""
        page.evaluate("document.querySelector('.modal').remove()")

    @staticmethod
    def extract(page) -> dict[str, Any]:
        """2. 数据提取：从页面 DOM 提取结构化数据"""
        # 返回的数据将传递给 build 方法
        return page.evaluate("() => { return { title: document.title, ... } }")

    @staticmethod
    def build(url: str, final_url: str, html: str, data: Any) -> PageContent:
        """3. 内容构建：将提取的数据转换为 PageContent 对象"""
        custom_data = data or {}
        return PageContent(
            url=url,
            final_url=final_url,
            title=custom_data.get("title", "No Title"),
            text="...",
            markdown="...",
            raw_html=html,
            article_html="...",
        )
```

### 3. 注册策略

确保你的新模块被导入。如果是在 `headless_strategies` 包内新建的文件，需要在 `src/websum_to_git/fetchers/headless_strategies/__init__.py` 中导入它：

```python
# src/websum_to_git/fetchers/headless_strategies/__init__.py

from .registry import get_route, route
from . import twitter
from . import example  # <--- 新增
```

## 配置项详解 (`HeadlessConfig`)

`@route` 装饰器接受以下关键字参数，直接对应 `HeadlessConfig` 模型：

- `timeout` (int | None): 抓取超时时间（秒）。如果不设置，默认为全局 HTTP 配置。
- `wait_selector` (str | None): 页面加载后额外等待出现的 CSS 选择器。
- `scroll` (bool): 是否执行自动滚动以触发懒加载。默认为 `True`。

## 生命周期

1. **Match**: `fetch_headless` 根据 URL 在注册表中查找匹配的策略。
2. **Setup**: 使用策略配置的 `timeout` 等参数启动抓取。
3. **Process**: 页面加载完成后（`domcontentloaded`），调用策略的 `process` (或装饰的函数)。
4. **Extract**: 调用策略的 `extract` 方法获取结构化数据（可选，默认为 None）。
5. **Build**: 
   - 如果有 `build` 方法，调用它生成 `PageContent`。
   - 否则，使用默认的 `extract_article` (Readability) 生成 `PageContent`。
