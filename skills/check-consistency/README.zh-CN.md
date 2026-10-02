# check-consistency

审计 Zotero、Obsidian 索引和 Notion 投影之间的跨系统一致性。检测
孤立 PDF、失效 Zotero key、陈旧索引行、失效附件身份链接、旧固定端口链接和重复 Resource ID。

全程只读:报告漂移并标注严重程度和建议修复方式,但不修复、不删除任何内容。修复
操作在用户确认后由对应 Agent 执行。

对话中默认输出人类可读的 Markdown 报告：范围与结论、问题及证据和处理建议、覆盖缺口。
数据源不可用不能算作「没有问题」。按需提供结构化 JSON，明确的机器调用可以只返回 JSON；
未要求时不另外创建报告文件。

完整流程与约束见 [SKILL.md](./SKILL.md)。
