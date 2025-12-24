"""Camoufox 公共封装，供需要浏览器抓取的 Fetcher 复用。"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections.abc import Callable
from typing import Any, TypeVar

from .structs import FetchError

logger = logging.getLogger(__name__)

_camoufox_cls: type | None = None
_playwright_timeout_error: type[Exception] | None = None
T = TypeVar("T")


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


def _auto_scroll(
    page: Any,
    step: int | None = None,
    max_iterations: int = 50,
    base_delay_ms: int = 300,
) -> None:
    """自动滚动 API，将配置参数透传给 JS 执行。

    Args:
        page: Playwright/Camoufox Page 对象
        step: 每次滚动的像素步长。默认 None (使用视口高度的一半)
        max_iterations: 最大滚动次数
        base_delay_ms: 每次滚动的基本等待时间(ms)
    """
    # 使用 Python 参数注入 JS，而不是拼接字符串
    js_script = """
    async ({ step, maxIterations, baseDelay }) => {
        return new Promise((resolve) => {
            // 如果未指定 step，则使用视口高度的一半，或默认 400
            const scrollStep = step || (window.innerHeight / 2) || 400;
            let position = 0;
            let iterations = 0;

            const scrollLoop = () => {
                const maxScroll = Math.max(
                    document.body.scrollHeight,
                    document.documentElement.scrollHeight,
                    0
                );
                
                iterations++;
                
                // 判断是否还有滚动空间以及是否达到最大迭代次数
                if (position < maxScroll && iterations < maxIterations) {
                    window.scrollTo(0, position);
                    position += scrollStep;
                    
                    // 随机化延迟，模拟人类行为
                    const randomDelay = Math.random() * 500;
                    setTimeout(scrollLoop, baseDelay + randomDelay);
                } else {
                    // 确保最后滚动到底部
                    window.scrollTo(0, maxScroll);
                    resolve();
                }
            };
            scrollLoop();
        });
    }
    """  # noqa: W293

    try:
        # 传递参数字典给 evaluate
        page.evaluate(js_script, {"step": step, "maxIterations": max_iterations, "baseDelay": base_delay_ms})
    except Exception as e:
        logger.warning("页面滚动执行出错 (非致命): %s", e)


def _run_in_fresh_thread(task: Callable[[], T]) -> T:
    """在新线程执行 Camoufox 任务，隔离已有事件循环。"""

    result: dict[str, Any] = {}

    def runner() -> None:
        try:
            result["value"] = task()
        except BaseException as exc:  # noqa: BLE001
            result["error"] = exc

    thread = threading.Thread(target=runner, name="camoufox-worker", daemon=True)
    thread.start()
    thread.join()

    if "error" in result:
        raise result["error"]  # type: ignore[misc]
    return result["value"]  # type: ignore[return-value]


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

    def task() -> tuple[str, str, Any | None]:
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
                        # 使用封装的滚动策略
                        _auto_scroll(page, max_iterations=50)
                        # 给赖加载内容一点额外的渲染时间
                        page.wait_for_timeout(2000)

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

    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            return _run_in_fresh_thread(task)
    except RuntimeError:
        pass

    return task()


def remove_overlays(page: Any) -> None:
    """移除常见的遮挡元素，如 Cookie 提示、弹窗、广告等。

    Args:
        page: Playwright Page 对象
    """
    logger.info("尝试移除页面悬浮窗和干扰元素")

    # 1. 尝试点击 "接受/同意" 按钮
    try:
        page.evaluate(
            """() => {
                const keywords = [
                    "accept", "accept all", "accept cookies", "agree", "i agree", "allow", "allow all", "consent",
                    "接受", "同意", "允许", "全部接受", "此时接受", "知道了", "ok", "got it"
                ];

                // 查找可能的按钮元素
                const candidates = Array.from(document.querySelectorAll('button, a, div[role="button"], input[type="button"], input[type="submit"], div[class*="button"], span[class*="button"]'));
                for (const el of candidates) {
                    // 忽略不可见元素
                    if (el.offsetParent === null) continue;
                    const text = (el.innerText || el.textContent || "").trim().toLowerCase();
                    // 检查文本是否匹配关键词
                    // 优先完全匹配，或者是关键词加上简单的符号
                    if (keywords.some(k => text === k || text === k + "!" || text === k + ".")) {
                        console.log("Found connect button:", text);
                        el.click();
                        return; // 点击一个后通常页面会刷新或弹窗消失，不仅需点击多个
                    }
                }
            }"""  # noqa: E501
        )
        # 点击后等待一小段时间，让页面响应（如设置 cookie 并移除遮罩）
        page.wait_for_timeout(1000)
    except Exception as e:
        logger.warning("尝试点击 Cookie 接受按钮时出错 (忽略): %s", e)

    # 2. 移除常见干扰元素选择器
    selectors = [
        "#onetrust-banner-sdk",  # OneTrust Cookie Banner
        ".fc-consent-root",  # Funding Choices
        "#cookie-banner",
        ".cookie-banner",
        "#cookies-banner",
        ".cookies-banner",
        "[id*='cookie-consent']",
        "[class*='cookie-consent']",
        "[id*='cookie-notice']",
        "[class*='cookie-notice']",
        ".cc-banner",  # Cookie Consent
        ".cc-window",
        ".adsbygoogle",  # Google Ads
        ".ad-container",
        "div[class*='popup'][style*='fixed']",  # 简单的通用弹窗匹配
        "div[class*='modal'][style*='fixed']",
    ]

    try:
        # 注入 JS 移除元素
        page.evaluate(
            """(selectors) => {
                selectors.forEach(selector => {
                    try {
                        const elements = document.querySelectorAll(selector);
                        elements.forEach(el => {
                            // 简单的安全检查：避免删除过大的区域（可能是正文）
                            // 这里只是简单判断，如果需要更安全可以检查文本量
                            if (el.innerText.length < 2000) {
                                el.remove();
                            }
                        });
                    } catch (e) {
                        // 忽略单个选择器的错误
                    }
                });
            }""",
            selectors,
        )
        logger.info("悬浮窗移除脚本执行完毕")
    except Exception as e:
        logger.warning("移除悬浮窗时发生错误: %s", e)
