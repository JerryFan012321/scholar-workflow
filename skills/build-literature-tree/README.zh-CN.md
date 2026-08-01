# build-literature-tree

按彭思达的 literature tree 方法，为某研究方向构建一棵 **novelty tree**。它是一棵三级分类树，
内部节点是抽象概念、叶子是论文：

```
里程碑任务(问题) → pipeline / representation(方案) → 论文(叶)
```

每个概念节点记录它的 **novelty 锚点** —— 首个提出该任务/pipeline 的论文。树旁并存一份
扁平的**全集论文列表**(paper list)：收集到的全部论文，其中一篇可以在册但尚未归类进树。

结果渲染为 Obsidian 受管块笔记：主题根笔记承载内联 Mermaid 概览与全集论文列表，每个概念
笔记承载其 novelty 锚点，以及 MOC 双链列表或论文表格。渲染幂等 —— 受管标记之外的内容原样
保留。规范化文档符合 `contracts/literature-tree.schema.json`。

完整流程与约束见 [SKILL.md](./SKILL.md)。
