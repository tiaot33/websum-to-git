from __future__ import annotations

import asyncio
import logging
import re
import time
from io import BytesIO
from pathlib import Path

from telegram import BotCommand, InputFile, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import AppConfig, load_config
from .fetchers import FetchError, capture_screenshot
from .pipeline import HtmlToObsidianPipeline

logger = logging.getLogger(__name__)

URL_REGEX = re.compile(r"https?://[^\s]+", re.IGNORECASE)
HEARTBEAT_PATH = Path("/tmp/websum_bot_heartbeat")

# Bot 命令定义
BOT_COMMANDS = [
    BotCommand("start", "开始使用 - 显示欢迎信息"),
    BotCommand("help", "帮助 - 显示可用命令列表"),
    BotCommand("url2img", "网页截图 - 将网页转换为图片"),
]

HELP_TEXT = """📚 *WebSum Bot 命令列表*

/start - 开始使用，显示欢迎信息
/help - 显示此帮助信息
/url2img <链接> - 将网页转换为截图

💡 *使用技巧*
• 直接发送网页链接即可自动总结并保存到 GitHub
• 使用 /url2img 命令可以获取网页的完整截图"""


def extract_first_url(text: str) -> str | None:
    match = URL_REGEX.search(text)
    return match.group(0) if match else None


class TelegramBotApp:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._pipeline = HtmlToObsidianPipeline(config)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        if not update.message:
            return
        welcome_text = (
            "👋 欢迎使用 WebSum Bot！\n\n"
            "请发送包含网页地址的消息，我会帮你：\n"
            "• 自动抓取网页内容\n"
            "• 使用 AI 生成摘要\n"
            "• 同步笔记到 GitHub\n\n"
            "输入 /help 查看所有可用命令"
        )
        await update.message.reply_text(welcome_text)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        if not update.message:
            return
        await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")

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
        except FetchError as exc:
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

        # 根据是否进行了 LLM 总结，显示不同的状态
        if result.summarized:
            message = f"✅ 处理完成\n\n📁 文件: `{result.file_path}`"
        else:
            message = f"⚠️ 内容较短，已保存原文\n\n📁 文件: `{result.file_path}`"

        if result.commit_hash:
            message += f"\n🔖 Commit: `{result.commit_hash[:7]}`"
        if result.github_url:
            message += f"\n\n📂 [GitHub 查看]({result.github_url})"
        if result.telegraph_url:
            message += f"\n📖 [Telegraph 预览]({result.telegraph_url})"
        await update.message.reply_text(message, parse_mode="Markdown", disable_web_page_preview=True)


async def heartbeat_job(context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG001
    HEARTBEAT_PATH.write_text(str(int(time.time())), encoding="utf-8")


async def post_init(application: Application) -> None:
    """Bot 启动后设置命令菜单"""
    await application.bot.set_my_commands(BOT_COMMANDS)
    logger.info("Bot 命令菜单已设置: %s", [cmd.command for cmd in BOT_COMMANDS])


def run_bot(config_path: str | Path = "config.yaml") -> None:
    config = load_config(config_path)
    app_config = config
    app = ApplicationBuilder().token(app_config.telegram.bot_token).post_init(post_init).build()

    bot_app = TelegramBotApp(app_config)

    app.add_handler(CommandHandler("start", bot_app.start))
    app.add_handler(CommandHandler("help", bot_app.help_command))
    app.add_handler(CommandHandler("url2img", bot_app.url2img))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_app.handle_message))

    job_queue = app.job_queue
    if job_queue is None:
        raise RuntimeError("JobQueue is not configured")
    job_queue.run_repeating(heartbeat_job, interval=60, first=0)

    app.run_polling()
