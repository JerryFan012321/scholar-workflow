# build-literature-tree

为某研究主题构建基于证据的文献脉络图:时间线、方法演化、follow-up 关系和贡献图。

每条非引用边(`follow-up`、`method-extension`、`representation-shift`、
`benchmark-successor`、`contradicts`)都必须携带证据、置信度和审核状态。单凭引用
关系不能证明方法继承或突破,里程碑也不会在无证据时被自动标记。

持久化规范化的 `literature-graph.json`(主数据),并渲染 Mermaid / draw.io / HTML
视图。图数据写入前必须取得用户批准。

完整流程与约束见 [SKILL.md](./SKILL.md)。
