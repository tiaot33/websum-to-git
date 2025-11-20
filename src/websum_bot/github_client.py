from __future__ import annotations

"""Minimal GitHub Contents API client for committing markdown notes."""

import base64
from dataclasses import dataclass
from typing import Optional

import requests

from .config import GithubConfig


class GithubError(Exception):
    pass


@dataclass
class CommitResult:
    path: str
    commit_url: str | None


@dataclass
class GithubClient:
    config: GithubConfig

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "WebSumToGitBot/0.1",
        }

    def commit_file(
        self,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: Optional[str] = None,
        author_name: Optional[str] = None,
        author_email: Optional[str] = None,
    ) -> CommitResult:
        if not repo or "/" not in repo:
            raise GithubError("Repository must be in the form owner/repo")

        endpoint = f"https://api.github.com/repos/{repo}/contents/{path}"
        payload: dict[str, object] = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch or self.config.default_branch,
        }

        committer: dict[str, str] = {}
        name = author_name or self.config.default_author_name
        email = author_email or self.config.default_author_email
        if name and email:
            committer = {"name": name, "email": email}
            payload["committer"] = committer

        try:
            resp = requests.put(endpoint, headers=self._headers(), json=payload, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            message = exc.response.text if getattr(exc, "response", None) is not None else str(exc)
            raise GithubError(f"GitHub commit failed: {message}") from exc

        data = resp.json()
        commit_url = None
        if isinstance(data, dict):
            commit_url = data.get("commit", {}).get("html_url")

        return CommitResult(path=path, commit_url=commit_url)
