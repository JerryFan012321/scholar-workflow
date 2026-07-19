# Obsidian 索引格式

## Managed Block 结构

论文索引文件中，managed block 包裹机器维护的表格部分，block 外的内容不得被程序修改：

```markdown
# 主题名称 论文索引

这里保留人工说明和笔记。

<!-- scholar-workflow:start -->
| 论文 | 作者 | 年份 | Venue | Zotero | PDF | arXiv | DOI | 同步时间 |
|---|---|---:|---|---|---|---|---|---|
| 论文标题 | 作者A等 | 2024 | CVPR | [key](zotero://...) | [pdf](../31-papers/...) | [2401.01234](https://arxiv.org/abs/2401.01234) | 10.xxxx | 2024-01-15 |
<!-- scholar-workflow:end -->

这里继续保留人工笔记。
```

## 必须包含的列

| 列 | 说明 |
|---|---|
| 论文 | 题名，可含 Zotero 链接 |
| 作者 | 第一作者 + 等 |
| 年份 | 发表年份 |
| Venue | 会议或期刊缩写 |
| Zotero | `zotero://select/library/items/{key}` 链接 |
| PDF | 相对于 vault_root 的相对路径链接 |
| arXiv | arXiv 链接（无则留空） |
| DOI | DOI 链接（无则留空） |
| 同步时间 | ISO 日期 |

## 分层索引结构

```
领域总览.md（子领域列表 + 简介）
  └── 子领域/
        └── 主题论文索引.md（managed block 论文表）
```

读取原则：先读上层索引，判断是否需要深入，再拉取叶级实体文件。
