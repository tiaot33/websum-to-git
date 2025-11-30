from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

# Telegraph API 基础地址
_API_BASE = "https://api.telegra.ph"


@dataclass
class TelegraphResult:
    """Telegraph 发布结果。"""

    url: str  # Telegraph 页面链接
    path: str  # 页面路径


class TelegraphClient:
    """Telegraph 匿名发布客户端。"""

    def __init__(self, short_name: str = "WebSum-Bot") -> None:
        self._session = requests.Session()
        self._access_token: str | None = None
        self._short_name = short_name

    def _ensure_account(self) -> str:
        """确保已创建 Telegraph 账户，返回 access_token。"""
        if self._access_token:
            return self._access_token

        logger.info("创建 Telegraph 匿名账户")
        response = self._session.post(
            f"{_API_BASE}/createAccount",
            data={
                "short_name": self._short_name,
                "author_name": "WebSum Bot",
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("ok"):
            error = data.get("error", "未知错误")
            raise RuntimeError(f"创建 Telegraph 账户失败: {error}")

        result = data.get("result", {})
        self._access_token = result.get("access_token")
        if not self._access_token:
            raise RuntimeError("Telegraph 返回的 access_token 为空")

        logger.info("Telegraph 账户创建成功")
        return self._access_token

    def publish_markdown(self, *, title: str, content: str, author_name: str = "WebSum Bot") -> TelegraphResult:
        """将 Markdown 内容发布到 Telegraph。

        Args:
            title: 页面标题
            content: Markdown 内容
            author_name: 作者名称

        Returns:
            TelegraphResult 包含页面 URL 和路径
        """
        access_token = self._ensure_account()

        # 将 Markdown 转换为 Telegraph Node 格式
        html_content = self._markdown_to_telegraph_html(content)
        logger.info("准备发布到 Telegraph, 标题: %s, 内容长度: %d", title, len(html_content))

        response = self._session.post(
            f"{_API_BASE}/createPage",
            data={
                "access_token": access_token,
                "title": title[:256],  # Telegraph 标题限制 256 字符
                "author_name": author_name[:128],
                "content": html_content,
                "return_content": "false",
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()

        if not data.get("ok"):
            error = data.get("error", "未知错误")
            raise RuntimeError(f"发布到 Telegraph 失败: {error}")

        result = data.get("result", {})
        path = result.get("path", "")
        url = result.get("url", f"https://telegra.ph/{path}")

        logger.info("Telegraph 发布成功: %s", url)
        return TelegraphResult(url=url, path=path)

    def _markdown_to_telegraph_html(self, markdown: str) -> str:
        """将 Markdown 转换为 Telegraph 支持的 HTML 格式。

        Telegraph 支持的标签: a, aside, b, blockquote, br, code, em, figcaption,
        figure, h3, h4, hr, i, iframe, img, li, ol, p, pre, s, strong, u, ul, video

        Args:
            markdown: Markdown 文本

        Returns:
            Telegraph 兼容的 HTML 内容 (JSON 字符串格式)
        """
        # 移除 YAML front matter
        markdown = re.sub(r"^---\n.*?\n---\n", "", markdown, flags=re.DOTALL)

        # 分行处理
        lines = markdown.strip().split("\n")
        nodes: list[dict] = []
        in_code_block = False
        code_block_lines: list[str] = []

        for line in lines:
            # 处理代码块
            if line.startswith("```"):
                if in_code_block:
                    # 结束代码块
                    code_text = "\n".join(code_block_lines)
                    nodes.append({"tag": "pre", "children": [code_text]})
                    code_block_lines = []
                    in_code_block = False
                else:
                    in_code_block = True
                continue

            if in_code_block:
                code_block_lines.append(line)
                continue

            # 跳过空行但保留段落间隔
            if not line.strip():
                continue

            # 处理标题 (Telegraph 只支持 h3, h4)
            if line.startswith("# "):
                nodes.append({"tag": "h3", "children": [self._process_inline(line[2:])]})
            elif line.startswith("## "):
                nodes.append({"tag": "h3", "children": [self._process_inline(line[3:])]})
            elif line.startswith("### "):
                nodes.append({"tag": "h4", "children": [self._process_inline(line[4:])]})
            elif line.startswith("#### ") or line.startswith("##### ") or line.startswith("###### "):
                # h4+ 都转为 h4
                text = re.sub(r"^#+\s*", "", line)
                nodes.append({"tag": "h4", "children": [self._process_inline(text)]})
            # 处理分隔线
            elif re.match(r"^[-*_]{3,}$", line.strip()):
                nodes.append({"tag": "hr"})
            # 处理引用
            elif line.startswith("> "):
                nodes.append({"tag": "blockquote", "children": [self._process_inline(line[2:])]})
            # 处理无序列表 (简化处理)
            elif re.match(r"^[-*+]\s+", line):
                text = re.sub(r"^[-*+]\s+", "", line)
                nodes.append({"tag": "p", "children": ["• " + self._process_inline(text)]})
            # 处理有序列表
            elif re.match(r"^\d+\.\s+", line):
                text = re.sub(r"^\d+\.\s+", "", line)
                nodes.append({"tag": "p", "children": [self._process_inline(text)]})
            # 普通段落
            else:
                nodes.append({"tag": "p", "children": [self._process_inline(line)]})

        # 处理未闭合的代码块
        if code_block_lines:
            code_text = "\n".join(code_block_lines)
            nodes.append({"tag": "pre", "children": [code_text]})

        # 转换为 JSON 字符串
        import json

        return json.dumps(nodes, ensure_ascii=False)

    def _process_inline(self, text: str) -> str:
        """处理行内 Markdown 格式，简化版本只保留纯文本。

        Args:
            text: 包含 Markdown 格式的文本

        Returns:
            处理后的文本
        """
        # 移除链接格式，保留文本
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        # 移除图片
        text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"[图片: \1]", text)
        # 移除加粗
        text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        text = re.sub(r"__([^_]+)__", r"\1", text)
        # 移除斜体
        text = re.sub(r"\*([^*]+)\*", r"\1", text)
        text = re.sub(r"_([^_]+)_", r"\1", text)
        # 移除行内代码
        text = re.sub(r"`([^`]+)`", r"\1", text)
        return text.strip()
