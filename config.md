# 配置说明

运行机器人前需要设置以下环境变量：

## 必填
- `TELEGRAM_BOT_TOKEN`：Telegram bot token。
- `GITHUB_TOKEN`：GitHub API token（需写权限）。
- `DEFAULT_GITHUB_REPO`：默认目标仓库 `owner/repo`。
- `OPENAI_API_KEY`：兼容 OpenAI 的 LLM API Key。

## 可选
- `DEFAULT_BRANCH`：默认分支，默认为 `main`。
- `DEFAULT_AUTHOR_NAME` / `DEFAULT_AUTHOR_EMAIL`：提交作者信息。
- `OPENAI_BASE_URL`：LLM API Base（默认 `https://api.openai.com/v1`）。
- `OPENAI_MODEL`：模型名称（默认 `gpt-4o-mini`）。

## 运行方式
- 推荐：`python -m websum_bot` 或 `uv run -m websum_bot`。
- 兼容脚本模式：`python ./src/websum_bot/__main__.py`（会自动注入 `src` 到 sys.path）。

## 命令参数速查
- `/summarize <url>` 必填 URL。
- 可选：`repo=owner/repo` `branch=branch` `filename=name.md` `author_name=Name` `author_email=email` `tags=a,b` `categories=c1,c2` `keywords=k1,k2`。

