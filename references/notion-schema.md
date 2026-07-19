# Notion 数据库结构

## 机器管理字段（sync 程序可写）

| 字段名 | 类型 | 说明 |
|---|---|---|
| Resource ID | Text | 幂等 upsert 主键，格式同 resource_id |
| Name | Title | 题名或文档名 |
| Type | Select | Paper / TechnicalDocument / Dataset / Project |
| Category | Select | 知识类目 |
| Project | Relation | 所属项目页面 |
| Status | Select | 阅读/研究/项目状态 |
| Zotero Item Key | Text | 论文跳转链接 |
| Local URL | URL | `http://127.0.0.1:23128/open/...` |
| Web Source | URL | arXiv / DOI / 原始网站 |
| Sync Revision | Text | 内容散列，用于增量判断 |
| Last Synced | Date | 最近机器更新时间 |

## 人工字段（sync 程序禁止修改）

- Summary（知识摘要）
- Notes（人工备注）
- Priority（人工优先级）
- 所有 Relation 字段的目标页面内容

## 同步规则

- 通过 Resource ID upsert，不按标题新建
- 只更新上表中的机器管理字段
- `Sync Revision` 不变时跳过更新
- 不上传任何文件内容到 Notion
