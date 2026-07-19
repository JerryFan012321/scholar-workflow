# scholar-workflow

面向 Claude Code 的"先计划后执行"学术资源管理插件。导入论文、归档技术文档、保持
Obsidian 索引与 Notion 投影同步、构建基于证据的文献脉络图 —— 全程带确定性安全检查,
任何外部写入前都有明确的批准门控。

[English](./README.md)

## 架构

Claude 负责理解、推荐和审批交互;确定性 CLI(`src/scholar_workflow/`)负责可测试、
可恢复的执行。Zotero 是论文主库,所有写入经统一的 `ZoteroWriteAdapter` 通过自研
Zotero Bridge 完成。Obsidian 保存知识和派生索引;Notion 保存管理投影。文件始终留在
本地唯一主存储。

## Skills

| Skill | 用途 |
|---|---|
| find-resource | 搜索论文、核验身份、定位已有资源 |
| ingest-resource | 导入论文 / 归档技术文档(先计划后执行) |
| sync-projections | 重建 Obsidian 索引表、同步 Notion 投影 |
| build-literature-tree | 构建基于证据的文献脉络图 |
| check-consistency | 跨系统一致性审计(只读) |

## 开发

开发规范与行为边界见 [AGENT.md](./AGENT.md),版本历史见 [CHANGELOG.md](./CHANGELOG.md)。

```
pytest tests/unit tests/contract
```
