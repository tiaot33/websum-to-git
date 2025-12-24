# 快速开始（Quick Start）

本指南面向只想“先跑起来”的使用者，默认你具备基础命令行和 GitHub 操作能力。

## 1. 准备环境

1. 确保已安装 Python 3.12+（建议 3.13）  
2. 克隆项目代码：

```bash
git clone <your-fork-or-repo-url>
cd WebSum-To-Git
```

3. 可选：创建虚拟环境

```bash
python -m venv .venv
source .venv/bin/activate  # Windows 用 .venv\Scripts\activate
```

4. 安装依赖：

```bash
pip install -r requirements.txt
```

如需启用无头浏览器抓取/截图，请额外运行（首次即可）：

```bash
pip install -U camoufox[geoip]
python -m camoufox fetch
```

## 2. 准备必要账号与凭证

你需要：

- Telegram Bot Token
  - 在 @BotFather 创建一个 Bot，并获取 Token
- LLM 服务凭证（OpenAI/Responses/Anthropic/Gemini 任一）
  - 获得 API Key 和对应的 `model`；如使用兼容服务，准备 `base_url`
- GitHub PAT（Personal Access Token）
  - 访问 https://github.com/settings/tokens
  - 创建一个 PAT（建议仅授予必要的 `repo` 权限）
  - 准备一个用于存放 Obsidian 笔记的仓库（如 `yourname/your-notes-repo`）
- （可选）Firecrawl API Key，用于兜底抓取短内容

## 3. 配置应用

1. 复制配置示例：

```bash
cp config.example.yaml config.yaml
```

2. 编辑 `config.yaml`，填入你的真实信息：

```yaml
telegram:
  bot_token: "你的 Telegram Bot Token"
  max_concurrent_jobs: 2
  max_queue_size: 50
  max_queue_size_per_chat: 10

llm:
  provider: "openai"        # openai | openai-response | anthropic | gemini
  base_url: "https://api.openai.com"   # openai/openai-response 默认可为空
  api_key: "你的 LLM API Key"
  model: "gpt-4.1-mini"
  enable_thinking: true
  max_input_tokens: 10000   # 长文分片阈值

llm_fast:
  # 可选：用于标签和翻译的快速模型，缺省回退到 llm
  provider: "openai"
  base_url: "https://fast-llm.example.com"
  api_key: "你的 Fast LLM API Key"
  model: "gpt-4o-mini"
  enable_thinking: false
  max_input_tokens: 8000

github:
  repo: "yourname/your-notes-repo"
  branch: "main"
  target_dir: "notes/telegram"
  pat: "你的 GitHub PAT"

firecrawl:
  # 可选：当 Headless 抓取内容 <500 字符时尝试兜底
  api_key: "你的 Firecrawl API Key"

http:
  # 可选：是否在抓取网页时校验 HTTPS 证书
  # 正常情况下请保持为 true；若本地环境证书链异常导致 SSLError，可暂时设为 false（存在安全风险）
  verify_ssl: true
```

其中 `llm` 用于网页摘要生成，`llm_fast`（可选）用于标签与翻译，可指向不同端口/模型以获得更低时延或成本；若未配置 `llm_fast`，系统会退回到 `llm`。

> 提示：请务必不要将包含真实密钥的 `config.yaml` 提交到 GitHub 公共仓库。

## 4. 运行服务

在项目根目录执行：

```bash
python src/main.py --config config.yaml
```

启动成功后，你应当能在控制台看到类似：

```text
INFO telegram.ext._application - Application started
```

若希望通过容器运行，可使用仓库提供的 `docker-compose.yaml`：

```bash
docker compose up --build -d
```

确保 `config.yaml` 位于项目根目录，并已绑定到容器中的 `/app/config.yaml`（默认 compose 文件已完成此映射）。

## 5. 在 Telegram 中使用

1. 打开你在 @BotFather 创建的 Bot 对话框  
2. 发送 `/start`，Bot 会提示你发送 HTML 网页地址  
3. 发送一条包含 HTML URL 的消息，例如：

```text
帮我总结一下这篇文章：https://example.com/some-article.html
```

4. Bot 会回复：
   - 先提示“已入队/排队中”，并在后台异步抓取与总结
   - 完成后返回 GitHub 文件路径/commit，含删除按钮，可一键删除本次提交
   - 若发布 Telegraph 成功，会附上预览链接
5. 截图：发送 `/url2img https://example.com` 获取整页截图（Camoufox）
6. 队列状态：发送 `/status` 查看本会话与全局队列状态

## 6. 在 Obsidian 中查看

1. 将你的 GitHub 仓库目录作为 Obsidian Vault 打开（或作为子目录挂载）
2. 在 `target_dir` 对应目录（例如 `notes/telegram`）中找到刚生成的 Markdown 文件
3. 打开文件，你将看到：
   - YAML front matter：`source/created_at/tags`
   - 摘要正文：以 `#` 开头的 AI 标题
   - 原文区：统一一级标题；非中文时包含“原文（中文翻译）”与“原文（原语言）”

> 说明：图片由抓取器原样保留在正文 Markdown 内（取决于目标网页/Fetcher）。

## 7. 常见问题

- **Bot 没有响应？**
  - 检查终端日志中是否有错误信息
  - 确保网络环境能访问 Telegram Bot API 和 LLM 服务

- **GitHub 没有生成文件？**
  - 确认 PAT 权限和 `repo/branch/target_dir` 是否正确
  - 检查日志是否有 GitHub API 报错

- **抓取结果太短/为空？**
  - 默认使用 Headless 抓取；若内容 <500 字符且配置了 Firecrawl，会自动重试 Firecrawl
  - 部分站点需要 Camoufox，确保已安装并运行 `python -m camoufox fetch`
  - 对登录墙/强脚本站点，尝试手动打开确认可见性

如果你需要更深入的定制或开发，请参考 `docs/development.md`。
