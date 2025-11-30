from __future__ import annotations

import tempfile
import time
from pathlib import Path

from .html_processor import HeadlessFetchError


def capture_screenshot(url: str, timeout: int = 15, full_page: bool = True) -> bytes:
    """使用 Camoufox 对目标网页截图并返回 PNG 字节。

    设计约束：
    - KISS：仅封装最小必要的截图流程，不做额外抽象。
    - YAGNI：当前仅支持全页截图和超时控制，不暴露更多可选项。
    - DRY：沿用 html_processor 中的 HeadlessFetchError，统一 headless 错误类型。
    """
    try:
        from camoufox.sync_api import Camoufox
    except ModuleNotFoundError as exc:  # pragma: no cover - 运行期缺依赖
        raise HeadlessFetchError(
            "Camoufox 未安装，请执行 `pip install -U camoufox[geoip]` 并运行 `python -m camoufox fetch`"
        ) from exc

    tmp_dir = Path(tempfile.gettempdir())
    screenshot_path = tmp_dir / f"websum_url2img_{int(time.time() * 1000)}.png"

    try:
        from camoufox.sync_api import Camoufox  # type: ignore[no-redef]

        with Camoufox(
            geoip=True,
            config={"humanize": True, "humanize:maxTime": 1.5, "humanize:minTime": 0.5},
        ) as browser:
            page = browser.new_page()

            try:
                response = page.goto(
                    url,
                    timeout=max(timeout, 1) * 1000,
                    wait_until="domcontentloaded",
                )

                try:  # noqa: SIM105
                    page.wait_for_load_state("load", timeout=8000)
                except Exception:
                    pass
                try:  # noqa: SIM105
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass

                # 额外等待一小段时间，确保懒加载内容完成
                time.sleep(2)
                page.wait_for_timeout(2000)

                if response and response.status >= 400:
                    status_text = getattr(response, "status_text", "") or ""
                    raise HeadlessFetchError(f"Headless 截图失败: HTTP {response.status} {status_text}".strip())

                page.screenshot(path=str(screenshot_path), full_page=full_page)
            except HeadlessFetchError:
                raise
            except Exception as exc:
                raise HeadlessFetchError(f"Headless 截图过程中页面加载失败: {url}") from exc

        data = screenshot_path.read_bytes()
    except HeadlessFetchError:
        raise
    except Exception as exc:  # pragma: no cover - 多种底层异常
        raise HeadlessFetchError(f"Headless 截图失败: {url}") from exc
    finally:
        try:  # noqa: SIM105
            screenshot_path.unlink(missing_ok=True)
        except Exception:
            # 删除失败不影响主流程
            pass

    return data
