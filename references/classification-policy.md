# 分类策略

## 资源类型判断

| 类型 | 判断依据 |
|---|---|
| `paper` | 有 DOI / arXiv ID，或明确是学术论文（有摘要、作者、会议/期刊） |
| `technical_document` | 技术报告、官方文档、教程、规范书、白皮书 |
| `snapshot` | 网页快照（HTML / MHTML / PDF 形式的网页内容） |
| `drawio` | draw.io / diagrams.net 文件 |
| `image` | 图片、截图、图表 |
| `dataset` | 数据集文件或描述文档 |

## 关键规则

- 技术 PDF（如 CUDA 文档、官方手册）即使是 PDF 格式，也是 `technical_document`，不得进入论文流程
- 分类由 intake-agent 确定，用户可纠正；分类确定后才进入下游流程
- 分类冲突时停止并报告，不自动猜测

## 存储目标映射

| 类型 | 存储目标 | 是否创建 Zotero 条目 |
|---|---|---|
| `paper` | `papers_root` | 是 |
| `technical_document` | `vault_root/32-documents/` 对应子目录 | 否（可选 Zotero 书目条目） |
| `snapshot` | `vault_root/32-documents/snapshots/` | 否 |
| `drawio` | `vault_root` 对应项目目录 | 否 |
| `image` | `vault_root` 对应项目目录 | 否 |
| `dataset` | 单独策略，第一阶段只支持元数据 | 否 |
