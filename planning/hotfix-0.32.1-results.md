# 0.32.1 hotfix：安装态单篇展示

## 范围与预期

分支 `codex/hotfix-project-context`，不合并 main。正常 runtime-only 发布、Codex 插件和 pipx CLI 更新；不切换或停止服务。

对象仅 test Vault 的 V-JEPA 2；冻结五分支输入，36 claims、68 条独立内容记录，显式 expanded 容量。安装后使用公开 `analysis batch-run`，预期保留全部内容，成对结构/几何 conformance 通过。结果放入新单篇候选目录；保留旧稿，不迁移正式库，不写 Zotero。暂存产物的逐字副本仅作人工评审，不冒充正式 commit。

准备了源身份、PDF hash、本机 ZotFlow 模式与逐页摘录存在性检查。摘录存在不等于每条论证都被充分支持，未重新宣称完成整篇科学审阅。视觉、点击和编辑效果须明确由用户评鉴。

## 自动验证

- 同步版本后 unit/contract：1420 passed，11 warnings，75.93s。
- 六文件 Ruff、skill frontmatter、diff 空白：通过。
- analyze-paper routing 描述未变；相关代码只读、摘录来源与批次失败清理 safety 条目已审阅；宿主模型执行能力不冒充自动测试通过。

## 待执行

首轮正常发布/安装已完成（source 29d6e82，runtime 75735f0），但公开 `--version` 暴露遗漏的 0.32.0 常量；停止生成真实样张，修正同一 0.32.1 hotfix 并加入独立版本一致性测试。新测试先从 pyproject 读取预期，分别验证 runtime 常量、两个 host manifest 和公开 CLI 返回值，随后必要全量回归；不访问业务数据。通过后重新正常发布安装并核对新 runtime SHA，不把首次安装冒充身份一致通过。

修正后的源码全量回归：1420 passed、1 failed、11 warnings（73.97s）；唯一失败来自新增测试未指定 Click 的正式 `prog_name`（测试输出为 main 而非 scholar-workflow），非版本不一致。只修正测试器调用后，版本/manifest/lifecycle 定向 21 passed（0.18s）；Ruff、diff 空白通过。未重复与该测试写法无关的业务或全量测试。

正常发布与安装身份、单篇 CLI 结果、可见文件与人工评鉴待记录。

回退基线：0.32.0 runtime `be0085be05ba5e16bf19ac3cf8ea1b1992aa67d4`，从同一正常安装入口恢复。人工评鉴之前不合并 main。
