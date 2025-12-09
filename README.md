# WebSum-To-Git

使用 Telegram Bot + LLM，将网页（HTML 地址）总结为 Obsidian 友好的 Markdown 笔记，并自动提交到 GitHub 指定仓库和目录。

核心流程：

1. 用户在 Telegram 中向 Bot 发送包含 HTML 网页链接的消息  
2. 服务抓取网页 HTML，抽取正文与图片链接  
3. 调用 LLM（支持 OpenAI / Anthropic / Gemini），对正文内容进行结构化总结，生成 Markdown  
4. 将生成的 Markdown 作为新文件提交到配置好的 GitHub 仓库与目录  

适用场景：
- 将碎片化的网页阅读（技术文章、博客、资料）沉淀到 Obsidian 知识库
- 最小成本接入：只需部署一个 Python 服务 + Telegram Bot + GitHub PAT

## 功能特性

- Telegram Bot 接收消息中的第一个 `http/https` URL
- 自动抓取目标网页 HTML，提取标题、正文、图片
- 通过统一封装调用多家 LLM：
  - `openai`：支持官方 OpenAI 以及 OpenAI 格式兼容服务（可配置 `base_url`）
  - `anthropic`：调用 Anthropic SDK（如 Claude 系列）
  - `gemini`：调用 Google Gemini（`google-generativeai` SDK）
- 输出 Obsidian 友好的 Markdown，包含：
  - 标题与正文总结
  - YAML front matter（包含来源 URL、创建时间、标题）
  - 正文图片链接（`![](url)` 形式）
- 使用 GitHub PAT 将笔记以新文件形式提交到指定仓库及子目录

## 目录结构

```bash
.
├── AGENTS.md                 # OpenSpec 及本项目给 AI/代理的说明
├── CLAUDE.md                 # 与 AGENTS.md 类似的说明文件
├── README.md                 # 概览与使用介绍（当前文件）
├── config.example.yaml       # 配置示例，不含真实凭证
├── requirements.txt          # Python 依赖
├── websum_to_git/            # 核心 Python 实现
│   ├── __init__.py
│   ├── bot.py                # Telegram Bot 入口与消息处理
│   ├── config.py             # 配置模型与加载
│   ├── github_client.py      # GitHub clone/commit/push 封装
│   ├── html_processor.py     # HTML 抓取与解析、图片 URL 提取
│   ├── llm_client.py         # 多 Provider LLM 调用封装（openai/anthropic/gemini）
│   ├── main.py               # CLI 入口（运行 Bot）
│   └── pipeline.py           # HTML → LLM 总结 → Markdown → GitHub 管道
└── openspec/                 # OpenSpec 变更与规范
    ├── AGENTS.md
    ├── project.md
    └── changes/add-tgbot-html-to-obsidian/...
```

更多面向开发者的细节与扩展方式，请参考 `docs/development.md`。快速上手可以直接看 `docs/quickstart.md`。

## 快速开始

如果你只想尽快跑起来，可以直接参考 `docs/quickstart.md`。核心步骤如下：

1. 安装依赖：`pip install -r requirements.txt`
2. 准备配置：复制 `config.example.yaml` 为 `config.yaml` 并填入真实凭证
3. 运行服务：`python -m websum_to_git.main --config config.yaml`
4. 在 Telegram 中向 Bot 发送包含 HTML 网页链接的消息

## 运行环境要求

- Python 3.10+（推荐）
- 能访问：
  - Telegram Bot API
  - 你配置的 LLM 服务（OpenAI / Anthropic / Gemini 等）
  - GitHub（用于 git clone / push）

## 抓取方式与 Headless 支持

系统会根据 URL 自动选择合适的 Fetcher：

- 优先尝试针对 Twitter、GitHub 等站点的专用抓取器
- 其后使用基于 `requests` 的轻量抓取器处理大多数页面
- 如安装了 Camoufox，将在必要时使用 Headless 浏览器作为兜底抓取方案

关于如何为特定网站添加自定义 Headless 抓取策略（例如处理复杂的动态网页），请参考 [Headless 策略指南](docs/headless_strategies.md)。


如需启用基于 Camoufox 的 Headless 抓取，请先安装依赖：

```bash
pip install -U camoufox[geoip]
python -m camoufox fetch
```

在 Linux 服务器上如遇到缺失系统依赖，请安装 Firefox 运行依赖：`libgtk-3-0`、`libdbus-glib-1-2`、`libxt6`、`libx11-xcb1`、`libasound2` 等。

## Docker 部署

仓库根目录提供了 `Dockerfile`，基于 `python:3.13-slim` 构建，已预装 Camoufox (Firefox)：

```bash
docker build -t websum-to-git .
docker run --rm \
  -v $(pwd)/config.yaml:/app/config.yaml \
  websum-to-git
```

容器内通过 `JobQueue` 定期在 `/tmp/websum_bot_heartbeat` 写入心跳文件，Docker `HEALTHCHECK` 会检测该心跳是否在最近一段时间内更新，以此判断 Bot 主循环是否仍然健康运行。

如需使用自定义配置路径，可在 `docker run` 时覆盖命令，例如：`docker run ... websum-to-git python src/main.py --config /app/your-config.yaml`。

也可使用 `docker-compose.yaml`：

```bash
docker compose up --build -d
```

确保在同级目录放置 `config.yaml`（或通过修改 compose 文件绑定其他配置路径）。

## 安全注意事项

- **不要** 将真实的 `config.yaml` 提交到 Git 仓库
- GitHub PAT 建议权限最小化（仅仓库所需的 `repo` 权限）
- 如需在生产环境使用，请结合你自己的密钥管理方案（环境变量、密钥管理服务等）

## 设计原则

本项目实现遵循以下工程原则：

- KISS：模块划分清晰，每个模块只做一件事
- YAGNI：只实现当前需求（Telegram → LLM → GitHub），不做未使用的泛化
- DRY：HTML 解析、LLM 调用、Git 操作分别封装，避免在 Bot 处理逻辑中重复
- SOLID：
  - 单一职责：`html_processor`、`llm_client`、`github_client`、`pipeline`、`bot` 各司其职
  - 依赖倒置：核心流程依赖配置与抽象封装，而非具体实现细节
