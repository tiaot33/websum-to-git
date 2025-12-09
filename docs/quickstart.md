# 快速开始（Quick Start）

本指南面向只想“先跑起来”的使用者，默认你具备基础命令行和 GitHub 操作能力。

## 1. 准备环境

1. 确保已安装 Python 3.10+  
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

如需启用无头浏览器模式，请额外运行（首次即可）：

```bash
pip install -U camoufox[geoip]
python -m camoufox fetch
```

## 2. 准备必要账号与凭证

你需要：

- Telegram Bot Token
  - 在 @BotFather 创建一个 Bot，并获取 Token
- LLM 服务凭证（OpenAI 格式）
  - 例如 OpenAI 官方、兼容 OpenAI 的国内外服务
  - 获得一个 API Key 和对应的 `base_url`、`model` 名称
- GitHub PAT（Personal Access Token）
  - 访问 https://github.com/settings/tokens
  - 创建一个 PAT（建议仅授予必要的 `repo` 权限）
  - 准备一个用于存放 Obsidian 笔记的仓库（如 `yourname/your-notes-repo`）

## 3. 配置应用

1. 复制配置示例：

```bash
cp config.example.yaml config.yaml
```

2. 编辑 `config.yaml`，填入你的真实信息：

```yaml
telegram:
  bot_token: "你的 Telegram Bot Token"

llm:
  # provider 可选: openai / openai-response / anthropic / gemini
  provider: "openai"
  # 对于 openai/openai-response/anthropic/gemini 兼容服务，可通过 base_url 自定义地址
  base_url: "https://api.openai.com"
  api_key: "你的 LLM API Key"
  model: "gpt-4.1-mini"

llm_fast:
  # 可选：用于标签和翻译的快速模型，通常指向更便宜/延迟更低的端口
  provider: "openai"
  base_url: "https://fast-llm.example.com"
  api_key: "你的 Fast LLM API Key"
  model: "gpt-4o-mini"

github:
  repo: "yourname/your-notes-repo"
  branch: "main"
  target_dir: "notes/telegram"
  pat: "你的 GitHub PAT"

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
python  src/main.py --config config.yaml
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
   - 先提示“已收到链接，正在抓取网页并调用 LLM 总结，请稍候……”
   - 完成后告知：生成的 Markdown 文件在 GitHub 仓库中对应的路径，例如：

```text
处理完成，已将笔记保存到 GitHub 目录中的文件: notes/telegram/20250101-123000-some-article-title.md
Commit: <commit-hash>
```

## 6. 在 Obsidian 中查看

1. 将你的 GitHub 仓库目录作为 Obsidian Vault 打开（或作为子目录挂载）
2. 在 `target_dir` 对应目录（例如 `notes/telegram`）中找到刚生成的 Markdown 文件
3. 打开文件，你将看到：
   - YAML front matter：包含 `source`、`created_at`、`title`
   - LLM 生成的正文摘要
   - 末尾的 `## Images` 段落，列出正文中出现的图片（`![](url)`）

这些远程图片将直接在 Obsidian 中加载显示。

## 7. 常见问题

- **Bot 没有响应？**
  - 检查终端日志中是否有错误信息
  - 确保网络环境能访问 Telegram Bot API 和 LLM 服务

- **GitHub 没有生成文件？**
  - 检查日志中是否有 `git` 相关错误
  - 确认 PAT 是否有足够权限，且没有开启额外的 2FA 限制
  - 确认 `repo`、`branch`、`target_dir` 配置无误

- **图片没有出现在 Markdown 中？**
  - 检查网页 HTML 中图片是否在 `<body>` 内，且 `<img src="...">` 能被访问
  - 当前实现会保留解析到的所有 `img` 的绝对 URL，并在 `## Images` 段落中统一展示

如果你需要更深入的定制或开发，请参考 `docs/development.md`。
