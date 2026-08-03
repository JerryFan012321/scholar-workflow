# build-literature-tree

按彭思达的 literature tree 方法，为某研究方向构建一棵 **novelty tree**。它是一棵三级分类树，
内部节点是抽象概念、叶子是论文：

```
里程碑任务(问题) → pipeline / representation(方案) → 论文(叶)
```

每个概念节点记录它的 **novelty 锚点** —— 首个提出该任务/pipeline 的论文。树旁并存一份
扁平的**全集论文列表**(paper list)：收集到的全部论文，其中一篇可以在册但尚未归类进树。

一个主题的全部内容放在一个以主题命名的文件夹里。索引文件用图书馆编码前缀：`01-Paperlist.md`
是固定的扁平全集账本，每棵树/视图是带编号的笔记(`02-…文献树.md`、`03-…`)。一棵树渲染为
一个自包含笔记 —— 内联 Mermaid 概览，然后是嵌套的 `##` 任务 / `###` pipeline 小节，各自
带 novelty 锚点、可选的内容简介、以及论文列表(subpaperlist)。每篇论文另有一个 `paper_assets/`
下的相关资料笔记，其 `# 相关文献树` 小节反向链接回它在树中的位置。渲染幂等 —— 受管标记之外
的内容原样保留。规范化文档符合 `contracts/literature-tree.schema.json`。

完整流程与约束见 [SKILL.md](./SKILL.md)。
