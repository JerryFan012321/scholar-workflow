# 独立知识目录登记测试

对象：新增 public knowledge registration-plan/register/list。先合成输入，后实现与测试。

| 输入与操作 | 独立预期 |
|---|---|
| 三个 Markdown 的清洁子目录，重复 plan | 零写入、摘要相同、导航完整；临时 UUID 不影响确认 |
| 根据摘要在新 CLI 进程 register | 仅一个 Field；正文原字节；原 registry 路径；list 可读 |
| 整 Vault 两个候选，选择一个 | manifest 只含所选 Field，不登记兄弟 |
| 没有明确选择/多个模式/未知 Field/相对或 symlink 根 | 拒绝，无持久写入 |
| plan 后正文、Canvas、任意 JSON、根 inode、manifest 或 registry 变化 | 旧摘要拒绝，无登记 |
| legacy 分析名/机器标记、受管 frontmatter、任意名 baseline、固定23128链接 | simple registration 拒绝；联合事务保持必要 |
| symlink 文件或目录/FIFO/非 UTF-8/超限文本 | 安全拒绝，不跟随、不阻塞 |
| 已有 portable Source 的显式 attach | source/field IDs 与 manifest/正文原样，只新增 host registry |
| 错误摘要/确认取消 | 零写入；不得把失败标成功 |

执行：定向新 CLI contracts + 既有 Field/Hub registration contracts；完整 tests/unit tests/contract；
新模块/tests Ruff、技能 frontmatter、diff。临时合成目录无真实业务操作。

安装态：正常 runtime-only 发布 hotfix 0.36.0 和 pipx/Codex 安装后，test 新独立“模范知识目录-0.36.0”
先写两份人类说明，公开 plan → digest-bound register → list。只登记该新目录，不登记整个 test。
资料说明以原生链接指向已经存在的 V-JEPA2 Markdown/Canvas，不复制/重新分析，不伪造 canonical owner。
计划/结果机器记录放 Source 外的同级展示目录，避免记录写入使批准摘要失效。
旧论文包三文件 hash 前后不变。新目录 manifest 与 host root 映射真实存在；这不等于旧分析正式归档。
需要人评鉴：在 Obsidian 打开说明，点击正文/Canvas，判断导航是否方便；未确认前 pending。
