# 开发文档（Development Guide）

本文面向需要二次开发或维护的工程师，默认你熟悉 Python、Telegram Bot、HTTP/LLM/GitHub API。

## 架构概览

单进程服务，Telegram 长轮询作为入口：

1) `bot.TelegramBotApp`  
   - 抽取消息中的第一个 URL，或处理 `/url2img`、删除回调  
   - 将任务入队，由调度器受控并发执行（避免多任务时阻塞 update 处理）  
2) `pipeline.HtmlToObsidianPipeline`  
   - `fetchers.fetch_page`：显式路由（GitHub 专用）→ Camoufox Headless → Firecrawl 兜底（内容 <500 且配置）  
   - `_summarize_page`：tiktoken 估算，短内容跳过 LLM，长内容分片总结  
   - `_generate_tags`：使用 fast_llm（可选）  
   - `_build_markdown`：front matter + 摘要；原文区统一一级标题，非中文先译后原文  
   - GitHub 发布（PyGithub 直接创建文件），Telegraph 预览（失败不致命）  
3) 配置集中 `config.py`，支持 fast_llm、firecrawl、http.verify_ssl。

Markdown 输出要点：front matter 包含 `source/created_at/tags`；摘要从 `#` 开始；原文区使用 `# 原文`，非中文时再加 `# 原文（中文翻译）` 与 `# 原文（原语言）`。

## 模块职责

- `config.py`：`AppConfig` 及子配置；`load_config` 校验必填字段，OpenAI/Responses 默认 base_url。  
- `bot.py`：命令 `/start` `/help` `/status` `/url2img`，消息 URL 入队处理，删除回调写入 GitHub，心跳文件 `/tmp/websum_bot_heartbeat`。  
- `task_queue.py`：in-memory 任务队列与并发控制（全局并发 + 单 Chat 顺序）。  
- `pipeline.py`：抓取→摘要/翻译→Markdown→GitHub/Telegraph；常量 `MIN_CONTENT_FOR_SUMMARY=500`。  
- `fetchers/__init__.py`：路由表 + Headless 兜底 + Firecrawl 回退；`MIN_CONTENT_FOR_RETRY=500`；导出 `PageContent`、`FetchError`、`capture_screenshot`。  
- `fetchers/headless.py` + `headless_strategies/*`：Camoufox 抓取，策略注册表（Twitter 登录遮挡/数据提取，HuggingFace iframe 跳转等）。  
- `fetchers/camoufox_helper.py`：惰性加载 Camoufox，自动滚动，移除 Cookie/弹窗遮罩。  
- `fetchers/firecrawl.py`：Firecrawl API 抓取 markdown/html，带元数据兜底。  
- `fetchers/github.py`：PyGithub 路由仓库/Issue/PR/文件/Gist，生成 Markdown。  
- `fetchers/screenshot.py`：Camoufox 全页截图（`/url2img` 使用）。  
- `markdown_chunker.py`：Markdown 结构分片，tiktoken 估算。  
- `llm_client.py`：OpenAI / OpenAI-Response / Anthropic / Gemini 客户端，支持 thinking 配置与超时。  
- `github_client.py`：PyGithub 直接创建/删除文件（不使用 git clone）。  
- `telegraph_client.py`：匿名账户创建 + Markdown→Telegraph JSON 简化转换。

## 本地开发流程

### 环境准备

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
# 若需 Headless 抓取/截图
pip install -U camoufox[geoip]
python -m camoufox fetch
```

复制配置：

```bash
cp config.example.yaml config.yaml
```

填入 Telegram Token、LLM（可选 fast_llm）、GitHub PAT/repo/branch/target_dir、可选 Firecrawl API Key、http.verify_ssl。

### 运行调试

```bash
python src/main.py --config config.yaml
```

在 Telegram 发送 URL 测试。`/url2img <url>` 可验证截图链路。删除按钮会调用 GitHub 删除对应文件。

### 日志

`main.py` 默认 INFO。需要更详细可设为 DEBUG 或对单模块调高 logger 级别。

## LLM 配置说明

- provider：`openai`（chat.completions）、`openai-response`（responses）、`anthropic`（messages）、`gemini`（generative ai）。  
- `enable_thinking`：为兼容的 provider 启用 thinking/reasoning；可在 fast_llm 关闭以加速标签/翻译。  
- `max_input_tokens`：摘要/翻译分片阈值，默认 10000（fast_llm 默认 8000 示例）。  
- fast_llm：若未配置则回退到 llm。

## Markdown 结构调整

- 位置：`pipeline._build_markdown`。  
- front matter：`source/created_at/tags`。  
- 原文标题：全部一级标题；非中文时先译再原文。  
- 提示词在 `src/websum_to_git/prompts/`，可按需修改摘要/标签/翻译模板。

## 扩展指南

- **新增 Headless 策略**：在 `fetchers/headless_strategies/custom.py` 使用 `@route("example.com", wait_selector="...")`；可提供 `process`/`extract`/`build`。  
- **新增专用 Fetcher**：在 `fetchers/__init__.py` 的 `ROUTERS` 添加匹配器与 handler（签名 `handler(url, config) -> PageContent`）。  
- **LLM Provider 扩展**：扩展 `config.py` provider 值，`llm_client.py` 添加 `_generate_with_xxx` 分支。  
- **输出格式**：改 `pipeline._build_markdown` 和相关 prompts。

## GitHub 发布策略

- 使用 PyGithub `create_file`，文件名 `{timestamp}-{safe_title}.md`，可选 `target_dir`。  
- 删除：`GitHubPublisher.delete_file` 获取 SHA 后删除（Bot 删除按钮使用）。  
- 无 git clone/缓存逻辑，如需自定义命名或目录规则在 `github_client.py` 修改。

## 测试建议

- fetchers 路由与回退：专用 GitHub 命中、Headless 成功、Firecrawl 触发阈值。  
- headless_strategies：Twitter 登录遮挡移除、数据提取完整性；HuggingFace iframe 跳转。  
- pipeline：短内容跳过摘要、长文本分片/合并、翻译分片、原文标题 H1。  
- markdown_chunker：标题换块、超长代码块、空文本。  
- llm_client：各 provider 调用参数（thinking 配置），回退路径。  
- github_client：创建/删除异常处理、路径生成。  
- bot：删除回调链路、`/url2img` 错误处理、心跳文件写入。  
- telegraph_client：Markdown 转换（front matter 去除、代码块/标题映射）。

## OpenSpec

重大能力/破坏性修改前参考 `openspec/AGENTS.md` 与 `openspec/changes/*`，按需新增 proposal/task/spec 并验证。
