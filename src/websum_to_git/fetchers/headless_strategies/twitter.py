"""Twitter/X.com 策略 (基于 Headless)。"""

from __future__ import annotations

import html
import logging
import re
from typing import Any, cast
from urllib.parse import urlsplit, urlunsplit

from websum_to_git.fetchers.structs import PageContent

from .registry import route

logger = logging.getLogger(__name__)

TWEET_TEXT_SELECTOR = '[data-testid="tweetText"]'
ARTICLE_VIEW_SELECTOR = '[data-testid="twitterArticleReadView"]'
WAIT_SELECTOR = f"{TWEET_TEXT_SELECTOR}, {ARTICLE_VIEW_SELECTOR}"


def _get_article_url(url: str) -> str | None:
    """将推文详情 URL 转为 X Article 专属 URL。"""
    parsed = urlsplit(url)
    if "/status/" not in parsed.path:
        return None

    article_path = parsed.path.replace("/status/", "/article/", 1)
    if article_path == parsed.path:
        return None

    return urlunsplit((parsed.scheme, parsed.netloc, article_path, parsed.query, parsed.fragment))


def _yaml_escape(value: str) -> str:
    """转义 YAML 双引号字符串。"""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _clean_markdown(markdown: str) -> str:
    """清理多余空行和行尾空白。"""
    markdown = re.sub(r"[ \t]+$", "", markdown, flags=re.MULTILINE)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    return markdown.strip() + "\n"


def _fallback_article_html(text: str) -> str:
    """在缺少结构化 HTML 时构造兜底 article 内容。"""
    escaped = html.escape(text).replace("\n", "<br/>\n")
    return f"<article><p>{escaped}</p></article>"


@route("x.com", wait_selector=WAIT_SELECTOR, scroll=False)
@route("twitter.com", wait_selector=WAIT_SELECTOR, scroll=False)
class TwitterStrategy:
    """Twitter/X.com 抓取策略。"""

    @staticmethod
    def _remove_overlays(page: Any) -> None:
        """移除登录横幅、弹窗和遮罩。"""
        page.evaluate(
            """
            () => {
                const selectors = [
                    '[data-testid="BottomBar"]',
                    '[data-testid="LoginBottomBar"]',
                    '[data-testid="sheetDialog"]',
                    '[data-testid="mask"]',
                    '#credential_picker_container',
                    'iframe[src*="accounts.google.com"]'
                ];

                selectors.forEach(selector => {
                    document.querySelectorAll(selector).forEach(el => el.remove());
                });

                document.querySelectorAll('[role="dialog"]').forEach(el => {
                    const text = el.textContent || '';
                    if (
                        text.includes('登录') ||
                        text.includes('Log in') ||
                        text.includes('Sign in')
                    ) {
                        el.remove();
                    }
                });

                document.body.style.overflow = 'auto';
                document.documentElement.style.overflow = 'auto';
            }
            """
        )

    @staticmethod
    def _is_article_read_view(page: Any) -> bool:
        """检测当前页面是否存在 Article 阅读视图。"""
        return bool(
            page.evaluate(
                f"""
                () => Boolean(document.querySelector('{ARTICLE_VIEW_SELECTOR}'))
                """
            )
        )

    @staticmethod
    def process(page: Any) -> None:
        """处理页面遮挡，并在 status 场景自动跳转到 article 页面。"""
        TwitterStrategy._remove_overlays(page)

        current_url = page.url
        if "/status/" in current_url and TwitterStrategy._is_article_read_view(page):
            article_url = _get_article_url(current_url)
            if article_url:
                logger.info("检测到 X Article，跳转专属页面抓取全文: %s", article_url)
                page.goto(article_url, wait_until="domcontentloaded", timeout=15000)
                current_url = page.url

        try:
            if "/article/" in current_url:
                page.wait_for_selector(ARTICLE_VIEW_SELECTOR, timeout=15000)
            else:
                page.wait_for_selector(TWEET_TEXT_SELECTOR, timeout=15000)
        except Exception:
            logger.debug("等待 Twitter 关键内容超时，继续抓取: %s", current_url)

        page.wait_for_timeout(1000)
        TwitterStrategy._remove_overlays(page)

    @staticmethod
    def extract(page: Any) -> dict:
        """提取推文或 X Article 内容。"""
        return page.evaluate(
            """
            () => {
                const data = {
                    page_type: window.location.href.includes('/article/') ? 'article' : 'tweet',
                    title: '',
                    author_name: '',
                    author_handle: '',
                    published_at: '',
                    text: '',
                    markdown_body: '',
                    article_html: '',
                    images: [],
                    videos: [],
                    cards: [],
                    poll: null,
                };

                function getPageType() {
                    const url = window.location.href;
                    if (url.includes('/article/')) return 'article';
                    if (url.includes('/status/')) return 'tweet';
                    return 'tweet';
                }

                function getAuthorInfo() {
                    const selectors = {
                        name: [
                            '[data-testid="User-Name"] a[role="link"]',
                            'a[href^="/"] h2[dir="ltr"]',
                            '[data-testid="UserName"]',
                            '[data-testid="tweet"] a[role="link"]',
                            '[data-testid="article-author-name"]'
                        ],
                        username: [
                            '[data-testid="User-Name"] span[dir="ltr"]',
                            'a[href^="/"] span[dir="ltr"]',
                            '[data-testid="UserName"] span',
                            '[data-testid="article-author-username"]'
                        ]
                    };

                    let authorName = '';
                    let authorUsername = '';

                    for (const selector of selectors.name) {
                        const el = document.querySelector(selector);
                        if (el && (el.textContent || '').trim()) {
                            authorName = (el.textContent || '').trim();
                            break;
                        }
                    }

                    for (const selector of selectors.username) {
                        const el = document.querySelector(selector);
                        const text = (el && el.textContent ? el.textContent : '').trim();
                        if (text.startsWith('@')) {
                            authorUsername = text;
                            break;
                        }
                    }

                    if (!authorUsername) {
                        const match = window.location.pathname.match(/^\\/([^/]+)/);
                        if (match) {
                            authorUsername = '@' + match[1];
                        }
                    }

                    if (!authorName && authorUsername) {
                        authorName = authorUsername.slice(1);
                    }

                    return {
                        name: authorName,
                        username: authorUsername.replace(/^@/, ''),
                    };
                }

                function getPublishTime() {
                    const selectors = [
                        'time[datetime]',
                        '[data-testid="tweet"] time',
                        '[data-testid="article-header"] time',
                        'a[href*="/status/"] time'
                    ];

                    for (const selector of selectors) {
                        const timeEl = document.querySelector(selector);
                        if (!timeEl) continue;

                        const datetime = timeEl.getAttribute('datetime');
                        if (datetime) return datetime;

                        const text = (timeEl.textContent || '').trim();
                        if (text) return text;
                    }

                    return '';
                }

                function normalizeImageUrl(url) {
                    if (!url) return '';
                    let normalized = url.trim();
                    normalized = normalized.replace(/:\\w+$/, '');
                    normalized = normalized.replace(/name=\\w+/, 'name=orig');
                    return normalized;
                }

                function processImage(img) {
                    const urlAttributes = ['src', 'data-src', 'data-image'];
                    let imageUrl = '';

                    for (const attr of urlAttributes) {
                        const value = img.getAttribute(attr);
                        if (value && value.trim() && !value.startsWith('data:')) {
                            imageUrl = value.trim();
                            break;
                        }
                    }

                    imageUrl = normalizeImageUrl(imageUrl);
                    if (!imageUrl) return null;
                    if (imageUrl.includes('profile_images')) return null;
                    if (imageUrl.includes('abs-0.twimg.com/emoji')) return null;
                    if (imageUrl.endsWith('.svg')) return null;

                    const alt = img.getAttribute('alt') || '图片';
                    return {
                        url: imageUrl,
                        alt: alt,
                        markdown: `![${alt}](${imageUrl})`,
                    };
                }

                function processVideo(video) {
                    const videoEl = video.tagName === 'VIDEO' ? video : video.querySelector('video');
                    if (videoEl && videoEl.src) {
                        return {
                            url: videoEl.src,
                            thumbnail: videoEl.getAttribute('poster') || '',
                            markdown: `[🎬 视频](${videoEl.src})`,
                        };
                    }

                    const poster = videoEl ? videoEl.getAttribute('poster') : '';
                    if (poster) {
                        return {
                            url: '',
                            thumbnail: poster,
                            markdown: `![视频缩略图](${poster})`,
                        };
                    }

                    return {
                        url: '',
                        thumbnail: '',
                        markdown: '🎬 *[视频内容]*',
                    };
                }

                function processLink(link) {
                    const href = link.getAttribute('href') || '';
                    const text = (link.textContent || '').trim();
                    if (!text) return '';

                    if (href.includes('/hashtag/') || href.includes('/search?q=%23')) {
                        return text;
                    }
                    if (href.startsWith('/') && !href.includes('/status/')) {
                        return text;
                    }

                    try {
                        const absolute = new URL(href, window.location.origin).toString();
                        return `[${text}](${absolute})`;
                    } catch {
                        return text;
                    }
                }

                function processEmoji(emoji) {
                    const alt = emoji.getAttribute('alt');
                    if (alt) return alt;
                    return emoji.textContent || '';
                }

                function extractTextContent(element) {
                    let markdown = '';

                    for (const node of element.childNodes) {
                        if (node.nodeType === Node.TEXT_NODE) {
                            markdown += node.textContent || '';
                            continue;
                        }

                        if (node.nodeType !== Node.ELEMENT_NODE) continue;

                        const tagName = node.tagName.toLowerCase();
                        switch (tagName) {
                            case 'img':
                                if (
                                    node.getAttribute('draggable') === 'false' ||
                                    (node.src || '').includes('emoji') ||
                                    node.getAttribute('alt')
                                ) {
                                    markdown += processEmoji(node);
                                }
                                break;
                            case 'a':
                                markdown += processLink(node);
                                break;
                            case 'br':
                                markdown += '\\n';
                                break;
                            default:
                                markdown += extractTextContent(node);
                        }
                    }

                    return markdown;
                }

                function processCard(card) {
                    const linkEl = card.querySelector('a[href]');
                    if (!linkEl) return null;

                    const href = linkEl.href;
                    const titleEl = card.querySelector('[dir="ltr"]');
                    const descEl = card.querySelector('span[dir="auto"]');
                    const title = titleEl ? (titleEl.textContent || '').trim() : '链接';
                    const description = descEl ? (descEl.textContent || '').trim() : '';

                    let markdown = `> 📎 **[${title}](${href})**`;
                    if (description) {
                        markdown += `\\n> ${description}`;
                    }

                    return {
                        href: href,
                        title: title,
                        description: description,
                        markdown: markdown,
                    };
                }

                function processPoll(poll) {
                    const questionEl = poll.querySelector('[role="heading"]');
                    const question = questionEl ? (questionEl.textContent || '').trim() : '投票';

                    const options = [];
                    poll.querySelectorAll('[role="button"]').forEach(option => {
                        const text = (option.textContent || '').trim();
                        if (text) options.push(text);
                    });

                    let markdown = `📊 **${question}**`;
                    if (options.length > 0) {
                        markdown += '\\n\\n' + options.map(text => `- [ ] ${text}`).join('\\n');
                    }

                    return {
                        question: question,
                        options: options,
                        markdown: markdown,
                    };
                }

                function isCodeBlock(element) {
                    if (element.tagName !== 'BLOCKQUOTE') return false;

                    const text = element.textContent || '';
                    const codePatterns = [
                        /\\b(fn|func|function|def|class|import|from|const|let|var|if|else|for|while|return)\\b/,
                        /[{};]\\s*\\n/,
                        /\\(\\s*\\w+\\s*:\\s*\\w+\\s*\\)/,
                        /->\\s*\\w+/,
                        /=\\s*\\{/,
                        /test\\s+"/
                    ];

                    const isQuotePattern = (
                        text.length < 200 &&
                        !text.includes('{') &&
                        !text.includes('}') &&
                        !text.includes(';') &&
                        !/\\b(fn|func|function|def|class|const|let|var|return)\\b/.test(text)
                    );

                    if (isQuotePattern) return false;
                    return codePatterns.some(pattern => pattern.test(text));
                }

                function extractCodeBlock(element) {
                    let code = element.innerText || element.textContent || '';
                    code = code.replace(/\\n{3,}/g, '\\n\\n').trim();

                    let language = '';
                    if (/\\bfn\\s+\\w+\\s*\\(/.test(code)) language = 'rust';
                    else if (/\\bfunc\\s+\\w+/.test(code)) language = 'go';
                    else if (/\\bdef\\s+\\w+\\s*\\(/.test(code)) language = 'python';
                    else if (/\\bfunction\\s+\\w+/.test(code)) language = 'javascript';
                    else if (/\\bconst\\s+\\w+\\s*[:=]/.test(code)) language = 'typescript';
                    else if (/\\bclass\\s+\\w+/.test(code)) language = 'java';
                    else if (/#include|#define/.test(code)) language = 'c';

                    return { code, language };
                }

                data.page_type = getPageType();
                const author = getAuthorInfo();
                data.author_name = author.name;
                data.author_handle = author.username;
                data.published_at = getPublishTime();

                if (data.page_type === 'article') {
                    const articleContainer = document.querySelector('[data-testid="twitterArticleReadView"]');
                    let title = '';

                    if (articleContainer) {
                        const titleDiv = articleContainer.querySelector('div[dir="auto"]');
                        if (titleDiv) {
                            title = (titleDiv.textContent || '').trim();
                        } else {
                            const firstSpan = articleContainer.querySelector('span');
                            if (firstSpan) title = (firstSpan.textContent || '').trim();
                        }
                    }

                    if (!title) {
                        const titleSelectors = [
                            '[data-testid="articleTitle"]',
                            'h1[dir="ltr"]',
                            'article h1'
                        ];
                        for (const selector of titleSelectors) {
                            const el = document.querySelector(selector);
                            if (el && (el.textContent || '').trim()) {
                                title = (el.textContent || '').trim();
                                break;
                            }
                        }
                    }

                    data.title = title || 'X Article';
                    if (!articleContainer) return data;

                    data.article_html = `<article>${articleContainer.innerHTML}</article>`;

                    let content = '';
                    const seenTexts = new Set();
                    const authorUsernameMatch = window.location.pathname.match(/^\\/([^/]+)/);
                    const authorUsername = authorUsernameMatch ? authorUsernameMatch[1] : '';
                    const blockElements = articleContainer.querySelectorAll(
                        'div.longform-unstyled, blockquote.longform-blockquote, ' +
                        'h1.longform-header-one, h2.longform-header-two, h3.longform-header-three, ' +
                        '[data-testid="articleBody"] > div'
                    );

                    function shouldSkipText(text) {
                        if (!text) return true;
                        if (text === title) return true;
                        if (text === authorUsername) return true;
                        if (text === data.author_name) return true;
                        if (text === '·') return true;
                        if (text === '关注') return true;
                        if (text.startsWith('点击 关注')) return true;
                        if (/^\\d+$/.test(text)) return true;
                        if (/^\\d+,\\d+$/.test(text)) return true;
                        if (/^\\d+\\s*(回复|转帖|喜欢|查看|书签)/.test(text)) return true;
                        return false;
                    }

                    blockElements.forEach((el, index) => {
                        const text = (el.textContent || '').trim();
                        if (index === 0 && text === title) return;
                        if (shouldSkipText(text)) return;
                        if (seenTexts.has(text)) return;
                        seenTexts.add(text);

                        if (isCodeBlock(el)) {
                            const { code, language } = extractCodeBlock(el);
                            if (code) {
                                content += '```' + language + '\\n' + code + '\\n```\\n\\n';
                            }
                            return;
                        }

                        const tagName = el.tagName.toLowerCase();
                        if (tagName === 'h1' || tagName === 'h2' || tagName === 'h3') {
                            const prefix = tagName === 'h1' ? '# ' : tagName === 'h2' ? '## ' : '### ';
                            content += prefix + text + '\\n\\n';
                            return;
                        }

                        if (tagName === 'blockquote') {
                            const lines = text
                                .split('\\n')
                                .map(line => line.trim())
                                .filter(Boolean)
                                .map(line => '> ' + line)
                                .join('\\n');
                            if (lines) content += lines + '\\n\\n';
                            return;
                        }

                        const isHeading =
                            !['作者：', '原文：', '来源：', '译者：', '注：'].some(prefix => text.startsWith(prefix)) &&
                            el.classList.contains('longform-header-two') &&
                            text.length < 100;

                        if (isHeading) {
                            content += '## ' + text + '\\n\\n';
                        } else {
                            content += text + '\\n\\n';
                        }
                    });

                    if (!content.trim()) {
                        const walker = document.createTreeWalker(articleContainer, NodeFilter.SHOW_TEXT);
                        let node;
                        while ((node = walker.nextNode())) {
                            const text = (node.textContent || '').trim();
                            if (shouldSkipText(text)) continue;
                            if (seenTexts.has(text)) continue;
                            seenTexts.add(text);

                            const parentEl = node.parentElement;
                            const parentTag = parentEl ? parentEl.tagName.toLowerCase() : '';
                            if (parentTag === 'h1' || parentTag === 'h2' || parentTag === 'h3') {
                                const prefix = parentTag === 'h1' ? '# ' : parentTag === 'h2' ? '## ' : '### ';
                                content += prefix + text + '\\n\\n';
                                continue;
                            }

                            const isHeading =
                                text.length < 80 &&
                                (text.includes('（') || text.includes(')')) &&
                                parentEl &&
                                parentEl.classList.contains('longform-header-two');

                            if (isHeading) {
                                content += '## ' + text + '\\n\\n';
                            } else {
                                content += text + '\\n\\n';
                            }
                        }
                    }

                    const imageEls = articleContainer.querySelectorAll('img[src*="pbs.twimg.com"]');
                    imageEls.forEach(img => {
                        const media = processImage(img);
                        if (media) data.images.push(media);
                    });

                    if (data.images.length > 0) {
                        content += data.images.map(item => item.markdown).join('\\n\\n') + '\\n\\n';
                    }

                    data.markdown_body = content.trim();
                    data.text = content
                        .replace(/^#{1,3}\\s+/gm, '')
                        .replace(/^>\\s?/gm, '')
                        .replace(/```[\\w-]*\\n?/g, '')
                        .replace(/```/g, '')
                        .trim();

                    return data;
                }

                const contentSelectors = [
                    '[data-testid="tweetText"]',
                    '[data-testid="tweet"] div[lang]',
                    '[data-testid="tweet"] [dir="auto"]',
                    'article [data-testid="tweetText"]'
                ];

                let contentEl = null;
                for (const selector of contentSelectors) {
                    const el = document.querySelector(selector);
                    if (el && (el.textContent || '').trim().length > 0) {
                        contentEl = el;
                        break;
                    }
                }

                if (!contentEl) return data;

                data.text = extractTextContent(contentEl).trim();
                const articleContainer = contentEl.closest('article');
                if (articleContainer) {
                    data.article_html = `<article>${articleContainer.innerHTML}</article>`;

                    articleContainer
                        .querySelectorAll('img[src*="pbs.twimg.com"], img[src*="video.twimg.com"]')
                        .forEach(img => {
                            const media = processImage(img);
                            if (media) data.images.push(media);
                        });

                    articleContainer
                        .querySelectorAll('[data-testid="videoPlayer"], video')
                        .forEach(video => data.videos.push(processVideo(video)));

                    articleContainer
                        .querySelectorAll('[data-testid="card.wrapper"], [data-testid="card.layoutLarge"]')
                        .forEach(card => {
                            const item = processCard(card);
                            if (item) data.cards.push(item);
                        });

                    const pollEl = articleContainer.querySelector('[data-testid="cardPoll"]');
                    if (pollEl) {
                        data.poll = processPoll(pollEl);
                    }
                }

                const markdownParts = [];
                if (data.text) markdownParts.push(data.text);
                if (data.images.length > 0) {
                    markdownParts.push(data.images.map(item => item.markdown).join('\\n\\n'));
                }
                if (data.videos.length > 0) {
                    markdownParts.push(data.videos.map(item => item.markdown).join('\\n\\n'));
                }
                if (data.poll && data.poll.markdown) {
                    markdownParts.push(data.poll.markdown);
                }
                if (data.cards.length > 0) {
                    markdownParts.push(data.cards.map(item => item.markdown).join('\\n\\n'));
                }

                data.markdown_body = markdownParts.filter(Boolean).join('\\n\\n').trim();
                return data;
            }
            """
        )

    @staticmethod
    def build(url: str, final_url: str, html: str, data: Any) -> PageContent:
        """构建 PageContent。"""
        tweet_data = cast(dict[str, Any], data or {})

        page_type = tweet_data.get("page_type", "tweet")
        author_name = tweet_data.get("author_name", "")
        author_handle = tweet_data.get("author_handle", "")
        published_at = tweet_data.get("published_at", "")
        text = tweet_data.get("text", "")
        markdown_body = tweet_data.get("markdown_body", "") or text

        author_display = author_name or author_handle or "Unknown"
        author_suffix = f" (@{author_handle})" if author_handle else ""
        source_label = "X (Twitter) Articles" if page_type == "article" else "X (Twitter)"

        if page_type == "article":
            title = tweet_data.get("title", "") or f"{author_display}{author_suffix}"
        else:
            preview = text[:50] + "..." if len(text) > 50 else text
            title = f"{author_display}{author_suffix}: {preview}" if preview else f"{author_display}{author_suffix}"

        source_url = final_url or url
        markdown_parts = ["---"]
        if page_type == "article":
            markdown_parts.append(f'title: "{_yaml_escape(title)}"')
        markdown_parts.append(f'author: "{_yaml_escape(author_display + author_suffix)}"')
        if published_at:
            markdown_parts.append(f'date: "{_yaml_escape(published_at)}"')
        markdown_parts.append(f'source: "{source_label}"')
        markdown_parts.append(f'url: "{_yaml_escape(source_url)}"')
        if source_url != url:
            markdown_parts.append(f'original_url: "{_yaml_escape(url)}"')
        markdown_parts.append("---")
        markdown_parts.append("")

        if page_type == "article":
            markdown_parts.append(f"# {title}")
            markdown_parts.append("")

        if markdown_body:
            markdown_parts.append(markdown_body)
            markdown_parts.append("")

        markdown_parts.append("---")
        markdown_parts.append(f"*原文发布于 {source_label}：{source_url}*")

        article_html = tweet_data.get("article_html") or _fallback_article_html(markdown_body or text or title)

        return PageContent(
            url=url,
            final_url=final_url,
            title=title,
            text=text or markdown_body,
            markdown=_clean_markdown("\n".join(markdown_parts)),
            raw_html=html,
            article_html=article_html,
        )
