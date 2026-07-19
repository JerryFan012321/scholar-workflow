---
name: sync-projections
description: Rebuild Obsidian paper index tables and sync Notion management projections after ingestion or on demand. Triggers: 'update index', 'rebuild paper table', 'sync Notion', 'update knowledge index', '更新论文表', '同步 Notion', '重建索引'.
---

# sync-projections

## 触发
- 论文导入完成后（library-agent 交接）
- 用户要求重建主题论文表或同步 Notion 结构
- Collection 调整、PDF 迁移或用户要求定期维护

## 步骤

### Obsidian 索引更新
1. 从 Zotero 和状态映射重建目标索引表，不把现有 Obsidian 表当主数据
2. 定位目标文件中的 managed block（`<!-- scholar-workflow:start/end -->`）
3. 只更新 managed block 内的表格行，保留 block 外所有人工内容
4. 大型目录先更新上层描述和子索引，再更新叶级表格
5. 表格必须包含：题名、作者、年份、Venue、Zotero item key、PDF 相对路径、arXiv、DOI、同步时间

### Notion 管理投影
6. 通过稳定 Resource ID upsert，不按标题盲目新建页面
7. 只写机器管理字段（见 `references/notion-schema.md`），不覆盖人工正文
8. 链接指向本地链接解析服务或稳定 Web 入口，不写死绝对 file:// 路径
9. 不上传任何文件

## 约束
- Obsidian 论文表是派生索引，重建依据是 Zotero 和状态映射
- Notion 的 `Sync Revision` 字段用于增量判断，避免不必要覆盖
- 两个子任务可并行执行，但各自独立报告状态
