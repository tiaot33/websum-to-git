## Context
- 需求：tgbot接收HTML URL，生成总结并提交到指定GitHub仓库根目录。
- 现状：无现有代码或spec，需定义最小可行流程，限制在单次HTML处理（不做爬虫）。

## Goals / Non-Goals
- Goals: 单命令完成URL→总结→GitHub提交；可预测或用户自定义文件名；成功/失败均给用户反馈。
- Non-Goals: 多页面爬取、需要登录的页面抓取、仓库初始化/权限管理、定时/批量任务、消息队列。

## Decisions
- 输入：Telegram命令接受HTTP(S) URL与目标仓库owner/repo，可选分支（缺省用配置的默认分支）、可选文件名、可选作者名/邮箱。
- 总结格式：Markdown，文首YAML frontmatter包含标题（若可用）、来源URL、创建时间、tags、分类、关键词；正文包含摘要段落与关键要点列表；使用兼容OpenAI格式的外部LLM生成，无硬性长度上限，同时要求重排但不遗漏源内容中的有用信息、图片、链接。
- 抓取与提取：直接下载HTML，去除script/style等噪声，优先提取主内容；若无法提取则回退到全文文本提要。
- 文件命名：默认仓库根目录文件名格式`summary-<yyyyMMddHHmm>-<slug>.md`，slug来源于域名或页面标题的安全化片段；允许用户覆盖文件名。
- 提交信息：提交消息包含源URL与生成时间；凭证使用具备repo权限的token；允许覆盖提交作者信息。
- 失败处理：任何阶段失败都不写入GitHub；向用户返回失败原因（不含敏感token），日志记录错误以便排查。

## Risks / Trade-offs
- 主体内容提取可能不准：采用简单启发式，必要时可回退到全文摘要。
- GitHub权限或分支缺失导致失败：需在命令前校验输入并在错误信息中提示缺少权限或分支不存在。
- 总结质量依赖外部模型/实现：初始版本保持简单摘要模板，可后续改进。

## Open Questions
- None at this time.
