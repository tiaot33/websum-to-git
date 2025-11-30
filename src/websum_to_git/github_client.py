from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from datetime import datetime

import requests

from .config import GitHubConfig

logger = logging.getLogger(__name__)


@dataclass
class PublishResult:
    file_path: str
    commit_hash: str | None


class GitHubPublisher:
    def __init__(self, config: GitHubConfig) -> None:
        self._config = config
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self._config.pat}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "websum-to-git",
            }
        )
        self._api_base = "https://api.github.com"

    def publish_markdown(self, *, content: str, source: str, title: str) -> PublishResult:
        if not self._config.repo or not self._config.pat:
            raise ValueError("GitHub 配置缺失 repo 或 pat")

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

        encoded_content = base64.b64encode(content.encode("utf-8")).decode("ascii")

        commit_message = f"Add note from {source} at {timestamp_str}"

        url = f"{self._api_base}/repos/{self._config.repo}/contents/{path}"
        payload = {
            "message": commit_message,
            "content": encoded_content,
            "branch": self._config.branch,
        }

        logger.info("发送 GitHub API 请求: PUT %s", url)
        response = self._session.put(url, json=payload, timeout=10)
        if response.status_code not in (200, 201):
            logger.error("GitHub API 请求失败: %d %s", response.status_code, response.text)
            raise RuntimeError(f"GitHub API 创建文件失败: {response.status_code} {response.text}")

        logger.info("GitHub API 响应成功, 状态码: %d", response.status_code)

        data = response.json()
        commit_hash: str | None = None
        if isinstance(data, dict):
            commit = data.get("commit")
            if isinstance(commit, dict):
                commit_hash = commit.get("sha")

        logger.info("文件已发布, commit hash: %s", commit_hash)
        return PublishResult(file_path=path, commit_hash=commit_hash)
