<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

## WebSum-To-Git Bot Notes

- Python bot entrypoint: `python -m websum_bot`（或 `uv run -m websum_bot`）；依赖见 `requirements.txt`。
- Env vars: `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `DEFAULT_GITHUB_REPO`, `GITHUB_TOKEN`; optional `DEFAULT_BRANCH`, `DEFAULT_AUTHOR_NAME`, `DEFAULT_AUTHOR_EMAIL`, `OPENAI_BASE_URL`, `OPENAI_MODEL`.
- Telegram命令 `/summarize <url> [repo=owner/repo] [branch=branch] [filename=name.md] [author_name=Name] [author_email=email] [tags=a,b] [categories=c1,c2] [keywords=k1,k2]`。
- 摘要流程：抓取HTML→Markdown化保留图片/链接→OpenAI格式LLM重排→添加YAML frontmatter（标题/来源/创建时间/tags/分类/关键词）→提交GitHub仓库根目录。
