# ingest-resource

把论文导入、把技术文档归档到本地库,分两个阶段:

- **计划(dry-run)** —— 分类资源、规范化标识符、对状态库和 Zotero 判重、推荐
  Zotero Collection / Vault 分类,并输出结构化 `action-plan.json`。不写任何外部系统。
- **执行** —— 需要有效且已批准的 `plan_id`。论文 PDF 只从 arXiv 下载并校验,再经
  `ZoteroWriteAdapter` 写入。技术文档复制进 Vault 并写来源/散列元数据。

论文 PDF 只进 `papers_root`,技术文档只进 Vault。Zotero Bridge 不可用时失败关闭。

完整流程与约束见 [SKILL.md](./SKILL.md)。
