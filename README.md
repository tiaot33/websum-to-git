# WebSum-To-Git Bot

Telegram 机器人：接收 HTML 页面地址，提取内容并通过兼容 OpenAI 的 LLM 重排为可读 Markdown 笔记（包含 YAML frontmatter），随后提交到指定 GitHub 仓库根目录。

## 功能
- `/summarize <url>`：抓取 HTML，保留图片/链接，LLM 重排生成 Markdown，添加 frontmatter（标题/来源/创建时间/tags/分类/关键词），提交到 GitHub。
- 可选参数：`repo=owner/repo` `branch=branch` `filename=name.md` `author_name=Name` `author_email=email` `tags=a,b` `categories=c1,c2` `keywords=k1,k2`。

## 快速开始
```bash
pip install -r requirements.txt   # 或 uv pip install -r requirements.txt
python -m websum_bot              # 或 uv run -m websum_bot
```

## 运行前置
- 创建一个 Telegram Bot（BotFather）获取 `TELEGRAM_BOT_TOKEN`。
- 准备具备目标仓库写权限的 `GITHUB_TOKEN`。
- 准备兼容 OpenAI API 的 LLM Key（默认 API 为 `https://api.openai.com/v1`）。

## 环境变量
- 必填：
  - `TELEGRAM_BOT_TOKEN`：Telegram bot token。
  - `GITHUB_TOKEN`：GitHub API token（需要 repo 写权限）。
  - `DEFAULT_GITHUB_REPO`：默认 `owner/repo`。
  - `OPENAI_API_KEY`：外部 LLM key。
- 可选：
  - `DEFAULT_BRANCH`（默认 `main`）
  - `DEFAULT_AUTHOR_NAME`, `DEFAULT_AUTHOR_EMAIL`（覆盖 commit 作者）
  - `OPENAI_BASE_URL`（默认 `https://api.openai.com/v1`）
  - `OPENAI_MODEL`（默认 `gpt-4o-mini`）

## 命令使用示例
```
/summarize https://example.com/article \
  repo=owner/repo branch=main filename=note.md \
  author_name=Bot author_email=bot@example.com \
  tags=ai,summary categories=tech keywords=llm,summarization
```

## 运行方式
- 推荐：`python -m websum_bot` 或 `uv run -m websum_bot`。
- 兼容：`python ./src/websum_bot/__main__.py`（脚本模式会自动注入 `src` 到 sys.path）。

## 流程简述
1) 解析命令参数（URL、仓库、分支、文件名、作者、frontmatter 列表）。
2) 抓取并解析 HTML，归一化链接，转换为 Markdown（保留图片/链接）。
3) 调用外部 LLM 重排 Markdown，提升可读性但不新增事实。
4) 构造 YAML frontmatter + 正文，生成唯一或用户指定文件名。
5) 通过 GitHub Contents API 提交到指定仓库/分支，返回路径/commit 链接。

## 开发与测试
- 运行测试：`pytest`（需安装 `requirements.txt`）。
- 关键代码位置：
  - 命令解析：`src/websum_bot/command_parser.py`
  - HTML 抓取/转换：`src/websum_bot/html_extractor.py`
  - LLM 调用：`src/websum_bot/llm_client.py`
  - 笔记构建：`src/websum_bot/markdown_note.py`
  - GitHub 提交：`src/websum_bot/github_client.py`
  - Bot 入口：`src/websum_bot/bot.py`, `src/websum_bot/__main__.py`

