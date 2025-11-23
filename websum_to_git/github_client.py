from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

from .config import GitHubConfig


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

    def publish_markdown(self, *, content: str, source_url: str, title: str) -> PublishResult:
        if not self._config.repo or not self._config.pat:
            raise ValueError("GitHub 配置缺失 repo 或 pat")

        now = datetime.now(timezone.utc)
        timestamp_str = now.strftime("%Y%m%d-%H%M%S")
        safe_title = "".join(c if c.isalnum() or c in "-_" else "-" for c in title)[:60] or "note"
        filename = f"{timestamp_str}-{safe_title}.md"

        if self._config.target_dir:
            target_dir = self._config.target_dir.rstrip("/")
            path = f"{target_dir}/{filename}"
        else:
            path = filename

        encoded_content = base64.b64encode(content.encode("utf-8")).decode("ascii")

        commit_message = f"Add note from {source_url} at {timestamp_str}"

        url = f"{self._api_base}/repos/{self._config.repo}/contents/{path}"
        payload = {
            "message": commit_message,
            "content": encoded_content,
            "branch": self._config.branch,
        }

        response = self._session.put(url, json=payload, timeout=10)
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"GitHub API 创建文件失败: {response.status_code} {response.text}"
            )

        data = response.json()
        commit_hash: str | None = None
        if isinstance(data, dict):
            commit = data.get("commit")
            if isinstance(commit, dict):
                commit_hash = commit.get("sha")

        return PublishResult(file_path=path, commit_hash=commit_hash)
