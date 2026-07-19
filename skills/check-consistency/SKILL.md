---
name: check-consistency
description: Audit cross-system consistency across Zotero, papers_root, Obsidian indexes, and Notion projections. Report drift, orphaned files, stale entries, and broken links. Read-only — never auto-fixes. Triggers: 'check consistency', 'audit library', 'find drift', 'check sync status', '检查库状态', '审计一致性', '有没有漂移'.
---

# check-consistency

## 触发
- 用户要求检查库状态或执行定期维护
- audit-agent 主动触发

## 步骤

1. 确定检查范围（全量 / 指定 Collection / 指定 Vault 目录 / 指定 Notion 项目）
2. **Zotero 检查**：条目是否存在、是否重复、Collection 分配是否正确
3. **文件检查**：PDF 是否存在于 `papers_root`，SHA-256 与附件记录是否一致
4. **Obsidian 检查**：索引行的 Zotero key 是否可解析，PDF 路径是否有效
5. **Notion 检查**：Resource ID 是否重复，本地链接服务 URL 是否可解析
6. **分层索引检查**：上层索引描述是否与实际子目录内容一致
7. 汇总漂移报告：孤立 PDF、失效 key、陈旧索引行、失效链接、重复条目
8. 输出结构化 JSON 报告，可选生成 Markdown 摘要

## 约束
- 全程只读，不修复、不删除任何发现的问题
- 报告中标注每项问题的严重程度（error / warning / info）和建议修复方式
- 修复操作需用户确认后由对应 Agent 执行，不在此 Skill 内完成
