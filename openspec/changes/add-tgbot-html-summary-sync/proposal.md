# Change: Telegram bot summarizes HTML URLs into GitHub

## Why
- Users need to pass an HTML页面链接给tgbot并持久存储总结，便于复用和协作。

## What Changes
- 新增Telegram命令，接受单个HTML地址和目标GitHub仓库（owner/repo，可选分支），把总结存入仓库根目录。
- 抓取并提取HTML主体内容，调用兼容OpenAI格式的外部LLM生成Markdown笔记（长度不做硬性限制），在文首添加YAML frontmatter记录标题、来源、创建时间、tags、分类、关键词，并在正文保留并重排有用信息、图片与链接。
- 分支来自配置的默认值，可按请求指定；允许用户自定义提交作者和文件名，提交信息引用源URL；对抓取、总结或GitHub写入失败提供可见错误。

## Impact
- Affected specs: tgbot-html-summary
- Affected code: Telegram命令处理、HTML抓取与提取、总结生成、GitHub客户端/鉴权配置
