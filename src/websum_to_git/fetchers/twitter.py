"""Twitter/X.com 专用 Fetcher。

使用 Camoufox (Headless Firefox) 抓取推文内容，处理登录横幅和弹窗。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from .camoufox_helper import fetch_with_camoufox
from .structs import PageContent, get_common_config

if TYPE_CHECKING:
    from websum_to_git.config import AppConfig

logger = logging.getLogger(__name__)


@dataclass
class TwitterFetcher:
    """Twitter/X.com 推文抓取器。"""

    config: AppConfig

    def __post_init__(self):
        self.timeout, self.verify_ssl = get_common_config(self.config)

    def fetch(self, url: str) -> PageContent:
        logger.info("使用 TwitterFetcher 抓取: %s", url)

        url = self._normalize_url(url)

        html, final_url, tweet_data = fetch_with_camoufox(
            url,
            timeout=self.timeout,
            wait_selector='[data-testid="tweetText"]',
            scroll=False,
            post_process=self._remove_overlays,
            extract=self._extract_tweet_data,
        )

        tweet_data = cast(dict[str, Any], tweet_data or {})

        return self._build_page_content(url, final_url, html, tweet_data)

    def _normalize_url(self, url: str) -> str:
        """标准化 URL，统一使用 x.com。"""
        return re.sub(r"twitter\.com", "x.com", url, flags=re.IGNORECASE)

    def _remove_overlays(self, page: Any) -> None:
        """移除登录横幅、Google 登录弹窗等干扰元素。"""
        page.evaluate(
            """
            () => {
                // 移除底部登录横幅
                const loginBar = document.querySelector('[data-testid="BottomBar"]');
                if (loginBar) loginBar.remove();

                // 移除底部登录横幅 (备用选择器)
                const loginBottomBar = document.querySelector('[data-testid="LoginBottomBar"]');
                if (loginBottomBar) loginBottomBar.remove();

                // 移除 "登录" 弹窗层
                const layers = document.querySelectorAll('[data-testid="sheetDialog"]');
                layers.forEach(layer => layer.remove());

                // 移除 Google One Tap 登录弹窗
                const googleOneTap = document.getElementById('credential_picker_container');
                if (googleOneTap) googleOneTap.remove();

                // 移除其他可能的 Google 登录 iframe
                const googleIframes = document.querySelectorAll('iframe[src*="accounts.google.com"]');
                googleIframes.forEach(iframe => iframe.remove());

                // 移除遮罩层
                const masks = document.querySelectorAll('[data-testid="mask"]');
                masks.forEach(mask => mask.remove());

                // 移除固定定位的登录提示
                const fixedElements = document.querySelectorAll('[role="dialog"]');
                fixedElements.forEach(el => {
                    if (el.textContent && (
                        el.textContent.includes('登录') ||
                        el.textContent.includes('Log in') ||
                        el.textContent.includes('Sign in')
                    )) {
                        el.remove();
                    }
                });

                // 恢复页面滚动
                document.body.style.overflow = 'auto';
                document.documentElement.style.overflow = 'auto';
            }
            """
        )

    def _extract_tweet_data(self, page: Any) -> dict:
        """从页面提取推文数据。"""
        return page.evaluate(
            """
            () => {
                const data = {
                    author_name: '',
                    author_handle: '',
                    text: '',
                    created_at: '',
                    images: [],
                    videos: [],
                    quote: null,
                    stats: { likes: '', retweets: '', replies: '', views: '' }
                };

                // 查找主推文容器 (第一条 article)
                const articles = document.querySelectorAll('article[data-testid="tweet"]');
                if (articles.length === 0) return data;

                // 取第一条推文作为主推文
                const mainTweet = articles[0];

                // 提取作者信息
                const userNameEl = mainTweet.querySelector('[data-testid="User-Name"]');
                if (userNameEl) {
                    // 作者名
                    const nameSpan = userNameEl.querySelector('span');
                    if (nameSpan) data.author_name = nameSpan.textContent || '';

                    // 作者 handle (@xxx)
                    const handleLinks = userNameEl.querySelectorAll('a');
                    for (const link of handleLinks) {
                        const href = link.getAttribute('href') || '';
                        if (href.match(/^\\/[^/]+$/)) {
                            data.author_handle = href.slice(1);
                            break;
                        }
                    }
                }

                // 提取推文正文
                const tweetTextEl = mainTweet.querySelector('[data-testid="tweetText"]');
                if (tweetTextEl) {
                    data.text = tweetTextEl.textContent || '';
                }

                // 提取发布时间
                const timeEl = mainTweet.querySelector('time');
                if (timeEl) {
                    data.created_at = timeEl.getAttribute('datetime') || timeEl.textContent || '';
                }

                // 提取图片
                const photoContainers = mainTweet.querySelectorAll('[data-testid="tweetPhoto"]');
                photoContainers.forEach(container => {
                    const img = container.querySelector('img');
                    if (img && img.src && !img.src.includes('profile_image')) {
                        data.images.push(img.src);
                    }
                });

                // 提取视频缩略图
                const videoContainers = mainTweet.querySelectorAll('[data-testid="videoPlayer"]');
                videoContainers.forEach(container => {
                    const poster = container.querySelector('video');
                    if (poster && poster.poster) {
                        data.videos.push({ thumbnail: poster.poster });
                    }
                });

                // 提取互动数据
                const statsGroup = mainTweet.querySelector('[role="group"]');
                if (statsGroup) {
                    const buttons = statsGroup.querySelectorAll('[data-testid]');
                    buttons.forEach(btn => {
                        const testId = btn.getAttribute('data-testid') || '';
                        const countEl = btn.querySelector('span');
                        const count = countEl ? countEl.textContent : '';

                        if (testId.includes('reply')) data.stats.replies = count;
                        else if (testId.includes('retweet')) data.stats.retweets = count;
                        else if (testId.includes('like')) data.stats.likes = count;
                    });
                }

                // 提取浏览量
                const viewsEl = mainTweet.querySelector('a[href*="/analytics"]');
                if (viewsEl) {
                    data.stats.views = viewsEl.textContent || '';
                }

                // 提取引用推文
                const quoteContainer = mainTweet.querySelector('[data-testid="quoteTweet"]');
                if (quoteContainer) {
                    const quoteText = quoteContainer.querySelector('[data-testid="tweetText"]');
                    const quoteUserName = quoteContainer.querySelector('[data-testid="User-Name"]');

                    data.quote = {
                        text: quoteText ? quoteText.textContent : '',
                        author_name: '',
                        author_handle: ''
                    };

                    if (quoteUserName) {
                        const nameSpan = quoteUserName.querySelector('span');
                        if (nameSpan) data.quote.author_name = nameSpan.textContent || '';

                        const handleLinks = quoteUserName.querySelectorAll('a');
                        for (const link of handleLinks) {
                            const href = link.getAttribute('href') || '';
                            if (href.match(/^\\/[^/]+$/)) {
                                data.quote.author_handle = href.slice(1);
                                break;
                            }
                        }
                    }
                }

                return data;
            }
            """
        )

    def _build_page_content(self, url: str, final_url: str, html: str, tweet_data: dict) -> PageContent:
        """从提取的数据构建 PageContent。"""
        author_name = tweet_data.get("author_name", "Unknown")
        author_handle = tweet_data.get("author_handle", "unknown")
        text = tweet_data.get("text", "")

        # 标题: 作者名 + 推文开头
        title_preview = text[:50] + "..." if len(text) > 50 else text
        title = f"{author_name} (@{author_handle}): {title_preview}"

        # 构建 Markdown 内容
        markdown_parts = []

        # 推文正文
        if text:
            markdown_parts.append(f"> {text}")
            markdown_parts.append("")

        # 作者信息
        markdown_parts.append(f"**作者**: [{author_name}](https://x.com/{author_handle}) (@{author_handle})")

        # 发布时间
        created_at = tweet_data.get("created_at", "")
        if created_at:
            markdown_parts.append(f"**发布时间**: {created_at}")

        # 互动数据
        stats = tweet_data.get("stats", {})
        likes = stats.get("likes", "")
        retweets = stats.get("retweets", "")
        replies = stats.get("replies", "")
        views = stats.get("views", "")

        stats_parts = []
        if likes:
            stats_parts.append(f"{likes} 赞")
        if retweets:
            stats_parts.append(f"{retweets} 转发")
        if replies:
            stats_parts.append(f"{replies} 回复")
        if views:
            stats_parts.append(f"{views} 浏览")

        if stats_parts:
            markdown_parts.append(f"**互动**: {' | '.join(stats_parts)}")

        markdown_parts.append("")

        # 图片
        images = tweet_data.get("images", [])
        if images:
            markdown_parts.append("### 图片")
            for i, img_url in enumerate(images, 1):
                markdown_parts.append(f"![图片 {i}]({img_url})")
            markdown_parts.append("")

        # 视频
        videos = tweet_data.get("videos", [])
        if videos:
            markdown_parts.append("### 视频")
            for i, video in enumerate(videos, 1):
                thumbnail = video.get("thumbnail", "")
                if thumbnail:
                    markdown_parts.append(f"![视频 {i} 缩略图]({thumbnail})")
            markdown_parts.append("")

        # 引用推文
        quote = tweet_data.get("quote")
        if quote and quote.get("text"):
            quote_author = quote.get("author_name", "")
            quote_handle = quote.get("author_handle", "")
            quote_text = quote.get("text", "")
            markdown_parts.append("### 引用推文")
            if quote_author or quote_handle:
                markdown_parts.append(f"> **{quote_author}** (@{quote_handle})")
            markdown_parts.append(f"> {quote_text}")
            markdown_parts.append("")

        # 原始链接
        markdown_parts.append(f"[查看原推文]({url})")

        markdown = "\n".join(markdown_parts)

        # 构建简单 HTML（用于兼容性）
        article_html = f"<article><p>{text}</p></article>"

        logger.info("TwitterFetcher 完成, 标题: %s", title)

        return PageContent(
            url=url,
            final_url=final_url,
            title=title,
            text=text,
            markdown=markdown,
            raw_html=html,
            article_html=article_html,
        )


def fetch_twitter(url: str, config: AppConfig) -> PageContent:
    """Twitter Fetcher 入口函数。"""
    fetcher = TwitterFetcher(config)
    return fetcher.fetch(url)
