# Source 与阅读器分离：独立测试

## 输入与预期

合成 Obsidian registry 包含一个真实目录及其子目录 Source。
`resolve_obsidian_vault_id` 的旧接口仅接受精确 Vault；新 reader resolver 可接受其子目录，
返回唯一包含它的已登记 Vault。无匹配、重复/嵌套匹配、symlink、registry 非普通文件或不安全权限
均拒绝，且不启动应用。两项能力都只读取 registry，不读取插件秘密配置。

`knowledge reader SOURCE_ID` 只报告打开位置，`knowledge open SOURCE_ID RELATIVE_PATH`
只允许启用且具有 read 能力的 Source 中实际存在的 Markdown/Canvas。绝对路径、`..`、
反斜杠、隐藏目录、symlink、目录、缺失或其他类型均拒绝。URI 使用已验证 Vault ID 和
Vault 相对文件路径，不产生 shell、任意 URL 或写入权限。失败不写 registry/manifest/正文。

## 执行

先运行新增 contract 与 ZotFlow/analysis commit 定向回归，再运行 unit/contract 全集。
测试使用临时合成目录和假 native opener，无真实业务变动。准备结果记录后，按正常 hotfix
流程提交、生成 runtime-only release、安装确定 SHA，再对已登记 test Source 执行一次
reader 查询和 open 笔记。安装态不重跑论文分析、批量迁移或项目实验。

## 可见产物和人工边界

test Vault 新建一份简洁使用说明，提供正文、Canvas 的真实链接及新命令。
打开请求成功不等于画面已显示；用户需要检查 Obsidian 打开正确文件、Canvas 可编辑、
原文链接仍在 ZotFlow 内打开。未获明确确认保持待人工评鉴。
