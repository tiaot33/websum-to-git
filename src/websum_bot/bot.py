from __future__ import annotations

"""Telegram command wiring for the HTML→Markdown→GitHub flow."""

import asyncio
import logging
from functools import partial
from typing import Tuple

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from .command_parser import CommandOptions, parse_command_args
from .config import BotConfig
from .github_client import GithubClient, GithubError
from .html_extractor import HtmlFetchError, extract_content, fetch_html
from .llm_client import LLMClient, LLMError
from .markdown_note import NoteMeta, build_note, slugify


logger = logging.getLogger(__name__)


def _default_filename(meta: NoteMeta) -> str:
    slug = slugify(meta.title or meta.source_url, "note")
    ts = meta.created_at.strftime("%Y%m%d%H%M")
    return f"summary-{ts}-{slug}.md"


def _process_request(
    opts: CommandOptions,
    llm: LLMClient,
    gh: GithubClient,
) -> Tuple[str, str | None]:
    """CPU-bound pipeline: fetch → extract → LLM → frontmatter → commit."""
    html = fetch_html(opts.url)
    content = extract_content(opts.url, html)

    body = llm.summarize_markdown(content.markdown, title=content.title)

    meta = NoteMeta(
        title=content.title or opts.url,
        source_url=opts.url,
        created_at=content.fetched_at,
        tags=opts.tags,
        categories=opts.categories,
        keywords=opts.keywords,
    )
    note = build_note(meta, body)

    filename = opts.filename or _default_filename(meta)
    commit_msg = f"Add summary for {opts.url}"

    result = gh.commit_file(
        repo=opts.repo,
        path=filename,
        content=note,
        message=commit_msg,
        branch=opts.branch,
        author_name=opts.author_name,
        author_email=opts.author_email,
    )
    return result.path, result.commit_url


async def summarize_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, config: BotConfig, llm: LLMClient, gh: GithubClient) -> None:
    """Handle /summarize: parse params, run pipeline off-thread, render result."""
    if not update.effective_message:
        return

    if not context.args:
        await update.effective_message.reply_text(
            "用法: /summarize <url> [repo=owner/repo] [branch=branch] [filename=name.md] "
            "[author_name=Name] [author_email=email] [tags=a,b] [categories=c1,c2] [keywords=k1,k2]"
        )
        return

    try:
        opts = parse_command_args(context.args, config)
    except ValueError as exc:
        await update.effective_message.reply_text(f"参数错误: {exc}")
        return

    status_msg = await update.effective_message.reply_text("处理中，请稍候…")

    loop = asyncio.get_running_loop()
    try:
        path, commit_url = await loop.run_in_executor(
            None, partial(_process_request, opts, llm, gh)
        )
        result_text = f"✅ 已提交笔记到 {opts.repo}:{opts.branch} 路径 `{path}`"
        if commit_url:
            result_text += f"\n提交: {commit_url}"
        await status_msg.edit_text(result_text)
    except (HtmlFetchError, LLMError, GithubError) as exc:
        logger.exception("Failed to process summarize request")
        await status_msg.edit_text(f"❌ 处理失败: {exc}")


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Simple greeting/usage handler."""
    if not update.effective_message:
        return
    await update.effective_message.reply_text("发送 /summarize <url> 来生成并提交Markdown笔记。")


def create_application(config: BotConfig) -> ApplicationBuilder:
    """Build a configured telegram Application with handlers wired."""
    llm = LLMClient(config.llm)
    gh = GithubClient(config.github)

    app = ApplicationBuilder().token(config.telegram_token).build()
    summarize_cb = partial(summarize_handler, config=config, llm=llm, gh=gh)
    app.add_handler(CommandHandler("summarize", summarize_cb))
    app.add_handler(CommandHandler("start", start_handler))
    return app
