"""Camoufox 公共封装，供需要浏览器抓取的 Fetcher 复用。"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from typing import Any

from .structs import FetchError

logger = logging.getLogger(__name__)

_camoufox_cls: type | None = None
_playwright_timeout_error: type[Exception] | None = None


def _ensure_camoufox() -> tuple[type, type[Exception] | None]:
    """惰性加载 Camoufox/Playwright，避免重复样板。"""

    global _camoufox_cls, _playwright_timeout_error

    if _camoufox_cls is None:
        try:
            from camoufox.sync_api import Camoufox

            _camoufox_cls = Camoufox
        except ModuleNotFoundError as exc:  # pragma: no cover - 运行期缺依赖
            raise FetchError(
                "Camoufox 未安装，请执行 `pip install -U camoufox[geoip]` 并运行 `python -m camoufox fetch`"
            ) from exc

    if _playwright_timeout_error is None:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

            _playwright_timeout_error = PlaywrightTimeoutError
        except ModuleNotFoundError:  # pragma: no cover - 理论上随 camoufox 安装
            _playwright_timeout_error = None

    return _camoufox_cls, _playwright_timeout_error


def fetch_with_camoufox(
    url: str,
    *,
    timeout: int,
    wait_selector: str | None = None,
    scroll: bool = True,
    post_process: Callable[[Any], None] | None = None,
    extract: Callable[[Any], Any] | None = None,
) -> tuple[str, str, Any | None]:
    """启动 Camoufox 抓取页面并返回 HTML/最终 URL/自定义数据。

    Args:
        url: 目标 URL
        timeout: 超时时间（秒）
        wait_selector: 可选，等待指定 selector 出现
        scroll: 是否滚动页面以触发懒加载
        post_process: 可选，对页面执行额外处理（如移除弹窗）
        extract: 可选，从页面提取结构化数据
    """

    camoufox_cls, playwright_timeout_error = _ensure_camoufox()

    try:
        with camoufox_cls(
            geoip=True,
            config={"humanize": True, "humanize:maxTime": 1.5, "humanize:minTime": 0.5},
        ) as browser:
            page = browser.new_page()

            try:
                logger.info("Camoufox 导航: %s", url)
                response = page.goto(
                    url,
                    timeout=max(timeout, 1) * 1000,
                    wait_until="domcontentloaded",
                )

                if response and response.status >= 400:
                    status_text = getattr(response, "status_text", "") or ""
                    raise FetchError(f"HTTP {response.status} {status_text}".strip())

                # 加载等待
                if playwright_timeout_error:
                    with contextlib.suppress(playwright_timeout_error):
                        page.wait_for_load_state("load", timeout=8000)
                    with contextlib.suppress(playwright_timeout_error):
                        page.wait_for_load_state("networkidle", timeout=8000)

                if wait_selector and playwright_timeout_error:
                    with contextlib.suppress(playwright_timeout_error):
                        page.wait_for_selector(wait_selector, timeout=15000)

                if post_process:
                    post_process(page)

                if scroll:
                    page.evaluate(
                        """
                        () => {
                            return new Promise((resolve) => {
                                const step = window.innerHeight / 2 || 400;
                                const maxIterations = 50;
                                let position = 0;
                                let iterations = 0;

                                const scrollStep = () => {
                                    const maxScroll = Math.max(
                                        document.body.scrollHeight,
                                        document.documentElement.scrollHeight,
                                        0
                                    );
                                    iterations++;
                                    if (position < maxScroll && iterations < maxIterations) {
                                        window.scrollTo(0, position);
                                        position += step;
                                        setTimeout(scrollStep, 300 + Math.random() * 500);
                                    } else {
                                        window.scrollTo(0, maxScroll);
                                        resolve();
                                    }
                                };
                                scrollStep();
                            });
                        }
                        """
                    )
                    page.wait_for_timeout(3000)

                data = extract(page) if extract else None
                html = page.content()
                final_url = page.url
                logger.info("Camoufox 抓取完成, 最终 URL: %s, HTML 长度: %d", final_url, len(html))

            except FetchError:
                raise
            except Exception as exc:  # pragma: no cover - 具体异常在上层处理
                raise FetchError(f"页面加载失败: {url}") from exc
            finally:
                page.close()

    except FetchError:
        raise
    except Exception as exc:  # pragma: no cover
        raise FetchError(f"Headless 抓取失败: {url}") from exc

    return html, final_url, data
