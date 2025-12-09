from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, NamedTuple, cast

from websum_to_git.fetchers.structs import HeadlessConfig, PageContent

# 浏览器页面对象类型 (Playwright Page)
Page = Any

logger = logging.getLogger(__name__)


class HeadlessRoute(NamedTuple):
    """Headless 抓取路由定义。"""

    matcher: Callable[[str], bool]
    config: HeadlessConfig
    process_page: Callable[[Page], None] | None = None
    extract: Callable[[Page], Any] | None = None
    build_content: Callable[[str, str, str, Any], PageContent] | None = None


# 全局路由表
_ROUTES: list[HeadlessRoute] = []


def route(
    pattern: str | Callable[[str], bool],
    timeout: int | None = None,
    wait_selector: str | None = None,
    scroll: bool = True,
):
    """注册 Headless 抓取策略的装饰器。

    支持装饰函数（仅 process_page）或类（包含 process/extract/build 静态方法）。

    Args:
        pattern: 域名字符串 (如 "twitter.com") 或 匹配函数。
            - 当为字符串时，内部使用 ``pattern in url`` 做子串匹配；
            - 当为函数时，应接受完整 URL 字符串并返回 bool，用于自定义匹配规则。
        timeout: 自定义超时
        wait_selector: 等待的选择器
        scroll: 是否滚动
    """

    def decorator(obj):
        matcher = (lambda u: pattern in u) if isinstance(pattern, str) else pattern
        config = HeadlessConfig(timeout=timeout, wait_selector=wait_selector, scroll=scroll)

        process_page: Callable[[Page], None] | None = None
        extract = None
        build_content = None

        if isinstance(obj, type):
            # 类装饰器模式
            process_attr = getattr(obj, "process", None)
            if process_attr is not None:
                process_page = cast(Callable[[Page], None], process_attr)
            extract = getattr(obj, "extract", None)
            build_content = getattr(obj, "build", None)
        elif callable(obj):
            # 函数装饰器模式 (默认为 process_page)
            process_page = cast(Callable[[Page], None], obj)

        # 注册路由
        r = HeadlessRoute(
            matcher=matcher,
            config=config,
            process_page=process_page,
            extract=extract,
            build_content=build_content,
        )
        _ROUTES.append(r)
        logger.debug("已注册 Headless 策略: %s (pattern=%s)", obj.__name__, pattern)
        return obj

    return decorator


def get_route(url: str) -> HeadlessRoute | None:
    """获取匹配当前 URL 的路由。"""
    for route in _ROUTES:
        if route.matcher(url):
            return route
    return None
