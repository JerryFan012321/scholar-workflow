---
name: build-literature-tree
description: Generate evidence-based literature lineage graphs, timelines, and method evolution trees for a research topic. Triggers: 'literature tree', 'paper lineage', 'research evolution', 'follow-up papers', '文献脉络', '论文发展树', '画出发展脉络', 'NeRF 到 3DGS'.
---

# build-literature-tree

## 触发
- 用户要求生成某主题的论文时间线、发展脉络、follow-up 关系或贡献图

## 步骤

1. 从 Zotero Collection、论文索引或用户列表确定论文集合
2. 读取分层索引，按需获取论文摘要或引言（不全量读取）
3. 生成候选引用边（`cites`）和方法关系边
4. 为每条非纯引用关系提取证据：论文原文位置、摘要依据、置信度
5. 区分关系类型：`cites` / `follow-up` / `method-extension` / `representation-shift` / `benchmark-successor` / `contradicts`
6. 标记里程碑候选，提交用户审核低置信边和里程碑判断
7. 用户审核后保存规范化 `literature-graph.json`
8. 生成 Mermaid / draw.io / HTML 可视化；PNG 是渲染副产品，不是唯一数据源
9. 可选：输出 Notion 简洁大纲投影

## 约束
- 每条非 `cites` 边必须包含：`evidence`（来源、位置、摘要）、`confidence`、`review_status`
- 引用关系只能证明"有引用"，不能单独证明方法继承或突破
- 无证据不得自动标记"里程碑"或"突破性贡献"
- 图数据写入前必须取得用户批准
- 输出格式遵循 `contracts/literature-graph.schema.json`
