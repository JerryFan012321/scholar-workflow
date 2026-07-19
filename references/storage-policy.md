# 存储策略

## 主存储分配

| 对象 | 权威主库 | 根目录配置 |
|---|---|---|
| 论文书目、分类、标签、附件关系 | Zotero 数据库 | Zotero 自管理 |
| 论文 PDF | Zotero 管理的 linked_file | `papers_root` |
| 个人知识、笔记、技术文档 | Obsidian Vault | `vault_root` |
| 知识大纲、项目、任务 | Notion | Notion 云端 |
| 插件运行状态 | 状态库 | `SCHOLAR_WORKFLOW_HOME` |

## 不变量

1. 论文 PDF 只存放于 `papers_root`，技术文档即使是 PDF 也进 Vault，不得互换
2. 一篇论文最多对应一个 Zotero 父条目和一个主 PDF 附件
3. Obsidian 论文表是可重建的派生索引，不是论文主库
4. Notion 不上传文件（论文、技术文档、图片、数据文件）
5. 状态库只记录映射、游标、任务状态和审计，不保存知识正文
6. Notion 中的机器字段可以更新；人工撰写内容不得被同步程序覆盖

## PDF 迁移规则

PDF 位置迁移必须通过配置变更和 Zotero 附件关系完成，不得在多个目录复制副本。
