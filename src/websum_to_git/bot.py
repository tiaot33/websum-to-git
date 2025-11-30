from __future__ import annotations

import asyncio
import logging
import re
import time
from io import BytesIO
from pathlib import Path

from telegram import InputFile, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import AppConfig, load_config
from .html_processor import HeadlessFetchError
from .pipeline import HtmlToObsidianPipeline
from .screenshot import capture_screenshot

logger = logging.getLogger(__name__)

URL_REGEX = re.compile(r"https?://[^\s]+", re.IGNORECASE)
HEARTBEAT_PATH = Path("/tmp/websum_bot_heartbeat")


def extract_first_url(text: str) -> str | None:
    match = URL_REGEX.search(text)
    return match.group(0) if match else None


class TelegramBotApp:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._pipeline = HtmlToObsidianPipeline(config)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        await update.message.reply_text("请发送包含 HTML 网页地址的消息，我会帮你摘要并同步到 GitHub。")

    async def url2img(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        if not update.message or not update.message.text:
            return

        text = update.message.text.strip()
        url = extract_first_url(text)
        if not url:
            await update.message.reply_text("未检测到有效的 http/https 地址，请在 /url2img 后附上网页链接。")
            return

        await update.message.reply_text("已收到链接，正在抓取网页并生成截图，请稍候……")

        try:
            image_bytes = await asyncio.to_thread(capture_screenshot, url)
        except HeadlessFetchError as exc:
            logger.exception("截图失败（Headless）: %s", url)
            await update.message.reply_text(f"截图失败（Headless 抓取异常）: {exc}")
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("处理 URL 截图失败: %s", url)
            await update.message.reply_text(f"截图失败: {exc}")
            return

        image_file = InputFile(BytesIO(image_bytes), filename="webpage_screenshot.png")
        try:
            await update.message.reply_photo(
                photo=image_file,
                caption=f"网页截图: {url}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("发送截图到 Telegram 失败: %s", url)
            await update.message.reply_text(f"截图已生成，但发送到 Telegram 时失败: {exc}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text:
            return

        text = update.message.text.strip()
        url = extract_first_url(text)
        if not url:
            await update.message.reply_text("未检测到有效的 http/https 地址，请发送包含 HTML 网页地址的文本。")
            return

        await update.message.reply_text("已收到链接，正在抓取网页并调用 LLM 总结，请稍候……")

        try:
            result = await asyncio.to_thread(self._pipeline.process_url, url)
        except Exception as exc:  # noqa: BLE001
            logger.exception("处理 URL 失败: %s", url)
            await update.message.reply_text(f"处理失败: {exc}")
            return

        message = f"处理完成，已将笔记保存到 GitHub 目录中的文件: {result.file_path}"
        if result.commit_hash:
            message += f"\nCommit: `{result.commit_hash}`"
        await update.message.reply_text(message)


async def heartbeat_job(context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG001
    HEARTBEAT_PATH.write_text(str(int(time.time())), encoding="utf-8")


def run_bot(config_path: str | Path = "config.yaml") -> None:
    config = load_config(config_path)
    app_config = config
    app = ApplicationBuilder().token(app_config.telegram.bot_token).build()

    bot_app = TelegramBotApp(app_config)

    app.add_handler(CommandHandler("start", bot_app.start))
    app.add_handler(CommandHandler("url2img", bot_app.url2img))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_app.handle_message))

    job_queue = app.job_queue
    if job_queue is None:
        raise RuntimeError("JobQueue is not configured")
    job_queue.run_repeating(heartbeat_job, interval=60, first=0)

    app.run_polling()
