---
name: ingest-resource
description: Import papers or archive technical documents into the local library. Handles planning (dry-run) and execution (requires approved plan). Triggers: 'import paper', 'add to Zotero', 'archive document', 'file this PDF', '导入论文', '加入 Zotero', '归档技术文档', '把这篇论文加入'.
---

# ingest-resource

## 触发
- 用户给出论文列表或候选，希望加入系统
- 用户要求归档技术文档、网页快照、draw.io 或其他非论文技术资料
- 用户批准某个导入计划（持有 `plan_id`）

## 步骤

### 阶段一：计划（永远 dry-run）
1. 分类资源 `kind`（paper / technical_document / snapshot / drawio / image）
2. 规范化 DOI、arXiv ID、标题、作者、年份
3. 检查输入批次、状态库、目标目录、Zotero（判重）
4. 论文：推荐 Zotero Collection 和 Obsidian 索引位置
5. 技术文档：推荐 Vault 分类目录
6. 生成结构化 `action-plan.json`，展示新增、更新、跳过、冲突、下载目标
7. 等待用户批准，返回 `plan_id`

### 阶段二：执行（必须持有有效 plan_id）
8. 验证 `plan_id`、输入散列、配置版本和批准状态
9. 论文：从 arXiv 下载 PDF 到临时目录，校验 %PDF / 大小 / SHA-256
10. 论文：调用 `ZoteroWriteAdapter` upsert 条目和 linked_file
11. 技术文档：下载或复制到 Vault 对应分类，写来源/时间/散列元数据
12. 返回 Zotero key、PDF 路径、Vault 路径等回执

## 约束
- 阶段一永远不写外部系统
- 阶段二没有有效 `plan_id` 不得执行
- 计划内容变化时旧批准自动失效
- 论文 PDF 只放 `papers_root`；技术文档只放 Vault——禁止互换
- arXiv 无 PDF 时记录元数据和候选状态，不从其他来源获取
- Bridge 健康检查失败时停止，不回退到 Local API 或其他旁路
- 身份冲突时停止该条目，不影响批次中其他安全条目
