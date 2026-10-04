# 模范项目与实验：安装态实际结果

2026-10-04；Scholar Workflow 0.32.3；单示例，无整库业务操作。

## 本轮交付

新建独立 `scholar-exemplars/model-project-0323/` 与从其 Git 源码重建的 `model-project-0323-replay/`。
不放入 test Vault 的现有 Git；只在 test 新增 `Scholar Workflow 实验/项目与实验-0.32.3/本轮成果.md`。

安装插件公开初始化脚本 plan/apply：首次 create=27、conflict=0；rerun create=0、keep=27、diagnostic=0。
新克隆 apply 仅补齐 5 个本地优先目录，不改变项目 ID。资料清单声明 6 项，通过公开 validate-context。
项目源码仅在新建示例 Git 本地提交 `eccdfafe6fa2d7f4f2ef499ff795dbfb2db9746e`，没有 push。
执行后原示例增加纯说明提交 `22808e9`，补明确新克隆的安装器 apply 步骤；既有 Run 的源码
仍绑定上述 eccdfaf，不冒称后续说明提交已重新执行。说明更新后公开 validate 仍通过。
初始化规则占位符未获批准，保持 unresolved，不冒称已完善业务规范。

## 两个目录各自实际执行

| 对象 | 结果 |
|---|---|
| wrong-cwd | 真实失败，退出码2；相对脚本无法定位，日志保留 |
| correct-cwd | 成功，退出码0；count=4、sum=10、mean=2.5 |
| replay | 成功，退出码0；与 correct-cwd 字节相同 |
| promote | 一份 local-required 指标成果，backup=not-verified |
| validate | runs=1、attempts=3、targets=1、artifacts=1；命令退出0 |
| index | 安装版公开命令成功 |

跨目录 project_id 同为 `bb140f9f-ce53-47bf-a385-c7ef050a118f`；源码 commit、配方 hash、fixture 不变。
配方 hash `9b8950c20b53d31e69ec9de825f8a7b134138be8e70a213a45a59c8e44266748`。
成果 SHA256 均为 `9e0bb1068a514350b5415cd8ec51fcd742baaa1aa1c4511f1351e1df6c69f979`。
原目录的旧实验没有被复制到新目录；新目录各自创建 Run、执行并记录三个 Attempt。

每个 Run 有公开 CLI 返回记录、actual.json、stdout/stderr、acceptance.json 与人类 report.md。
复现入口仅调用安装版公开 CLI，不导入 Scholar 私有实现。小型算术源码是新增示例，不是论文仓库。
Obsidian 曾在文件 watcher 入库前返回 not-found；索引出现后再次 open 成功，active file 精确匹配
`Scholar Workflow 实验/项目与实验-0.32.3/本轮成果.md`。这只证明应用载入该文件，不代替人类视觉评鉴。

## 未通过／未做

- 本轮成果及 V-JEPA2 0.32.3 Canvas 的人类可读性、审美、点击便利性仍待人工评鉴。
- 外部对象在 overview 中诚实标 unverified，没有把可打印 URI 当实际应用可用性。
- 尚未把这套项目/实验复现包沉淀为新安装版 skill reference；本轮只是现有安装能力的可见组合。
- 未注册正式 Source/Field，未做正式迁移、全篇科学支持审议、真实训练、远端执行或备份恢复演练。
- 没有更改正式 Vault、Zotero、原论文 pair、旧业务项目、Hub 服务或 scholar-workflow main。

下一切片是基于这个真实样例沉淀可移植复现 reference 与必要入口；不得重跑整库或重新开发同一有效样例。
