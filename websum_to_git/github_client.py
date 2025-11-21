from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import GitHubConfig


@dataclass
class PublishResult:
    file_path: str
    commit_hash: str | None


class GitHubPublisher:
    """
    GitHub 集成策略：

    - 使用本地缓存目录保存仓库副本，避免每次请求都重新 clone。
    - 若缓存目录不存在，则使用 PAT 进行首次 clone。
    - 若缓存目录已存在，则执行 fetch + pull 更新到最新。
    """

    def __init__(self, config: GitHubConfig) -> None:
        self._config = config
        self._repo_dir: Path | None = None

    def _run_git(self, args: list[str], cwd: Path) -> None:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"git 命令失败: git {' '.join(args)}\n{completed.stderr}")

    def _get_repo_dir(self) -> Path:
        if self._repo_dir is not None:
            return self._repo_dir

        safe_repo = self._config.repo.replace("/", "_")
        # 使用用户家目录下的固定缓存路径，避免因当前工作目录变化导致
        # 出现嵌套的 `.websum_to_git/.websum_to_git/...` 结构
        base_dir = Path.home() / ".websum_to_git" / "repos"
        base_dir.mkdir(parents=True, exist_ok=True)
        repo_dir = base_dir / safe_repo
        self._repo_dir = repo_dir
        return repo_dir

    def _ensure_repo(self) -> Path:
        repo = self._config.repo
        branch = self._config.branch
        pat = self._config.pat

        if not repo or not pat:
            raise ValueError("GitHub 配置缺失 repo 或 pat")

        repo_dir = self._get_repo_dir()
        repo_url = f"https://{pat}@github.com/{repo}.git"

        if not (repo_dir / ".git").exists():
            # 首次 clone
            repo_dir.parent.mkdir(parents=True, exist_ok=True)
            self._run_git(
                ["clone", "--branch", branch, repo_url, str(repo_dir)],
                cwd=repo_dir.parent,
            )
        else:
            # 已存在缓存仓库，仅拉取最新代码
            self._run_git(["fetch", "origin", branch], cwd=repo_dir)
            self._run_git(["checkout", branch], cwd=repo_dir)
            self._run_git(["pull", "--ff-only", "origin", branch], cwd=repo_dir)

        return repo_dir

    def publish_markdown(self, *, content: str, source_url: str, title: str) -> PublishResult:
        repo_dir = self._ensure_repo()
        branch = self._config.branch

        target_dir = repo_dir / self._config.target_dir if self._config.target_dir else repo_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc)
        timestamp_str = now.strftime("%Y%m%d-%H%M%S")
        safe_title = "".join(c if c.isalnum() or c in "-_" else "-" for c in title)[:60] or "note"
        filename = f"{timestamp_str}-{safe_title}.md"
        file_path = target_dir / filename

        file_path.write_text(content, encoding="utf-8")

        rel_path = file_path.relative_to(repo_dir)
        self._run_git(["add", str(rel_path)], cwd=repo_dir)

        commit_message = f"Add note from {source_url} at {timestamp_str}"
        self._run_git(["commit", "-m", commit_message], cwd=repo_dir)
        self._run_git(["push", "origin", branch], cwd=repo_dir)

        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_dir),
            check=False,
            capture_output=True,
            text=True,
        )
        commit_hash = completed.stdout.strip() if completed.returncode == 0 else None

        return PublishResult(file_path=str(rel_path), commit_hash=commit_hash)
