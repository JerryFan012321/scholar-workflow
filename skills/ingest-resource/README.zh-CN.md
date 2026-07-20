# ingest-resource

把论文导入、把技术文档归档到本地库,分两个阶段:

- **计划(dry-run)** —— `scholar-workflow plan <inputs...>` 分类资源、规范化标识符、
  对状态库和 Zotero 判重,输出结构化计划(每个资源 create / skip / conflict)。不写任何
  外部系统。把计划呈现给用户,等待对话中批准 —— 不落盘、无 plan 文件。
- **执行** —— 用户批准后,`scholar-workflow apply <inputs...>` 从 arXiv 下载论文 PDF
  并校验,落入 `paper_inbox` 收件箱。Zotero 无本地写 API,导入由用户手动完成。技术文档
  复制进 Vault 并写来源/散列元数据。

下载的论文 PDF 只进 `paper_inbox`,技术文档只进 Vault。元数据由 Zotero Local API 只读提供。

完整流程与约束见 [SKILL.md](./SKILL.md)。
