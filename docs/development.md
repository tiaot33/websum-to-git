# 开发文档（Development Guide）

本文面向希望在本项目基础上二次开发或维护的工程师，假设你熟悉 Python、Git、Telegram Bot 和基础的 HTTP/LLM 调用。

## 架构概览

整体架构是一个单进程 Python 服务，使用 Telegram 长轮询（`run_polling`）作为入口：

1. `websum_to_git.bot.TelegramBotApp` 负责：
   - 从 Telegram 消息中抽取第一个 URL
   - 调用 `HtmlToObsidianPipeline` 执行业务流程
   - 将结果反馈给用户
2. `websum_to_git.pipeline.HtmlToObsidianPipeline` 串联：
   - 抓取网页 HTML（`html_processor.fetch_html`）
   - 解析正文与图片（`html_processor.parse_page`）
   - 调用 LLM 生成 Markdown 总结（`llm_client.LLMClient.summarize_page`）
   - 组装最终 Obsidian Markdown（带 YAML front matter 与图片引用）
   - 调用 GitHub 发布（`github_client.GitHubPublisher.publish_markdown`）
3. 配置集中在 `config.yaml`，由 `websum_to_git.config.load_config` 加载。

### 模块职责

- `websum_to_git/config.py`
  - 定义 `AppConfig` / `TelegramConfig` / `LLMConfig` / `GitHubConfig`
  - 从 YAML 加载配置并进行基本校验（必填字段）
- `websum_to_git/html_processor.py`
  - `fetch_html(url)`: 使用 `requests` 获取 HTML
  - `parse_page(url, html, final_url)`: 使用 `BeautifulSoup`:
    - 清理 `script/style/noscript`
    - 从 `<title>` 获取标题（fallback 为最终 URL）
    - 从 `<body>` 提取纯文本正文
    - 提取 `<img>` 标签并用 `urljoin` 转为绝对 URL
- `websum_to_git/llm_client.py`
  - `LLMClient.summarize_page(...)`: 调用 OpenAI 格式 `/v1/chat/completions`
  - 控制提示词、温度、最长正文长度等
- `websum_to_git/github_client.py`
  - `GitHubPublisher.publish_markdown(...)`:
    - 使用 PAT 通过 HTTPS 克隆指定 repo/branch 至临时目录
    - 写入 Markdown 文件到 `target_dir`
    - `git add` / `git commit` / `git push`
- `websum_to_git/pipeline.py`
  - `HtmlToObsidianPipeline.process_url(url)`：组合所有步骤
  - `_build_markdown(...)`：整合 front matter + 摘要 + 图片列表
- `websum_to_git/bot.py`
  - 消息匹配、URL 抽取、错误处理、运行入口（`run_bot`）
- `websum_to_git/main.py`
  - CLI 入口，解析 `--config` 参数并启动 Bot

## 本地开发流程

### 环境准备

1. 创建虚拟环境（推荐）

```bash
python -m venv .venv
source .venv/bin/activate  # Windows 使用 .venv\Scripts\activate
```

2. 安装依赖

```bash
pip install -r requirements.txt
```

3. 准备配置文件

```bash
cp config.example.yaml config.yaml
```

根据需要填入：
- Telegram Bot Token
- LLM base_url / api_key / model
- GitHub repo / branch / target_dir / pat

> 提醒：请不要把包含真实凭证的 `config.yaml` 提交到 Git 仓库。

### 运行调试

1. 直接运行模块入口：

```bash
python -m websum_to_git.main --config config.yaml
```

2. 或在调试器中运行 `websum_to_git/main.py` 的 `main()`。

3. 在 Telegram 中向 Bot 发送一个 HTML 页面 URL，观察日志与行为。

### 日志

`websum_to_git/main.py` 使用 `logging.basicConfig` 设置日志级别为 `INFO`。如需更详细日志，可修改为：

```python
logging.basicConfig(level=logging.DEBUG, ...)
```

或在单个模块中增加更细粒度的日志。

## 扩展与修改建议

### 修改 LLM 提示词或模型

- 修改位置：`websum_to_git/llm_client.py:23` 的 `system_prompt`
- 修改模型：在配置文件 `config.yaml` 中调整 `llm.model`
- 定制建议：
  - 若 Obsidian 有统一模版，可在 system prompt 中要求固定结构
  - 若需要中英双语总结，也可以在 prompt 中显式说明

#### 选择不同的 LLM Provider

配置文件 `llm` 段支持：

- `provider: "openai"`（默认）
  - 使用 `openai` 官方 SDK，支持 `base_url` 自定义（用于兼容 OpenAI 格式服务）
- `provider: "anthropic"`
  - 使用 `anthropic` 官方 SDK（messages API）
  - `base_url` 字段目前忽略
- `provider: "gemini"`
  - 使用 `google-generativeai` SDK
  - `base_url` 字段目前忽略

所有 provider 均共享字段：

- `api_key`: 对应服务的 API Key
- `model`: 模型名称（如 `gpt-4.1-mini`、`claude-3.5-sonnet`、`gemini-1.5-pro` 等）

### 调整 Markdown 结构

- 修改位置：`websum_to_git/pipeline.py:_build_markdown`
- 当前结构：
  - YAML front matter（`source_url`、`created_at`、`title`）
  - `# 标题`
  - LLM 输出的摘要内容
  - 可选的 `## Images` + `![](url)` 列表
- 可扩展方向：
  - 增加标签字段（如 `tags`）到 front matter
  - 将图片段落改为折叠块、表格或分组展示

### 支持更多消息格式

当前只处理文本消息中出现的第一个 URL：

- 匹配正则：`websum_to_git/bot.py:URL_REGEX`
- 如需：
  - 支持多 URL：可在正则上用 `findall` 并循环处理
  - 支持按钮/命令：在 `bot.py` 中添加更多 `CommandHandler` 或 `CallbackQueryHandler`

### GitHub 集成策略

当前策略：**缓存 GitHub 仓库，只在需要时重新 clone，正常情况下仅 pull 最新代码**。

- 缓存路径：默认使用项目根目录下的 `.websum_to_git/repos/<owner_repo>`（`/` 替换为 `_`）
- 首次运行：
  - 若缓存目录不存在，则使用 PAT 执行 `git clone --branch <branch> https://PAT@github.com/owner/repo.git`
- 后续运行：
  - 若缓存目录已存在：
    - 执行 `git fetch origin <branch>`
    - 执行 `git checkout <branch>`
    - 执行 `git pull --ff-only origin <branch>`

写入文件与提交仍在缓存仓库内完成：

- 在 `target_dir` 子目录下创建 Markdown 文件
- `git add` + `git commit` + `git push origin <branch>`

如需修改缓存策略（例如缓存目录位置或清理逻辑），可调整：

- 位置：`websum_to_git/github_client.py:31` 的 `_get_repo_dir`
- 同步逻辑：`websum_to_git/github_client.py:43` 的 `_ensure_repo`

## 测试建议

当前项目没有内置测试框架，你可以按需添加（如 `pytest`），但建议：

- 单元测试：
  - `html_processor.parse_page`：给定固定 HTML，断言提取的标题、正文和图片 URL
  - `pipeline._build_markdown`：给定 `PageContent` 和摘要，断言生成 Markdown 中：
    - front matter 字段存在
    - 图片 URL 全部出现在 `![](url)` 中
- 集成测试（需要准备测试仓库与 Bot）：
  - 使用测试 PAT 和测试 repo
  - 用真实 HTML URL 执行一次完整流程，确认生成文件在目标目录出现

## OpenSpec 相关

关于本次能力的规范与变更，请参考：

- 变更：
  - `openspec/changes/add-tgbot-html-to-obsidian/proposal.md`
  - `openspec/changes/add-tgbot-html-to-obsidian/tasks.md`
- 能力规范：
  - `openspec/changes/add-tgbot-html-to-obsidian/specs/html-to-obsidian-sync/spec.md`

如需对行为进行重大修改（如多格式输入、双向同步、增量更新等），建议先新增对应的 OpenSpec 变更再动手实现。

