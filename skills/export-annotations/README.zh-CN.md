# export-annotations

把你在 Zotero 中对某篇论文所做的批注整理成结构化的 Obsidian 笔记。

只读取一篇论文的全部高亮、笔记和你写的评论,剥离翻译插件(Translate)追加的机器翻译,
再按论证逻辑重新组织 —— 你的评论作主干,高亮原文作佐证。页码以 `(p.N)` 内联标注附在
每条上,不作为排序依据。

全程只读,绝不写入 `zotero.sqlite`。若该论文在 vault 中已有分析笔记,则另建一篇独立的
批注笔记,两篇通过 frontmatter 交叉链接。

完整流程与约束见 [SKILL.md](./SKILL.md)。
