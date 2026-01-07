"""Telegram t.me 策略 (基于 Headless)。"""

from __future__ import annotations

import logging
from typing import Any, cast

from websum_to_git.fetchers.structs import PageContent

from .registry import route

logger = logging.getLogger(__name__)


@route("t.me", scroll=False)
class TelegramStrategy:
    """Telegram 消息嵌入页面抓取策略。

    Telegram 消息页面的内容位于 iframe 内部，需要进入 iframe 才能提取。
    """

    @staticmethod
    def extract(page: Any) -> dict:
        """从 iframe 内部提取消息数据。

        Telegram 页面结构：主页面包含一个 iframe，真正的消息内容在 iframe 内。
        """
        data = {
            "text": "",
            "author_name": "",
            "author_link": "",
            "datetime": "",
            "views": "",
            "link_preview": None,  # 链接预览卡片
        }

        # 获取所有 frames，找到包含消息内容的 iframe
        frames = page.frames
        logger.debug("页面共有 %d 个 frames", len(frames))

        # 遍历所有 frame 查找消息内容
        for frame in frames:
            try:
                frame_url = frame.url
                logger.debug("检查 frame: %s", frame_url)

                # Telegram embed iframe 的 URL 通常包含 embed=1 或是 /s/ 路径
                # 直接尝试在每个 frame 中查找消息元素
                result = frame.evaluate(
                    """
                    () => {
                        const data = {
                            text: '',
                            author_name: '',
                            author_link: '',
                            datetime: '',
                            views: '',
                            link_preview: null,
                            found: false
                        };

                        // 提取消息正文
                        const textEl = document.querySelector('.tgme_widget_message_text');
                        if (textEl) {
                            data.text = textEl.innerHTML;
                            data.found = true;
                        }

                        // 提取链接预览卡片
                        const linkPreview = document.querySelector('.tgme_widget_message_link_preview');
                        if (linkPreview) {
                            const preview = {
                                url: linkPreview.getAttribute('href') || '',
                                site_name: '',
                                title: '',
                                description: ''
                            };

                            // 网站名称 (如 "X (formerly Twitter)")
                            const siteEl = linkPreview.querySelector('.link_preview_site_name');
                            if (siteEl) preview.site_name = siteEl.textContent || '';

                            // 标题
                            const titleEl = linkPreview.querySelector('.link_preview_title');
                            if (titleEl) preview.title = titleEl.textContent || '';

                            // 描述
                            const descEl = linkPreview.querySelector('.link_preview_description');
                            if (descEl) preview.description = descEl.textContent || '';

                            data.link_preview = preview;
                            data.found = true;
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

                if result.get("found"):
                    logger.info("在 frame [%s] 中找到 Telegram 消息内容", frame_url)
                    data["text"] = result.get("text", "")
                    data["author_name"] = result.get("author_name", "")
                    data["author_link"] = result.get("author_link", "")
                    data["datetime"] = result.get("datetime", "")
                    data["views"] = result.get("views", "")
                    data["link_preview"] = result.get("link_preview")
                    break

            except Exception as e:
                logger.debug("frame 查询失败 (忽略): %s", e)
                continue

        if not data["text"] and not data["link_preview"]:
            logger.warning("未能从任何 frame 中提取到 Telegram 消息内容")

        return data

    @staticmethod
    def build(url: str, final_url: str, html: str, data: Any) -> PageContent:
        """构建 PageContent。"""
        import re

        msg_data = cast(dict[str, Any], data or {})

        text = msg_data.get("text", "")
        author_name = msg_data.get("author_name", "Telegram")
        author_link = msg_data.get("author_link", "")
        datetime_str = msg_data.get("datetime", "")
        views = msg_data.get("views", "")
        link_preview = msg_data.get("link_preview")

        # 标题：截取前50字符
        text_preview = text[:50] + "..." if len(text) > 50 else text
        # 移除 HTML 标签用于标题
        text_plain = re.sub(r"<[^>]+>", "", text_preview)
        title = f"{author_name}: {text_plain}" if author_name else text_plain

        markdown_parts = []

        # 消息正文（保留原始 HTML 转换为 Markdown）
        if text:
            # 简单处理：将 <br> 转换为换行
            text_md = text.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
            text_md = re.sub(r"<[^>]+>", "", text_md)  # 移除其他 HTML 标签
            markdown_parts.append(f"> {text_md}\n")

        # 链接预览卡片
        if link_preview:
            preview_url = link_preview.get("url", "")
            site_name = link_preview.get("site_name", "")
            preview_title = link_preview.get("title", "")
            preview_desc = link_preview.get("description", "")

            markdown_parts.append("---")
            markdown_parts.append("**引用链接**:")
            if site_name:
                markdown_parts.append(f"- **来源**: {site_name}")
            if preview_title:
                if preview_url:
                    markdown_parts.append(f"- **标题**: [{preview_title}]({preview_url})")
                else:
                    markdown_parts.append(f"- **标题**: {preview_title}")
            elif preview_url:
                markdown_parts.append(f"- **链接**: {preview_url}")
            if preview_desc:
                markdown_parts.append(f"- **摘要**: {preview_desc}")
            markdown_parts.append("---")
            markdown_parts.append("")

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

        # 纯文本版本：包含链接预览内容
        plain_parts = []
        if text:
            plain_parts.append(re.sub(r"<[^>]+>", "", text))
        if link_preview:
            preview_title = link_preview.get("title", "")
            preview_desc = link_preview.get("description", "")
            if preview_title:
                plain_parts.append(f"\n引用: {preview_title}")
            if preview_desc:
                plain_parts.append(preview_desc)
        plain_text = "\n".join(plain_parts)

        # article_html 也包含链接预览
        article_parts = [f"<div class='tgme_widget_message_text'>{text}</div>"]
        if link_preview:
            preview_url = link_preview.get("url", "")
            preview_title = link_preview.get("title", "")
            preview_desc = link_preview.get("description", "")
            article_parts.append("<div class='link_preview'>")
            if preview_title:
                article_parts.append(f"<h3><a href='{preview_url}'>{preview_title}</a></h3>")
            if preview_desc:
                article_parts.append(f"<p>{preview_desc}</p>")
            article_parts.append("</div>")

        return PageContent(
            url=url,
            final_url=final_url,
            title=title,
            text=plain_text,
            markdown="\n".join(markdown_parts),
            raw_html=html,
            article_html=f"<article>{''.join(article_parts)}</article>",
        )
