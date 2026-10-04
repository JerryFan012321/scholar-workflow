# 已有论文包只读检查：独立测试方案

对象：一个显式目录中的三个显式文件，不扫描 Vault、不生成论文或写登记。
新命令 `analysis check-bundle DIRECTORY --markdown NAME --canvas NAME --sidecar NAME`。
可选 `--require-ir 5` 防止把旧格式当新模板；默认人类 Markdown，另有 JSON。

## 输入与预期

- 沿用冻结的 synthetic scalar reader v5 输入：38 条独立内容，五分支；与真实 V-JEPA 无关。
- 合法生成的成对文件和其 sidecar：退出0，列五分支、38条内容、实际节点数，三个原始文件hash。
- 编辑正文、删除原文链接、删除正文反链、同层节点横移、插入交叉连线：退出7，保留原始finding。
- sidecar基线hash改动：退出7，不重新信任、不修复。
- Markdown文件名与 note_stem 不同：退出7（实际Vault反链不可用）。
- 无关 Advanced Canvas 安全metadata可接受；不放行其他额外顶层字段。
  v5原始拒绝代码为 `invalid-json-canvas-contract`（不是v1-v3的 `invalid-canvas-shape`）。
- v4合法包仍能按v4检查；明确要求5时退出7，不自动转换。
- 原始hash独立以三份文件逐字节计算对比，不将Canvas受管语义hash当文件hash；相对目录拒绝。
- 缺文件、目录/文件symlink、越界或绝对子文件名、重复文件、超限/非UTF8/坏JSON/重复JSON键：退出2。
- FIFO与读取中变动拒绝；仅检查一组冻结读取字节，不称为事务或可信批准。
- 中英文标签一致；用户标题按文字转义。正文科学支持、当前PDF真实性、GUI可读性及正式登记均未检验。
- 所有运行：目录和状态home前后完全相同，无Hub、Zotero、cmux或网络调用。

## 执行与影响

先定向新contract与既有v5格式/安全测试，再完整 `tests/unit tests/contract`。
检查改动文件Ruff、skill frontmatter和diff；保留已有无关改动和历史CLI四项import排序问题。
正常提交、runtime发布和安装后只检查原0.32.3 V-JEPA2单篇包；记录三个文件与registry前后hash。
输出报告和截图只放test新“论文包检查-0.35.0”文件夹，原件零改写。
用户人工评鉴：报告可读；由报告打开正文/Canvas，观察五分支、对齐、无交叉、留白和源链接。
自动通过不等于人工通过，也不等于Source/Field联合事务已完成。
