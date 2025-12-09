"""URL 到 Fetcher 的路由与注册中心。

提供 `register_fetcher` 装饰器用于注册具体的 Fetcher 实现。
提供 `fetch` 函数作为统一入口。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import TYPE_CHECKING, Callable, TypeVar

from .base import BaseFetcher, FetchError, PageContent

if TYPE_CHECKING:
    from websum_to_git.config import AppConfig

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30
T = TypeVar("T", bound=type[BaseFetcher])


class FetcherRegistry:
    """Fetcher 注册中心。"""

    _registry: list[tuple[int, type[BaseFetcher]]] = []

    @classmethod
    def register(cls, priority: int = 0) -> Callable[[T], T]:
        """注册 Fetcher 的装饰器。

        Args:
            priority: 优先级，数字越大越先尝试。默认 0。
        """

        def decorator(fetcher_cls: T) -> T:
            cls._registry.append((priority, fetcher_cls))
            # 按优先级降序排序
            cls._registry.sort(key=lambda x: x[0], reverse=True)
            return fetcher_cls

        return decorator

    @classmethod
    def get_fetchers(cls) -> list[type[BaseFetcher]]:
        """获取所有已注册的 Fetcher 类，按优先级排序。"""
        return [f[1] for f in cls._registry]


# 公开装饰器
register_fetcher = FetcherRegistry.register


def _build_fetcher(fetcher_class: type[BaseFetcher], config: AppConfig) -> BaseFetcher:
    """根据配置构造具体 Fetcher 实例。

    这里包含一些特定于具体 Fetcher 的初始化逻辑（如 Token 注入）。
    为了完全解耦，未来可以让 Fetcher 自己处理 config，但目前保留此工厂逻辑。
    """
    # 动态检查是否是 GitHubFetcher，避免硬编码导入导致的循环依赖或耦合
    # 也可以让 Fetcher 接受 config 对象，或者 kwargs
    if fetcher_class.__name__ == "GitHubFetcher":
        return fetcher_class(  # type: ignore
            timeout=_DEFAULT_TIMEOUT,
            verify_ssl=config.http.verify_ssl,
            token=config.github.pat or None,
        )

    return fetcher_class(
        timeout=_DEFAULT_TIMEOUT,
        verify_ssl=config.http.verify_ssl,
    )


def fetch(
    url: str,
    config: AppConfig,
    fetchers: Iterable[type[BaseFetcher]] | None = None,
) -> PageContent:
    """抓取 URL 内容，按顺序尝试多个 Fetcher。"""
    candidates = tuple(fetchers) if fetchers is not None else FetcherRegistry.get_fetchers()
    last_error: Exception | None = None

    if not candidates:
        logger.warning("没有注册任何 Fetcher！")

    for fetcher_class in candidates:
        if not fetcher_class.can_handle(url):
            continue

        fetcher = _build_fetcher(fetcher_class, config)
        logger.info("URL '%s' 尝试 %s", url, fetcher_class.__name__)

        try:
            return fetcher.fetch(url)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("%s 处理失败: %s", fetcher_class.__name__, exc)
            continue

    if last_error:
        raise FetchError(f"所有抓取方式失败: {last_error}") from last_error

    raise FetchError(f"未找到可用的 Fetcher 处理 {url}")


class FetcherFactory:
    """向后兼容封装。"""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def fetch(self, url: str) -> PageContent:
        return fetch(url, self._config)
