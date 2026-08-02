# check-consistency

审计 Zotero、`papers_root`、Obsidian 索引和 Notion 投影之间的跨系统一致性。检测
孤立 PDF、失效 Zotero key、陈旧索引行、失效本地链接和重复 Resource ID。

全程只读:报告漂移并标注严重程度和建议修复方式,但不修复、不删除任何内容。修复
操作在用户确认后由对应 Agent 执行。

输出结构化 JSON 报告,可选附 Markdown 摘要。

完整流程与约束见 [SKILL.md](./SKILL.md)。
