"""自定义/零散 Headless 策略集中存放模块。

建议将体量较小、一次性或简单配置类的网站策略集中写在这里，
避免为每个小站点单独创建文件。

使用方式与其他策略模块一致，例如：

    from .registry import route

    @route("example.com", wait_selector="#content", timeout=60, scroll=False)
    def process_example(page):
        ...
"""

from __future__ import annotations

import logging
from typing import Any

from .registry import route

logger = logging.getLogger(__name__)


@route("t.me", scroll=False)
def process_telegram(page: Any) -> None:
    """
    处理 Telegram 消息嵌入页面。
    移除底部的 widget_actions_wrap 横幅（包含 "Open in Telegram" 等按钮）。
    """
    banner = page.query_selector("#widget_actions_wrap")
    if banner:
        banner.evaluate("el => el.remove()")
        logger.debug("已移除 Telegram 底部横幅 #widget_actions_wrap")


@route("huggingface.co", scroll=False)
@route("hf.space", scroll=False)
def process_huggingface(page: Any) -> None:
    """
    处理 HuggingFace 页面。
    如果检测到 Spaces 应用 iframe (通常在 .space-iframe)，
    直接跳转到 iframe 的 src URL，以便通用提取器能获取真实的应用内容。
    否则什么都不做，按普通页面处理。
    """
    # 尝试查找 Spaces iframe
    # 不使用 wait_for_selector，避免非 Spaces 页面超时
    iframe = page.query_selector("iframe.space-iframe")
    if not iframe:
        logger.debug("当前 HuggingFace 页面未检测到 Space iframe，跳过重定向")
        return

    src = iframe.get_attribute("src")
    if not src:
        logger.debug("检测到 iframe.space-iframe 但未找到 src 属性")
        return

    logger.info("检测到 HuggingFace Space iframe，正在重定向至: %s", src)
    try:
        # 使用 goto 跳转到 iframe 内容页。此处不再依赖滚动脚本，避免 page.evaluate
        # 在部分 Space 中触发 TargetClosedError。
        page.goto(src, wait_until="domcontentloaded")
    except Exception as exc:  # noqa: BLE001
        # 不让单个 Space 的导航失败直接中断整个抓取流程，由外层统一处理。
        logger.warning("跳转至 HuggingFace Space 失败，将回退为原页面内容: %s", exc)
