from __future__ import annotations

from datetime import datetime, timezone

from .config import AppConfig
from .github_client import GitHubPublisher, PublishResult
from .html_processor import PageContent, fetch_html, fetch_html_headless, parse_page
from .llm_client import LLMClient


class HtmlToObsidianPipeline:
    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._llm = LLMClient(config.llm)
        self._publisher = GitHubPublisher(config.github)

    def process_url(self, url: str) -> PublishResult:
        if self._config.http.fetch_mode == "headless":
            html, final_url = fetch_html_headless(url)
        else:
            html, final_url = fetch_html(
                url,
                verify=self._config.http.verify_ssl,
            )
        page = parse_page(url=url, html=html, final_url=final_url)

        summary_md = self._llm.summarize_page(
            title=page.title,
            url=page.final_url,
            body_text=page.text,
        )

        full_markdown = self._build_markdown(page=page, summary_markdown=summary_md)

        return self._publisher.publish_markdown(
            content=full_markdown,
            source_url=page.final_url,
            title=page.title,
        )

    def _build_markdown(self, *, page: PageContent, summary_markdown: str) -> str:
        now = datetime.now(timezone.utc).isoformat()
        front_matter_lines = [
            "---",
            f"source_url: {page.final_url}",
            f"created_at: {now}",
            f"title: {page.title}",
            "---",
            "",
        ]

        body_lines: list[str] = []
        body_lines.append(f"# {page.title}")
        body_lines.append("")
        body_lines.append(summary_markdown.strip())
        body_lines.append("")

        if page.image_urls:
            body_lines.append("## Images")
            body_lines.append("")
            for img in page.image_urls:
                body_lines.append(f"![]({img})")
            body_lines.append("")

        return "\n".join(front_matter_lines + body_lines)
