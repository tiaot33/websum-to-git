"""GitHub 专用 Fetcher。

支持多种 GitHub 内容类型:
- 仓库主页: 获取 README
- Issue/PR: 获取内容和评论
- 代码文件: 获取文件内容
- Gist: 获取 Gist 内容

使用 PyGithub 库进行 API 调用。
"""

from __future__ import annotations

import base64
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from re import Pattern
from typing import TYPE_CHECKING

from github import Auth, Github
from github.GithubException import GithubException

from .structs import FetchError, PageContent, get_common_config

if TYPE_CHECKING:
    from websum_to_git.config import AppConfig

logger = logging.getLogger(__name__)


@dataclass
class GitHubFetcher:
    """GitHub 抓取逻辑封装。"""

    config: AppConfig

    def __post_init__(self):
        timeout, verify_ssl = get_common_config(self.config)
        token = self.config.github.pat

        auth = Auth.Token(token) if token else None
        self._github = Github(auth=auth, timeout=timeout, verify=verify_ssl)

        # 路由表: (正则, 处理函数)
        self._routes: list[tuple[Pattern, Callable[[str, re.Match], PageContent]]] = [
            (
                re.compile(r"^https?://gist\.github\.com/(?:[^/]+/)?(?P<gist_id>[a-f0-9]+)$"),
                self._handle_gist,
            ),
            (
                re.compile(r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/blob/(?P<ref>[^/]+)/(?P<path>.+)$"),
                self._handle_file,
            ),
            (
                re.compile(
                    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/(?P<type>issues|pull)/(?P<number>\d+)$"
                ),
                self._handle_issue_or_pr,
            ),
            (
                re.compile(r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)(?:/tree/.*)?$"),
                self._handle_repo,
            ),
        ]

    def fetch(self, url: str) -> PageContent:
        """抓取 GitHub 内容。"""
        logger.info("使用 GitHubFetcher 抓取: %s", url)

        for pattern, handler in self._routes:
            match = pattern.match(url)
            if match:
                return handler(url, match)

        raise FetchError(f"不支持的 GitHub URL 格式: {url}")

    def _handle_gist(self, url: str, match: re.Match) -> PageContent:
        """处理 Gist URL。"""
        gist_id = match.group("gist_id")
        return self._fetch_gist(url, gist_id)

    def _handle_file(self, url: str, match: re.Match) -> PageContent:
        """处理代码文件 URL。"""
        return self._fetch_file(
            url,
            match.group("owner"),
            match.group("repo"),
            match.group("ref"),
            match.group("path"),
        )

    def _handle_issue_or_pr(self, url: str, match: re.Match) -> PageContent:
        """处理 Issue/PR URL。"""
        return self._fetch_issue_or_pr(
            url,
            match.group("owner"),
            match.group("repo"),
            int(match.group("number")),
            is_pr=(match.group("type") == "pull"),
        )

    def _handle_repo(self, url: str, match: re.Match) -> PageContent:
        """处理仓库主页 URL。"""
        return self._fetch_repo_readme(url, match.group("owner"), match.group("repo"))

    def _fetch_repo_readme(self, url: str, owner: str, repo: str) -> PageContent:
        """获取仓库 README。"""
        logger.info("获取仓库 README: %s/%s", owner, repo)

        try:
            gh_repo = self._github.get_repo(f"{owner}/{repo}")
        except GithubException as exc:
            raise FetchError(f"无法获取仓库 {owner}/{repo}: {exc}") from exc

        repo_name = gh_repo.full_name
        description = gh_repo.description or ""
        stars = gh_repo.stargazers_count
        forks = gh_repo.forks_count
        language = gh_repo.language or ""

        # 获取 README
        try:
            readme = gh_repo.get_readme()
            readme_content = base64.b64decode(readme.content).decode("utf-8")
        except GithubException:
            readme_content = "(无 README)"

        # 构建 Markdown
        markdown_parts = []
        markdown_parts.append(f"# {repo_name}")
        markdown_parts.append("")

        if description:
            markdown_parts.append(f"> {description}")
            markdown_parts.append("")

        markdown_parts.append(f"**语言**: {language or '未知'} | **Stars**: {stars} | **Forks**: {forks}")
        markdown_parts.append("")
        markdown_parts.append(f"[查看仓库]({url})")
        markdown_parts.append("")
        markdown_parts.append("---")
        markdown_parts.append("")
        markdown_parts.append("## README")
        markdown_parts.append("")
        markdown_parts.append(readme_content)

        markdown = "\n".join(markdown_parts)
        title = f"{repo_name} - GitHub 仓库"

        return PageContent(
            url=url,
            final_url=url,
            title=title,
            text=f"{description}\n\n{readme_content}",
            markdown=markdown,
            raw_html=f"<article><h1>{repo_name}</h1><p>{description}</p><pre>{readme_content}</pre></article>",
            article_html=f"<article>{readme_content}</article>",
        )

    def _fetch_issue_or_pr(self, url: str, owner: str, repo: str, number: int, is_pr: bool) -> PageContent:
        """获取 Issue 或 PR 内容。"""
        item_type = "PR" if is_pr else "Issue"
        logger.info("获取 %s: %s/%s#%s", item_type, owner, repo, number)

        try:
            gh_repo = self._github.get_repo(f"{owner}/{repo}")
            item = gh_repo.get_pull(number) if is_pr else gh_repo.get_issue(number)
        except GithubException as exc:
            raise FetchError(f"无法获取 {item_type} {owner}/{repo}#{number}: {exc}") from exc

        title = item.title or ""
        body = item.body or ""
        state = item.state
        user = item.user.login if item.user else "unknown"
        created_at = item.created_at.isoformat() if item.created_at else ""
        labels = [label.name for label in item.labels]

        # 获取评论（Issue API 可获取评论，PR 需要通过 issue 获取评论）
        comments: list[dict[str, str]] = []
        try:
            # PR 的评论需要通过 issue 接口获取
            issue = gh_repo.get_issue(number)
            for i, comment in enumerate(issue.get_comments()):
                if i >= 10:  # 最多 10 条评论
                    break
                comment_user = comment.user.login if comment.user else "unknown"
                comment_body = comment.body or ""
                comments.append({"user": comment_user, "body": comment_body})
        except GithubException:
            pass

        # 构建 Markdown
        markdown_parts = []
        markdown_parts.append(f"# {title}")
        markdown_parts.append("")
        repo_url = url.split("/issues/")[0].split("/pull/")[0]
        markdown_parts.append(f"**{item_type}** #{number} in [{owner}/{repo}]({repo_url})")
        markdown_parts.append("")
        markdown_parts.append(f"**状态**: {state} | **作者**: @{user} | **创建时间**: {created_at}")

        if labels:
            markdown_parts.append(f"**标签**: {', '.join(labels)}")

        markdown_parts.append("")
        markdown_parts.append("---")
        markdown_parts.append("")
        markdown_parts.append(body)

        if comments:
            markdown_parts.append("")
            markdown_parts.append("---")
            markdown_parts.append("")
            markdown_parts.append("## 评论")
            for _i, comment in enumerate(comments, 1):
                markdown_parts.append("")
                markdown_parts.append(f"### @{comment['user']}")
                markdown_parts.append("")
                markdown_parts.append(comment["body"])

        markdown_parts.append("")
        markdown_parts.append(f"[查看原文]({url})")

        markdown = "\n".join(markdown_parts)
        full_title = f"{title} · {item_type} #{number} · {owner}/{repo}"

        return PageContent(
            url=url,
            final_url=url,
            title=full_title,
            text=f"{title}\n\n{body}",
            markdown=markdown,
            raw_html=f"<article><h1>{title}</h1><p>{body}</p></article>",
            article_html=f"<article>{body}</article>",
        )

    def _fetch_file(self, url: str, owner: str, repo: str, ref: str, file_path: str) -> PageContent:
        """获取代码文件内容。"""
        logger.info("获取代码文件: %s/%s/%s@%s", owner, repo, file_path, ref)

        try:
            gh_repo = self._github.get_repo(f"{owner}/{repo}")
            file_content = gh_repo.get_contents(file_path, ref=ref)
        except GithubException as exc:
            raise FetchError(f"无法获取文件 {owner}/{repo}/{file_path}: {exc}") from exc

        # get_contents 可能返回列表（目录）或单个文件
        if isinstance(file_content, list):
            raise FetchError(f"路径 {file_path} 是目录，不是文件")

        content = base64.b64decode(file_content.content).decode("utf-8")
        filename = file_path.split("/")[-1]

        # 检测语言
        ext = filename.split(".")[-1] if "." in filename else ""
        lang_map = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "go": "go",
            "rs": "rust",
            "java": "java",
            "rb": "ruby",
            "cpp": "cpp",
            "c": "c",
            "h": "c",
            "md": "markdown",
            "json": "json",
            "yaml": "yaml",
            "yml": "yaml",
            "toml": "toml",
            "sh": "bash",
        }
        language = lang_map.get(ext, "")

        # 构建 Markdown
        markdown_parts = []
        markdown_parts.append(f"# {filename}")
        markdown_parts.append("")
        markdown_parts.append(f"**仓库**: [{owner}/{repo}]({url.split('/blob/')[0]})")
        markdown_parts.append(f"**路径**: `{file_path}`")
        markdown_parts.append(f"**分支/标签**: `{ref}`")
        markdown_parts.append("")
        markdown_parts.append(f"[查看原文件]({url})")
        markdown_parts.append("")
        markdown_parts.append("---")
        markdown_parts.append("")
        markdown_parts.append(f"```{language}")
        markdown_parts.append(content)
        markdown_parts.append("```")

        markdown = "\n".join(markdown_parts)
        title = f"{filename} · {owner}/{repo}"

        return PageContent(
            url=url,
            final_url=url,
            title=title,
            text=content,
            markdown=markdown,
            raw_html=f"<article><h1>{filename}</h1><pre>{content}</pre></article>",
            article_html=f"<article>{content}</article>",
        )

    def _fetch_gist(self, url: str, gist_id: str) -> PageContent:
        """获取 Gist 内容。"""
        logger.info("获取 Gist: %s", gist_id)

        try:
            gist = self._github.get_gist(gist_id)
        except GithubException as exc:
            raise FetchError(f"无法获取 Gist {gist_id}: {exc}") from exc

        description = gist.description or ""
        owner_login = gist.owner.login if gist.owner else "anonymous"
        files = gist.files

        # 构建 Markdown
        markdown_parts = []
        markdown_parts.append(f"# Gist by @{owner_login}")
        markdown_parts.append("")

        if description:
            markdown_parts.append(f"> {description}")
            markdown_parts.append("")

        markdown_parts.append(f"[查看 Gist]({url})")
        markdown_parts.append("")
        markdown_parts.append("---")

        all_content = []
        for filename, file_data in files.items():
            content = file_data.content or ""
            language = (file_data.language or "").lower()
            all_content.append(content)

            markdown_parts.append("")
            markdown_parts.append(f"## {filename}")
            markdown_parts.append("")
            markdown_parts.append(f"```{language}")
            markdown_parts.append(content)
            markdown_parts.append("```")

        markdown = "\n".join(markdown_parts)
        title = f"Gist: {description or gist_id}"

        return PageContent(
            url=url,
            final_url=url,
            title=title,
            text="\n\n".join(all_content),
            markdown=markdown,
            raw_html=f"<article><h1>{title}</h1><p>{description}</p></article>",
            article_html=f"<article>{description}</article>",
        )


def fetch_github(url: str, config: AppConfig) -> PageContent:
    """GitHub Fetcher 入口函数。"""
    fetcher = GitHubFetcher(config)
    return fetcher.fetch(url)
