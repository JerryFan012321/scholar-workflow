# build-literature-tree

## 既有论文单元导航

`knowledge list --paper-units --source-id SOURCE_UUID --field-id FIELD_UUID --language zh`
只组合选定领域的本地论文及显式引用，复用论文包，保留全部用途和资料、分析、Canvas、
笔记入口与缺失/冲突诊断。有安全且唯一的阅读器映射时提供 Obsidian 直接链接，列清单本身
不打开应用、不写文件。它不刷新 Zotero 书目，也不替换固定 `01-Paperlist.md`。
此模式自 **0.43.0** 提供；详见[导航契约](references/field-paper-units.md)。
安装、原生阅读和人工可读性分别判断。
补充文件仅按 provider 或便携附件清单中的明确关系纳入；缺失、不安全和冲突均保留诊断。
列清单不读取附件内容，也不把已记录的哈希当作本次完整性核验。

## 逐贡献演进预览

自 0.43.0 提供 `literature-preview --input evolution.json --format md|json`：
校验四类 novelty、主/支/局部位置，显示紧凑纵向归属概览及带原文页级入口的完整技术取舍。
复用论文身份，不复制论文正文；不读取配置、登记库或原文件，不写任何内容。
真实科学支持、最终可编辑图和外观人工评鉴分别待验；
详见[预览契约](references/evolution-preview.md)。

## 现有概念分类视图

为某研究方向构建一棵 **novelty tree**。它是一棵可变深度的分类树，
内部节点是抽象概念、叶子是论文。两种同构的树共用一套结构与渲染器，靠节点 kind 区分：

```
技术路线树：里程碑任务 → pipeline / representation(方案) → module(可选) → 论文(叶)
挑战洞见树：challenge(挑战) → insight(洞见) → 论文(叶)
```

每个概念节点记录它的 **novelty 锚点**——在该树声明的语料范围内，有证据支持、最早引入该
任务/pipeline/module/insight 的论文（类 1/2/3 及 insight 首创）。若无法确定优先关系则保持
未解析，不把有限语料中的最早记录写成全局“第一篇”。只是**改进**已有 pipeline 的论文（类 4）
作普通成员挂在被改进节点下、不记锚点。每棵树旁并存一份扁平的**全集论文列表**（paper list）：
收集到的全部论文，其中一篇可以在册但尚未归类，也可以同时出现在多棵树里。

一个主题的全部内容放在一个以主题命名的文件夹里。索引文件用图书馆编码前缀：`01-Paperlist.md`
是固定的扁平全集账本，每棵树/视图是带编号的笔记(`02-…文献树.md`、`03-…`)。一棵树渲染为
一个自包含笔记 —— 内联 Mermaid 概览，然后是嵌套的概念小节(任务/挑战为 `##`、pipeline/insight
为 `###`、module 为 `####`)，各自带 novelty 锚点、可选的内容简介、以及论文列表(subpaperlist)。
新论文的相关资料笔记位于 `resources/papers/<稳定论文目录段>/论文信息.md`，其 `# 相关文献树`
小节反向链接回它在树中的位置；分析 Markdown、Canvas、sidecar 与其他 Scholar 附属笔记同处该
论文文件夹，原 PDF 仍由 Zotero 保存。目录段与稳定论文身份的映射由清单保存，不从标题临时推断。
现有 `paper_assets/*.md` 保持原路径，未经审议不自动迁移。渲染幂等 —— 受管标记之外
的内容原样保留。规范化文档符合 `contracts/literature-tree.schema.json`。

完整流程与约束见 [SKILL.md](./SKILL.md)。
