from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import AppConfig, load_config
from .pipeline import HtmlToObsidianPipeline

logger = logging.getLogger(__name__)

URL_REGEX = re.compile(r"https?://[^\s]+", re.IGNORECASE)


def extract_first_url(text: str) -> str | None:
    match = URL_REGEX.search(text)
    return match.group(0) if match else None


class TelegramBotApp:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._pipeline = HtmlToObsidianPipeline(config)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text("请发送包含 HTML 网页地址的消息，我会帮你摘要并同步到 GitHub。")

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


def run_bot(config_path: str | Path = "config.yaml") -> None:
    config = load_config(config_path)
    app_config = config
    app = ApplicationBuilder().token(app_config.telegram.bot_token).build()

    bot_app = TelegramBotApp(app_config)

    app.add_handler(CommandHandler("start", bot_app.start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_app.handle_message))

    app.run_polling()
