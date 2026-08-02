# sync-projections

在导入完成后或按需维护知识库的派生投影。

- **Obsidian 索引** —— 从 Zotero 和状态映射重建论文索引表,只写 managed block 内部,
  保留 block 外的全部人工内容。
- **Notion 投影** —— 按稳定 Resource ID upsert,只写机器管理字段。不上传文件、
  不覆盖人工内容。

Obsidian 论文表是可重建的派生索引,不是主数据。两个子任务可并行执行。

完整流程与约束见 [SKILL.md](./SKILL.md)。
