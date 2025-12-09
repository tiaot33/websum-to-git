from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, cast

from github import Github, GithubException

from .config import GitHubConfig

if TYPE_CHECKING:
    from github.ContentFile import ContentFile
    from github.Repository import Repository

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    file_path: str
    commit_hash: str | None
    web_url: str | None  # GitHub 文件的 Web 链接


class GitHubPublisher:
    def __init__(self, config: GitHubConfig) -> None:
        self._config = config
        if not self._config.pat:
            raise ValueError("GitHub PAT is missing")
        self._client = Github(self._config.pat)
        self._repo_obj: Repository | None = None

    @property
    def repo(self) -> Repository:
        if self._repo_obj is None:
            if not self._config.repo:
                raise ValueError("GitHub repo name is missing")
            self._repo_obj = self._client.get_repo(self._config.repo)
        return self._repo_obj

    def publish_markdown(self, *, content: str, source: str, title: str) -> PublishResult:
        logger.info("准备发布 Markdown 到 GitHub, 仓库: %s, 分支: %s", self._config.repo, self._config.branch)

        now = datetime.now()
        timestamp_str = now.strftime("%Y%m%d-%H%M%S")
        safe_title = "".join(c if c.isalnum() or c in "-_" else "-" for c in title)[:60] or "note"
        filename = f"{timestamp_str}-{safe_title}.md"

        if self._config.target_dir:
            target_dir = self._config.target_dir.rstrip("/")
            path = f"{target_dir}/{filename}"
        else:
            path = filename

        logger.info("目标文件路径: %s", path)

        commit_message = f"Add note from {source} at {timestamp_str}"
        
        try:
            # Create file using PyGithub
            # content should be str or bytes. PyGithub handles encoding.
            result = self.repo.create_file(
                path=path,
                message=commit_message,
                content=content,
                branch=self._config.branch,
            )
            
            commit = result.get("commit")
            commit_hash = commit.sha if commit else None
            
            # 构建 Web URL (PyGithub result 中包含 content 但 web url 可能需要自己拼或者从 content 获取 html_url)
            # content_file = result.get("content")
            # web_url = content_file.html_url if content_file else ...
            # 为了保持一致性和减少请求，手动构建通常也可以，但使用返回的 html_url 更准确
            content_obj: ContentFile | None = result.get("content")  # type: ignore
            web_url = content_obj.html_url if content_obj else f"https://github.com/{self._config.repo}/blob/{self._config.branch}/{path}"

            logger.info("GitHub 发布成功, commit: %s, url: %s", commit_hash, web_url)
            return PublishResult(file_path=path, commit_hash=commit_hash, web_url=web_url)

        except GithubException as e:
            logger.error("GitHub API 操作失败: %s", e)
            raise RuntimeError(f"GitHub 发布失败: {e}") from e

    def delete_file(self, file_path: str) -> str:
        """删除指定路径的文件。返回 commit hash。"""
        logger.info("正在删除 GitHub 文件: %s", file_path)
        try:
            # 获取文件的 SHA
            contents = self.repo.get_contents(file_path, ref=self._config.branch)
            if isinstance(contents, list):
                # 应该是个文件，如果是目录会返回列表
                raise RuntimeError(f"路径指向一个目录而非文件: {file_path}")
            
            # PyGithub 的类型定义较为动态，显式转换为 ContentFile 以满足静态检查
            from github.ContentFile import ContentFile
            content_file = cast(ContentFile, contents)
            
            message = f"Delete {file_path} via WebSum Bot"
            result = self.repo.delete_file(
                path=content_file.path,
                message=message,
                sha=cast(str, content_file.sha),
                branch=self._config.branch
            )
            
            commit = result.get("commit")
            commit_hash = commit.sha if commit else "unknown"
            logger.info("文件已删除: %s, commit: %s", file_path, commit_hash)
            return commit_hash
            
        except GithubException as e:
            logger.error("删除文件失败: %s", e)
            raise RuntimeError(f"无法删除文件 {file_path}: {e}") from e
