from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Message, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from .config import AppConfig, load_config
from .fetchers import capture_screenshot, get_camoufox_browser_version
from .pipeline import HtmlToObsidianPipeline
from .task_queue import ChatTaskQueueFullError, Job, TaskQueueFullError, TaskScheduler
from .url_utils import strip_tracking_params

logger = logging.getLogger(__name__)

URL_REGEX = re.compile(r"https?://[^\s]+", re.IGNORECASE)
HEARTBEAT_PATH = Path("/tmp/websum_bot_heartbeat")

# Bot 命令定义
BOT_COMMANDS = [
    BotCommand("start", "开始使用 - 显示欢迎信息"),
    BotCommand("help", "帮助 - 显示可用命令列表"),
    BotCommand("status", "队列状态 - 查看当前排队/并发"),
    BotCommand("url2img", "网页截图 - 将网页转换为图片"),
]

HELP_TEXT = """📚 *WebSum Bot 命令列表*

/start - 开始使用，显示欢迎信息
/help - 显示此帮助信息
/status - 查看任务队列状态
/url2img <链接> - 将网页转换为截图

💡 *使用技巧*
• 直接发送网页链接即可自动总结并保存到 GitHub
• 多个任务会自动排队处理，可用 /status 查看状态
• 使用 /url2img 命令可以获取网页的完整截图"""


def extract_first_url(text: str) -> str | None:
    match = URL_REGEX.search(text)
    return strip_tracking_params(match.group(0)) if match else None


class TelegramBotApp:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._scheduler = TaskScheduler(
            max_concurrent_jobs=config.telegram.max_concurrent_jobs,
            max_queue_size=config.telegram.max_queue_size,
            max_queue_size_per_chat=config.telegram.max_queue_size_per_chat,
        )

    async def shutdown(self) -> None:
        await self._scheduler.shutdown()

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

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        if not update.message:
            return
        chat = update.effective_chat
        if not chat:
            return

        status = await self._scheduler.get_status(chat.id)
        text = (
            "📊 当前队列状态\n\n"
            f"全局：running {status.global_running}/{status.max_concurrent_jobs}，"
            f"pending {status.global_pending}/{status.max_queue_size}\n"
            f"本会话：running {status.chat_running}，pending {status.chat_pending}/{status.max_queue_size_per_chat}\n"
            f"Camoufox 浏览器版本：{get_camoufox_browser_version()}\n\n"
            "提示：直接发送 URL 或使用 /url2img 会自动入队排队处理。"
        )
        await update.message.reply_text(text)

    async def url2img(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG002
        if not update.message or not update.message.text:
            return

        text = update.message.text.strip()
        url = extract_first_url(text)
        if not url:
            await update.message.reply_text("未检测到有效的 http/https 地址，请在 /url2img 后附上网页链接。")
            return

        status_message = await update.message.reply_text("已接收截图任务，正在入队排队中……")

        bot = context.bot
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id is None:
            return

        async def on_start() -> None:
            await bot.edit_message_text(chat_id=chat_id, message_id=status_message.message_id, text="⏳ 开始生成截图……")

        async def on_success(image_bytes: bytes) -> None:
            image_file = InputFile(BytesIO(image_bytes), filename="webpage_screenshot.png")
            try:
                await bot.send_photo(chat_id=chat_id, photo=image_file, caption=f"网页截图: {url}")
                await bot.edit_message_text(
                    chat_id=chat_id, message_id=status_message.message_id, text="✅ 截图已生成并发送。"
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("发送截图到 Telegram 失败: %s", url)
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=status_message.message_id,
                    text=f"❌ 截图已生成，但发送到 Telegram 失败: {exc}",
                )

        async def on_failure(exc: Exception) -> None:
            logger.exception("截图失败: %s", url)
            msg = str(exc)
            if len(msg) > 1200:
                msg = msg[:1200] + "…"
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=f"❌ 截图失败: {msg}",
            )

        job = Job(
            job_id=str(uuid.uuid4()),
            chat_id=chat_id,
            status_message_id=status_message.message_id,
            created_at=datetime.now(),
            kind="screenshot",
            run=lambda: capture_screenshot(url),
            on_start=on_start,
            on_success=on_success,
            on_failure=on_failure,
        )

        try:
            pending_in_chat = await self._scheduler.enqueue(job)
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=f"✅ 截图任务已入队（本会话待处理: {pending_in_chat}）。你可发送 /status 查看队列状态。",
            )
        except (TaskQueueFullError, ChatTaskQueueFullError) as exc:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=f"⚠️ 队列已满，拒绝入队: {exc}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("截图任务入队失败: %s", url)
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=f"❌ 入队失败: {exc}",
            )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text:
            return

        text = update.message.text.strip()
        url = extract_first_url(text)
        if not url:
            await update.message.reply_text("未检测到有效的 http/https 地址，请发送包含 HTML 网页地址的文本。")
            return

        status_message = await update.message.reply_text("已接收任务，正在入队排队中……")

        bot = context.bot
        bot_data = context.bot_data
        chat_id = update.effective_chat.id if update.effective_chat else None
        if chat_id is None:
            return

        async def on_start() -> None:
            await bot.edit_message_text(chat_id=chat_id, message_id=status_message.message_id, text="⏳ 开始处理……")

        async def on_success(result: Any) -> None:
            # 运行函数返回类型由 job.kind 决定；这里按 pipeline 结果处理。
            # mypy/pyright 在此项目中不是强制，运行期安全由逻辑保证。
            pipeline_result = result

            # 根据是否进行了 LLM 总结，显示不同的状态
            if pipeline_result.summarized:
                message = f"✅ 处理完成\n\n📁 文件: `{pipeline_result.file_path}`"
            else:
                message = f"⚠️ 内容较短，已保存原文\n\n📁 文件: `{pipeline_result.file_path}`"

            if pipeline_result.commit_hash:
                message += f"\n🔖 Commit: `{pipeline_result.commit_hash[:7]}`"
            if pipeline_result.github_url:
                message += f"\n\n📂 [GitHub 查看]({pipeline_result.github_url})"

            # 添加删除按钮
            keyboard = None
            if pipeline_result.file_path and pipeline_result.commit_hash:
                request_id = str(uuid.uuid4())
                bot_data[f"del:{request_id}"] = pipeline_result.file_path
                keyboard = [[InlineKeyboardButton("🗑️ 删除本次提交", callback_data=f"del:{request_id}")]]

            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=message,
                parse_mode="Markdown",
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )

            # Telegraph 链接单独发送，启用链接预览
            if pipeline_result.telegraph_url:
                await bot.send_message(
                    chat_id=chat_id,
                    text=pipeline_result.telegraph_url,
                    disable_web_page_preview=False,
                )

        async def on_failure(exc: Exception) -> None:
            logger.exception("处理 URL 失败: %s", url)
            msg = str(exc)
            if len(msg) > 1200:
                msg = msg[:1200] + "…"
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=f"❌ 处理失败: {msg}",
                disable_web_page_preview=True,
            )

        def run() -> Any:
            pipeline = HtmlToObsidianPipeline(self._config)
            return pipeline.process_url(url)

        job = Job(
            job_id=str(uuid.uuid4()),
            chat_id=chat_id,
            status_message_id=status_message.message_id,
            created_at=datetime.now(),
            kind="summary",
            run=run,
            on_start=on_start,
            on_success=on_success,
            on_failure=on_failure,
        )

        try:
            pending_in_chat = await self._scheduler.enqueue(job)
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=f"✅ 任务已入队（本会话待处理: {pending_in_chat}）。你可发送 /status 查看队列状态。",
            )
        except (TaskQueueFullError, ChatTaskQueueFullError) as exc:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=f"⚠️ 队列已满，拒绝入队: {exc}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("任务入队失败: %s", url)
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message.message_id,
                text=f"❌ 入队失败: {exc}",
            )
            return

    async def handle_delete_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query:
            return

        await query.answer()

        if not query.message or not isinstance(query.message, Message):
            # 如果消息无法访问（例如已被删除），则不处理
            return

        data = query.data
        if not data or not data.startswith("del:"):
            return

        request_id = data.split(":", 1)[1]
        file_path = context.bot_data.get(f"del:{request_id}")

        if not file_path:
            # 此时 query.message 既然已确认是 Message，就可以放心访问 text
            await query.edit_message_text(text=f"{query.message.text}\n\n⚠️ 无法找到文件记录，可能已被清理。")
            return

        try:
            # 执行删除
            await asyncio.to_thread(HtmlToObsidianPipeline(self._config).delete_file, file_path)

            # 清理 bot_data
            del context.bot_data[f"del:{request_id}"]

            # 更新消息文本
            # 移除按钮，并追加已删除提示
            original_text = query.message.text_markdown
            if original_text:
                # 尝试保持原有格式，但 edit_message_text 有时对 markdown 支持有限制，简单追加即可
                new_text = f"{original_text}\n\n🗑️ *本次提交已删除*"
                await query.edit_message_text(text=new_text, parse_mode="Markdown", disable_web_page_preview=True)
            else:
                await query.edit_message_text(text="🗑️ 本次提交已删除")

        except Exception as exc:
            logger.exception("删除文件失败: %s", file_path)
            await query.edit_message_text(text=f"{query.message.text}\n\n❌ 删除失败: {exc}")


async def heartbeat_job(context: ContextTypes.DEFAULT_TYPE) -> None:  # noqa: ARG001
    HEARTBEAT_PATH.write_text(str(int(time.time())), encoding="utf-8")


async def post_init(application: Application) -> None:
    """Bot 启动后设置命令菜单"""
    await application.bot.set_my_commands(BOT_COMMANDS)
    logger.info("Bot 命令菜单已设置: %s", [cmd.command for cmd in BOT_COMMANDS])


def run_bot(config_path: str | Path = "config.yaml") -> None:
    config = load_config(config_path)
    app_config = config
    bot_app = TelegramBotApp(app_config)

    async def on_shutdown(application: Application) -> None:  # noqa: ARG001
        await bot_app.shutdown()

    app = (
        ApplicationBuilder()
        .token(app_config.telegram.bot_token)
        .post_init(post_init)
        .post_shutdown(on_shutdown)
        .build()
    )

    app.add_handler(CommandHandler("start", bot_app.start))
    app.add_handler(CommandHandler("help", bot_app.help_command))
    app.add_handler(CommandHandler("status", bot_app.status_command))
    app.add_handler(CommandHandler("url2img", bot_app.url2img))
    app.add_handler(CallbackQueryHandler(bot_app.handle_delete_callback, pattern="^del:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_app.handle_message))

    job_queue = app.job_queue
    if job_queue is None:
        raise RuntimeError("JobQueue is not configured")
    job_queue.run_repeating(heartbeat_job, interval=60, first=0)

    app.run_polling()
