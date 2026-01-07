"""Telegram t.me 策略 (基于 Headless)。"""

from __future__ import annotations

import logging
from typing import Any, cast

from websum_to_git.fetchers.structs import PageContent

from .registry import route

logger = logging.getLogger(__name__)


@route("t.me", scroll=False)
class TelegramStrategy:
    """Telegram 消息嵌入页面抓取策略。"""

    @staticmethod
    def process(page: Any) -> None:
        """移除底部横幅等干扰元素。"""
        page.evaluate(
            """
            () => {
                // 移除底部 widget_actions_wrap 横幅（包含 "Open in Telegram" 等按钮）
                const actionsWrap = document.getElementById('widget_actions_wrap');
                if (actionsWrap) actionsWrap.remove();

                // 移除页脚
                const footer = document.querySelector('.tgme_widget_message_footer');
                if (footer) footer.remove();
            }
            """
        )

    @staticmethod
    def extract(page: Any) -> dict:
        """从页面提取消息数据，只保留 tgme_widget_message_text。"""
        return page.evaluate(
            """
            () => {
                const data = {
                    text: '',
                    author_name: '',
                    author_link: '',
                    datetime: '',
                    views: ''
                };

                // 提取消息正文
                const textEl = document.querySelector('.tgme_widget_message_text');
                if (textEl) {
                    data.text = textEl.innerHTML;
                }

                // 提取作者信息
                const authorEl = document.querySelector('.tgme_widget_message_owner_name');
                if (authorEl) {
                    data.author_name = authorEl.textContent || '';
                    const link = authorEl.querySelector('a');
                    if (link) data.author_link = link.getAttribute('href') || '';
                }

                // 提取时间
                const timeEl = document.querySelector('.tgme_widget_message_date time');
                if (timeEl) {
                    data.datetime = timeEl.getAttribute('datetime') || timeEl.textContent || '';
                }

                // 提取浏览量
                const viewsEl = document.querySelector('.tgme_widget_message_views');
                if (viewsEl) {
                    data.views = viewsEl.textContent || '';
                }

                return data;
            }
            """
        )

    @staticmethod
    def build(url: str, final_url: str, html: str, data: Any) -> PageContent:
        """构建 PageContent。"""
        msg_data = cast(dict[str, Any], data or {})

        text = msg_data.get("text", "")
        author_name = msg_data.get("author_name", "Telegram")
        author_link = msg_data.get("author_link", "")
        datetime_str = msg_data.get("datetime", "")
        views = msg_data.get("views", "")

        # 标题：截取前50字符
        text_preview = text[:50] + "..." if len(text) > 50 else text
        # 移除 HTML 标签用于标题
        import re
        text_plain = re.sub(r"<[^>]+>", "", text_preview)
        title = f"{author_name}: {text_plain}" if author_name else text_plain

        markdown_parts = []

        # 消息正文（保留原始 HTML 转换为 Markdown）
        if text:
            # 简单处理：将 <br> 转换为换行
            text_md = text.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
            text_md = re.sub(r"<[^>]+>", "", text_md)  # 移除其他 HTML 标签
            markdown_parts.append(f"> {text_md}\n")

        # 作者信息
        if author_name:
            if author_link:
                markdown_parts.append(f"**频道**: [{author_name}]({author_link})")
            else:
                markdown_parts.append(f"**频道**: {author_name}")

        # 时间
        if datetime_str:
            markdown_parts.append(f"**发布时间**: {datetime_str}")

        # 浏览量
        if views:
            markdown_parts.append(f"**浏览量**: {views}")

        markdown_parts.append("")
        markdown_parts.append(f"[查看原消息]({url})")

        # 纯文本版本
        plain_text = re.sub(r"<[^>]+>", "", text) if text else ""

        return PageContent(
            url=url,
            final_url=final_url,
            title=title,
            text=plain_text,
            markdown="\n".join(markdown_parts),
            raw_html=html,
            article_html=f"<article><div class='tgme_widget_message_text'>{text}</div></article>",
        )
