"""使用 Camoufox 进行网页截图，复用 camoufox_helper 中的公共逻辑。"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import tempfile
import time
from pathlib import Path

from .camoufox_helper import _ensure_camoufox, _run_in_fresh_thread
from .structs import FetchError

logger = logging.getLogger(__name__)


def capture_screenshot(url: str, timeout: int = 15, full_page: bool = True) -> bytes:
    """使用 Camoufox 对目标网页截图并返回 PNG 字节。

    设计约束：
    - KISS：仅封装最小必要的截图流程，不做额外抽象。
    - YAGNI：当前仅支持全页截图和超时控制，不暴露更多可选项。
    - DRY：复用 camoufox_helper 中的浏览器初始化逻辑。
    """
    camoufox_cls, playwright_timeout_error = _ensure_camoufox()

    tmp_dir = Path(tempfile.gettempdir())
    screenshot_path = tmp_dir / f"websum_url2img_{int(time.time() * 1000)}.png"

    try:
        task = lambda: _capture_with_camoufox(  # noqa: E731
            camoufox_cls,
            playwright_timeout_error,
            url,
            timeout,
            full_page,
            screenshot_path,
        )
        try:
            loop = asyncio.get_running_loop()
            data = _run_in_fresh_thread(task) if loop.is_running() else task()
        except RuntimeError:
            data = task()
    finally:
        try:  # noqa: SIM105
            screenshot_path.unlink(missing_ok=True)
        except Exception:
            # 删除失败不影响主流程
            pass

    logger.info("Camoufox 截图完成: %s", url)
    return data


def _capture_with_camoufox(
    camoufox_cls: type,
    playwright_timeout_error: type[Exception] | None,
    url: str,
    timeout: int,
    full_page: bool,
    screenshot_path: Path,
) -> bytes:
    try:
        with camoufox_cls(
            geoip=True,
            config={"humanize": True, "humanize:maxTime": 1.5, "humanize:minTime": 0.5},
        ) as browser:
            page = browser.new_page()

            try:
                logger.info("Camoufox 截图导航: %s", url)
                response = page.goto(
                    url,
                    timeout=max(timeout, 1) * 1000,
                    wait_until="domcontentloaded",
                )

                # 加载等待 - 复用 camoufox_helper 中相同的等待模式
                if playwright_timeout_error:
                    with contextlib.suppress(playwright_timeout_error):
                        page.wait_for_load_state("load", timeout=8000)
                    with contextlib.suppress(playwright_timeout_error):
                        page.wait_for_load_state("networkidle", timeout=8000)

                # 额外等待一小段时间，确保懒加载内容完成
                time.sleep(2)
                page.wait_for_timeout(2000)

                if response and response.status >= 400:
                    status_text = getattr(response, "status_text", "") or ""
                    raise FetchError(f"Headless 截图失败: HTTP {response.status} {status_text}".strip())

                page.screenshot(path=str(screenshot_path), full_page=full_page)
            except FetchError:
                raise
            except Exception as exc:
                raise FetchError(f"Headless 截图过程中页面加载失败: {url}") from exc
            finally:
                page.close()

        return screenshot_path.read_bytes()
    except FetchError:
        raise
    except Exception as exc:  # pragma: no cover - 多种底层异常
        raise FetchError(f"Headless 截图失败: {url}") from exc
