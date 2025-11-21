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

---

## 项目级 AI 使用约定

本仓库针对 AI/代理类工具（包括本地或云端 LLM 助手）有以下额外约定，用于保证代码质量与安全性。

### 1. 语言与沟通

- 对人类协作者输出时，**默认使用简体中文**。
- 面向终端用户的文案，如无特别说明，也优先使用简体中文。

### 2. 工程原则

- 严格遵循：**KISS / YAGNI / DRY / SOLID**
  - KISS：优先简单直接的实现，不做多层抽象
  - YAGNI：仅实现当前明确需要的功能
  - DRY：避免在不同模块复制逻辑，优先封装公共能力
  - SOLID：保持模块/类具有单一职责，注意依赖倒置
- 新增模块时，应保证：
  - 单一职责清晰（如本项目中的 `html_processor`、`llm_client`、`github_client`、`pipeline`、`bot`）
  - 配置与凭证集中由 `config` 模块管理，而非散落在各处

### 3. 危险操作约束

以下操作在本仓库中被视为高风险，**不得由 AI 自主发起**，如有需要必须由人类显式执行：

- Git 操作：
  - `git commit`, `git push`, `git reset --hard`, `git revert` 等
- 文件系统破坏性操作：
  - 删除目录/文件、批量重命名、移动 `.git` 或配置文件等
- 生产相关配置修改：
  - 涉及真实凭证（Token、PAT、API Key）的变更

AI 可以：
- 创建或修改本地源代码、示例配置（如 `config.example.yaml`）、文档
- 建议 Git 命令和使用方式，但不自动执行

### 4. 配置与敏感信息

- 所有真实凭证须通过：
  - 本地未纳入版本控制的配置文件（如 `config.yaml`），或
  - 环境变量 / 机密管理服务
- 示例文件（如 `config.example.yaml`）中不得包含真实的 Token/PAT。
- 当需要新增配置项时：
  - 优先在 `config.py` 中扩展数据类
  - 更新示例配置和相关文档（README / quickstart / development）

### 5. OpenSpec 使用

- 对于**新能力**、**破坏性变更**或**跨模块大改动**：
  - 必须先在 `openspec/changes` 下创建变更（proposal / tasks / specs）
  - 通过 `openspec validate <change-id> --strict` 校验后再实施
- 对于简单修改（如文档更新、非破坏性配置调整、Bug 修复）：
  - 可在不新增变更的前提下直接修改，但要确保不破坏现有行为

### 6. 文档规范

- 项目核心说明文件：
  - `README.md`：整体介绍与高层用法
  - `docs/quickstart.md`：快速开始，面向使用者
  - `docs/development.md`：开发说明，面向工程师
- 当新增/修改重要行为（特别是用户入口或配置）时，应同步更新相关文档。
