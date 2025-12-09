"""Twitter/X.com 策略 (基于 Headless)。"""

from __future__ import annotations

import logging
from typing import Any, cast

from websum_to_git.fetchers.structs import PageContent

from .registry import route

logger = logging.getLogger(__name__)


@route("x.com", wait_selector='[data-testid="tweetText"]', scroll=False)
@route("twitter.com", wait_selector='[data-testid="tweetText"]', scroll=False)
class TwitterStrategy:
    """Twitter/X.com 抓取策略。"""

    @staticmethod
    def process(page: Any) -> None:
        """移除登录横幅、Google 登录弹窗等干扰元素。"""
        page.evaluate(
            """
            () => {
                // 移除底部登录横幅
                const loginBar = document.querySelector('[data-testid="BottomBar"]');
                if (loginBar) loginBar.remove();

                const loginBottomBar = document.querySelector('[data-testid="LoginBottomBar"]');
                if (loginBottomBar) loginBottomBar.remove();

                // 移除 "登录" 弹窗层
                const layers = document.querySelectorAll('[data-testid="sheetDialog"]');
                layers.forEach(layer => layer.remove());

                // 移除 Google One Tap
                const googleOneTap = document.getElementById('credential_picker_container');
                if (googleOneTap) googleOneTap.remove();

                // 移除 Google iframes
                const googleIframes = document.querySelectorAll('iframe[src*="accounts.google.com"]');
                googleIframes.forEach(iframe => iframe.remove());

                // 移除遮罩
                const masks = document.querySelectorAll('[data-testid="mask"]');
                masks.forEach(mask => mask.remove());

                // 移除固定登录提示
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

                document.body.style.overflow = 'auto';
                document.documentElement.style.overflow = 'auto';
            }
            """
        )

    @staticmethod
    def extract(page: Any) -> dict:
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

                const articles = document.querySelectorAll('article[data-testid="tweet"]');
                if (articles.length === 0) return data;

                const mainTweet = articles[0];

                // 作者
                const userNameEl = mainTweet.querySelector('[data-testid="User-Name"]');
                if (userNameEl) {
                    const nameSpan = userNameEl.querySelector('span');
                    if (nameSpan) data.author_name = nameSpan.textContent || '';

                    const handleLinks = userNameEl.querySelectorAll('a');
                    for (const link of handleLinks) {
                        const href = link.getAttribute('href') || '';
                        if (href.match(/^\\/[^/]+$/)) {
                            data.author_handle = href.slice(1);
                            break;
                        }
                    }
                }

                // 正文
                const tweetTextEl = mainTweet.querySelector('[data-testid="tweetText"]');
                if (tweetTextEl) data.text = tweetTextEl.textContent || '';

                // 时间
                const timeEl = mainTweet.querySelector('time');
                if (timeEl) data.created_at = timeEl.getAttribute('datetime') || timeEl.textContent || '';

                // 图片
                const photoContainers = mainTweet.querySelectorAll('[data-testid="tweetPhoto"]');
                photoContainers.forEach(container => {
                    const img = container.querySelector('img');
                    if (img && img.src && !img.src.includes('profile_image')) {
                        data.images.push(img.src);
                    }
                });

                // 视频
                const videoContainers = mainTweet.querySelectorAll('[data-testid="videoPlayer"]');
                videoContainers.forEach(container => {
                    const poster = container.querySelector('video');
                    if (poster && poster.poster) data.videos.push({ thumbnail: poster.poster });
                });

                // 互动
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

                const viewsEl = mainTweet.querySelector('a[href*="/analytics"]');
                if (viewsEl) data.stats.views = viewsEl.textContent || '';

                // 引用
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

    @staticmethod
    def build(url: str, final_url: str, html: str, data: Any) -> PageContent:
        """构建 PageContent。"""
        tweet_data = cast(dict[str, Any], data or {})

        author_name = tweet_data.get("author_name", "Unknown")
        author_handle = tweet_data.get("author_handle", "unknown")
        text = tweet_data.get("text", "")

        title_preview = text[:50] + "..." if len(text) > 50 else text
        title = f"{author_name} (@{author_handle}): {title_preview}"

        markdown_parts = []
        if text:
            markdown_parts.append(f"> {text}\n")

        markdown_parts.append(f"**作者**: [{author_name}](https://x.com/{author_handle}) (@{author_handle})")

        created_at = tweet_data.get("created_at", "")
        if created_at:
            markdown_parts.append(f"**发布时间**: {created_at}")

        stats = tweet_data.get("stats", {})
        stats_line = []
        if stats.get("likes"):
            stats_line.append(f"{stats['likes']} 赞")
        if stats.get("retweets"):
            stats_line.append(f"{stats['retweets']} 转发")
        if stats.get("replies"):
            stats_line.append(f"{stats['replies']} 回复")
        if stats.get("views"):
            stats_line.append(f"{stats['views']} 浏览")
        if stats_line:
            markdown_parts.append(f"**互动**: {' | '.join(stats_line)}")

        markdown_parts.append("")

        images = tweet_data.get("images", [])
        if images:
            markdown_parts.append("### 图片")
            for i, img_url in enumerate(images, 1):
                markdown_parts.append(f"![图片 {i}]({img_url})")
            markdown_parts.append("")

        videos = tweet_data.get("videos", [])
        if videos:
            markdown_parts.append("### 视频")
            for i, video in enumerate(videos, 1):
                thumb = video.get("thumbnail", "")
                if thumb:
                    markdown_parts.append(f"![视频 {i} 缩略图]({thumb})")
            markdown_parts.append("")

        quote = tweet_data.get("quote")
        if quote and quote.get("text"):
            markdown_parts.append("### 引用推文")
            q_auth = quote.get("author_name", "")
            q_hand = quote.get("author_handle", "")
            if q_auth:
                markdown_parts.append(f"> **{q_auth}** (@{q_hand})")
            markdown_parts.append(f"> {quote.get('text', '')}\n")

        markdown_parts.append(f"[查看原推文]({url})")

        return PageContent(
            url=url,
            final_url=final_url,
            title=title,
            text=text,
            markdown="\n".join(markdown_parts),
            raw_html=html,
            article_html=f"<article><p>{text}</p></article>",
        )
