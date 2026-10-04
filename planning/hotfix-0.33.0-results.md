# 0.33.0：项目／实验复现能力结果

日期：2026-10-05。独立 hotfix，main 未合并；整阶段未完成。

## 开发验证

- 独立输入与范围：`project-reproducibility-test-plan.md`。
- 首轮定向 34 passed（4.02s），发现系统 Python 缺 pydantic，三个剩余 lint 项未通过。
- 最小修正：通过已安装 CLI console entry 选择产品 Python，只给初始化器用；helper 本身标准库。
  unsupported launcher 在创建目标前拒绝，未自动装依赖。代码计算在 src，tools 只做薄入口。
- 修正后定向 37 passed（4.58s），包括两个 launcher/系统 Python 边界；全量 1441 passed、
  11 个现有依赖/多线程 fork 警告，77.10s。
- 七个 Python 文件 Ruff、init-project skill validator、diff 空白检查通过。
- 触发 description 不改；原 init-project routing 不变。新增 safety 用公开脚本负例守护，
  reproduction outcome 继续 pending，自动 schema 不能冒称人类评鉴通过。
- 新模板未找到个人路径、真实 Zotero library/attachment ID、固定 23128 或密钥字段。

## 交付边界

可移植模板、新脚本、按需 reference 和双语说明已实现。准备不提交/执行；实际 replay 另行进行。
安装、单对象 canary、source/runtime SHA、真实 CLI/cache 身份及人类展示结果随后补充。
回退：0.32.3 / runtime `c0fa2000a7b8d56a841bc753be12d5f3898e7114`。

新版本不重新生成论文分析、迁移正式 Vault、扫描业务项目、改变服务或构建内置 Codex 控制面。
人类便利性、完整模范 Source/Field、论文新候选科学支持与原生工具评鉴仍未全项通过。

## 正常发布／安装和真实 canary

- Source `150aa75fc57ad0789ef29a8c771e2b4cf724f165` 已推 hotfix；runtime-only
  `3f00999797beab81c032775038917ff72ae5c480` 由 make-release 生成并推 release。
  runtime 根无 planning/dev-guide/tests/evals/AGENT，未发现本机私人路径或样例真实 Zotero ID。
- pipx 固定上述 runtime SHA 正常安装；direct_url commit_id 与 requested_revision 均一致。
  包元数据、模块常量、public --version、两个 plugin manifests 与 Codex cache 均 0.33.0。
- Codex 正常 marketplace upgrade/add，安装缓存 `scholar-workflow/0.33.0`，未手改缓存。
- 用普通系统 Python 运行安装缓存的 example_project.py plan/apply；创建新独立
  `scholar-exemplars/model-project-0330/`，product Python 由 console entry 正确选择。
  只将此前明确选定的 V-JEPA2 论文/分析两条引用加入清单，公开 validate-context 通过6项。
- 另行提交该新示例源码（仅本地、不push）`2bbfc47c8d426f8dafed88ccefb594f9e5713362`。
  安装 CLI 实际执行并记录：wrong-cwd failed/2、correct-cwd succeeded/0、replay succeeded/0。
- 从同源码新克隆 `model-project-0330-replay/`，安装器补齐5个本地优先目录后重新生成数据和实验。
  两边 project_id `e0dd6b54-e158-4392-bdfd-ac4d3200b120`；recipe hash
  `f200b752a1f60dbc1d93637f0dca1455feb089e80e8ebba510889374e38a62a4` 相同。
- 实际 count=4、sum=10、mean=2.5；成果 SHA256 两边均
  `9e0bb1068a514350b5415cd8ec51fcd742baaa1aa1c4511f1351e1df6c69f979`。
  每边 public validate 返回 runs=1、attempts=3、targets=1、artifacts=1；backup=not-verified。
- test Vault 可见说明在 `Scholar Workflow 实验/项目与实验-0.33.0/本轮成果.md`。
  示例中的真实用户资料引用未进入产品模板；本轮未改写旧论文 pair。整个G17及人类评鉴仍pending。

## 旧论文产物的只读核对

- Markdown 字节 SHA256 仍为 `f2f1c0df1eafc915ab2d2433bc70bab501d9a0c2a41e571ba94c4978ac2c7559`。
- Canvas 当前字节 SHA256 为 `ae474839336040886b8b92e223d440c206627365eb24264de1046fcdd2fff4f1`，
  不再与初次生成时的字节校验值相同。差异是序列化和允许的
  `metadata={"version":"1.0-1.0","frontmatter":{}}`，符合编辑器保存表现；不能据此断定写入者。
- 将原 `.replay-stage` 生成稿与现稿各自用 `jq -S -c 'del(.metadata)'` 规范化，二者 SHA256 均为
  `04b6d7cf8e8c932cbfab89ab78320e89e04de0a2d4b10e5b64310fb81cbf7eab`。
  节点、文字、边、坐标、样式及数组顺序语义一致；当前编辑器 metadata 原样保留，未覆盖文件。
- 原生成回执是历史证据，不改成当前校验值；本节单独记录本轮观察。
