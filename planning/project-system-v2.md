# 科研项目系统 v2 — 改造计划

> 状态：Accepted 0.3，2026-09-22。用户已授权按本文实施 `init-project`、项目身份和实验档案；
> 真实项目迁移、正式备份后端和既有项目的 destructive/untrack 操作仍不在授权范围内。
>
> 本文使用三种标记：**已锁定**表示用户已经确认的上位规则；**推荐**表示本计划给出的实现选择；
> **待决策**表示实现前仍需用户裁定。外部 AI 项目调研只影响源码和配置 profile，不能覆盖已锁定规则。

## 1. 目标与范围

本次改造把当前“固定目录生成器”升级为四个相互分离、可组合的能力：

1. **共同项目契约**：所有科研项目共享的数据、环境、文档、实验、本地保存和指令边界。
2. **源码与配置 profile**：针对不同 AI 项目类型组织 `src/`、`configs/`、训练、推理和测试代码。
3. **实验档案系统**：以 Run / Attempt / Target / Artifact 表达实验配方、执行实例和成果。
4. **安全迁移机制**：对旧骨架只诊断、只增不覆；任何移动、删除、untrack 或语义重分类都逐项目讨论。

本阶段不是集群调度器，也不会让 `init-project` 隐式启动训练。实验执行仍由人显式发起；系统首批只负责
建档、校验、索引、完成回执和成果回收。以后如增加执行器，只能消费已经登记的 Run 和 Target，不能接受
浏览器或自由文本传入的任意命令。

## 2. 决策优先级

发生冲突时按以下顺序处理：

1. 根 `AGENT.md` 及其导入规则；
2. `planning/GOALS.md` 中的目标、不变量与非目标；
3. 已同步进入 GOALS 的、本文标记为“已锁定”的用户共识；
4. 共同项目契约；
5. 源码/config profile；
6. 单个项目经用户确认的覆盖项；
7. 外部仓库的组织习惯。

新的用户共识必须先同步到 `GOALS.md` 与 `CHANGELOG.md`，phase spec 只细化、不得覆盖上位 G/INV/NG。

TRELLIS、Gaussian Splatting、Detectron2、SAM 2、DreamerV3 和 TorchTitan 是 profile 的设计证据，
不是项目根目录规范的权威来源。

## 3. 共同契约与跨系统接口

3.1–3.5 均为已锁定的共同契约。P-D10 已由三系统联合计划裁定为显式独立复制，不建立托管链接。

### 3.1 Git 与源码

- 源码 Git 与本地实验档案是两套系统；实验记录引用完整 commit SHA，不管理 branch 或 worktree。
- 多个 Run 可以基于同一个 commit；Run 的差异可以只来自 `run.sh`、resolved config、数据选择或 seed。
- 新项目的源码演化默认可采用 `develop → main`，但初始化器不在无提交时伪造分支，也不隐式切换分支。
- `configs/` 只保存长期可复用、机器无关、适合进入源码 Git 的 canonical config/recipe。
- 某次 Run 的脚本、override 和最终 resolved config 属于 Run，不进入源码 Git。

### 3.2 数据

数据按数据集聚合，而不是把所有项目数据按处理阶段横向混在一起：

```text
dataset/
└── <dataset-id>/
    ├── source/
    ├── intermediate/
    ├── prepared/
    └── metadata/
```

- `source/`：原始取得或物化的输入。
- `intermediate/`：可重算的中间产物。
- `prepared/`：训练、评估或推理直接消费的形式。
- `metadata/`：来源、许可、版本、split、校验值和生成关系。
- `dataset/` 是每台机器上的本地物化区，不进入源码 Git；执行服务器可以按相同契约物化所需数据，
  但来源、版本和生成关系必须能由本地记录复核。
- 下载、转换、预处理源码固定进入 `src/utils/dataset_toolkit/`。
- 训练期 Dataset/DataLoader 属于项目包，不放进 dataset toolkit。

### 3.3 环境、服务器与 Target

- `env/` 只保存机器无关、可复现的环境定义与构建脚本。
- 个人服务器、API 和已有环境台账继续由全局 `env-records` 持有。
- 项目 Target profile 只描述 Attempt 去哪里、通过何种受控执行器运行。
- 本机也是显式 `local` Target，不能用“字段缺失”表示本地。
- Target 不保存密码、token、private key 或任意 shell command。
- 旧 `env/server/` 的内容必须分类后迁移，不能机械整体搬运。

### 3.4 文档、实验与服务器边界

- 服务器是执行场，不是长期知识真源。
- `docs/` 是本地优先的项目知识库，不在服务器维护第二份正文真源。
- `experiments/` 是本地实验档案，不是试验性源码目录。
- 试验性源码如确有需要使用 `prototypes/`，框架型扩展优先使用 `extensions/`。
- 其他既有项目的 `.gitignore`、tracked 文件和目录迁移必须逐项目讨论，不能批量改写。

### 3.5 与全局科研知识系统的接口（已锁定）

- 项目 `docs/` 是项目内独立工作正文；跨项目知识 Vault 的契约见 `knowledge-system-v2.md`。
- Knowledge→Project 只能由人或 agent 显式选择内容并复制到已注册项目的 `docs/`。复制时移除知识系统
  `sw_*` 身份、sidecar、baseline marker 与托管关系；目标冲突时拒绝，不覆盖、不自动改名。
- Project→Knowledge 由人或 agent 判断内容成熟后显式归档，创建新的 Vault-native 文档和身份。
- 两个副本独立演化；系统不建立实时同步、托管 project-reference 或必须维护的语义 provenance。
- Run/Attempt 报告继续属于实验档案。复制或归档其人类可读内容不会改变 recipe、retention、promotion
  或 backup 状态。

## 4. 目标结构

以下是 v2 的概念结构。`project-layout.json` 是便携项目身份与所选 profile 的正式 manifest：

```text
project/
├── AGENTS.md
├── CLAUDE.md
├── AGENT.md
├── project-layout.json                 # schema v2：稳定 project_id + profile/addon 及版本
├── .agents/
│   └── skills/
├── src/
│   ├── <package>/                      # profile 展开区
│   └── utils/
│       └── dataset_toolkit/
├── configs/                            # canonical components/recipes
├── tools/                              # 薄入口
├── tests/
├── assets/                             # 可发布的 README/项目资产
├── env/                                # 机器无关环境定义
├── dataset/                            # host-local，可在执行服务器物化；不进入源码 Git
│   └── <dataset-id>/
│       ├── source/
│       ├── intermediate/
│       ├── prepared/
│       └── metadata/
├── docs/                               # 本地知识库，不部署到服务器
│   ├── notes/
│   ├── plan/
│   └── report/
└── experiments/                        # 本地实验档案，不进入源码 Git
    ├── profiles/
    │   └── targets/
    ├── <run-id>/
    │   ├── run.yaml
    │   ├── run.sh
    │   ├── inputs/
    │   ├── report.md
    │   ├── notes.md
    │   ├── artifacts.yaml
    │   ├── artifacts/
    │   └── attempts/
    │       └── <attempt-id>/
    └── index.yaml                      # 可选、可重建索引
```

新项目的本地目录不需要用 tracked `.gitkeep` 假装进入源码 Git。现有项目若已跟踪 `docs/` 或
`experiments/`，初始化器只能报告状态和建议 patch，绝不自动执行 `git rm --cached`。

## 5. 源码与配置 Profiles

### 5.1 共同源码契约

所有 profile 共享：

```text
src/<package>/                  # 可导入、可测试的实现
src/utils/dataset_toolkit/      # 离线数据生产工具
configs/                        # canonical config/recipe
tools/                          # 薄 CLI/人工入口
tests/                          # 对应源码职责
```

共同规则：

- 真正实现进入 `src/`；`tools/` 只解析参数和调用实现。
- `configs/` 不保存服务器绝对路径、凭据、输出位置或某次 Run 的 resolved config。
- 配置格式保持中立，可使用 YAML、JSON、TOML 或 Python；不再写死“normally JSON”。
- 可组合片段使用 `configs/components/`，完整可复用配方使用 `configs/recipes/`。
- Recipe 是源码侧可复用配方，不是 Run，也不是实验记录。
- 只有配置必须随安装包发布时，才放 `src/<package>/configs/`；根配置与包内配置不能成为两份真源。
- `benchmarks/` 可保存基准程序和小型 reference fixture，不保存正式实验结果。
- Profile catalog 必须拒绝任何落入 `dataset/`、`experiments/`、`env/` 或 `docs/` 的声明。

### 5.2 主 Profiles

首版使用“一种主 profile + 零到多个正交 addon”，不允许多个主 profile 任意混装。

| Profile | 适用项目 | 核心源码边界 | 配置组织 |
|---|---|---|---|
| `paper-method` | 单论文、单方法 | `method/`、`data/`、`evaluation/` | `train/`、`inference/`、`evaluation/` |
| `multi-stage-3d` | TRELLIS、复杂 3DGS | `datasets/`、`modules/`、`models/`、`representations/`、`renderers/`、`trainers/`、`pipelines/` | `components/{data,model,representation,renderer,trainer}` + `recipes/{train,inference,evaluation}` |
| `research-framework` | Detectron2 式长期框架 | `config/`、`data/`、`structures/`、`layers/`、`modeling/`、`engine/`、`optimization/`、`evaluation/`、`checkpoint/`、`export/` | `common/`、`tasks/`、`datasets/` |
| `foundation-model` | SAM 2 式模型发布 | 推理包 `modeling/`、`predictors/`、`builders/` 与独立 `training/` | `training/`、`inference/`、`evaluation/` |
| `world-model` | DreamerV3 式世界模型/RL | `method/{agent,world_model,policy}` 与 `runtime/{envs,replay,drivers,runners,logging,backends}` | components + train/evaluation recipes |
| `training-platform` | TorchTitan 式训练平台 | `components/`、`models/`、`distributed/`、`observability/`、`protocols/`、`training_engine/` | components + recipes；Python 组合代码可进根 `recipes/` |

Profile 只生成目录和必要包边界，不生成空的 `model.py`、`train.py` 或算法伪实现。

### 5.3 Addons

首版建议只提供少量正交 addon：

| Addon | 新增边界 |
|---|---|
| `native-kernels` | `src/<package>/csrc/`、`tests/hardware/` |
| `interactive-app` | `apps/` |
| `notebooks` | `notebooks/` |
| `benchmarks` | `benchmarks/` |
| `viewer` | `apps/viewer/` |
| `research-extensions` | `extensions/` |

`dataset-toolkit` 不是 addon，因为它已属于共同契约。

### 5.4 Profile Manifest

**推荐**在项目根创建可见、可读、进入源码 Git 的 `project-layout.json`：

```json
{
  "schema_version": 1,
  "language": "python",
  "package": "my_project",
  "source_profile": {"id": "multi-stage-3d", "version": 1},
  "addons": [{"id": "native-kernels", "version": 1}]
}
```

- 它只记录源码布局选择，不记录 dataset、Run、Target、服务器或凭据。
- Profile/addon 版本固定，插件升级不得静默向既有项目添加目录。
- 无 manifest、无 profile 参数时只创建共同基座，不猜项目类型。
- 现有源码可产生候选 profile 诊断，但只有用户确认后才能写 manifest。
- 请求与既有 manifest 不一致时，必须在任何写入前停止并生成迁移计划。

插件内部由一个版本化、机器可读的 profile catalog 同时驱动初始化器、职责说明和测试，避免 Python、
Markdown 与测试各维护一份目录清单。

## 6. 实验档案模型

### 6.1 Run

Run 是一次科学实验设计和可复现配方。建议必要字段为：

- `schema_version`、`run_id`、`created_at`、`record_state`；
- `source.commit`：完整 commit SHA；
- `entrypoint.path` 与内容 SHA-256；
- canonical config 来源、快照、resolved config 与 SHA-256；
- dataset ID、version、split、manifest 与哈希；
- seed；
- 机器无关环境定义与哈希；
- `recipe_hash`。

`recipe_hash` 只纳入：

```text
commit SHA
+ run.sh hash
+ resolved config hash
+ dataset identity/version/split/manifest hash
+ seed
+ machine-independent environment hash
```

Target、GPU、hostname、绝对路径、执行时间、状态、报告正文和人工说明不进入 recipe hash。

第一条正式 Attempt 建立后，Run recipe 冻结。报告、notes 和 artifact manifest 可以继续增长。修改
commit、脚本、resolved config、数据选择、seed 或机器无关环境定义时，应创建新 Run。

### 6.2 Attempt

Attempt 是 Run 的一次实际执行、失败重试或迁移执行。建议必要字段为：

- `attempt_id`、`run_id`；
- Target profile ID 及执行时的 profile hash；
- status、开始/结束时间、exit code；
- 实际工作目录、输出位置和日志位置；
- 实测 hostname、OS、GPU、driver、CUDA、Python 和环境；
- 实际 commit/recipe hash 回读结果；
- output inventory 路径与哈希。

只换服务器、Target、GPU、运行时间或重试失败执行，均是同一个 Run 的新 Attempt。

### 6.3 Target Profile

推荐位置：

```text
experiments/profiles/targets/<target-id>.yaml
```

推荐字段：

```yaml
schema_version: 1
target_id: gpu-a
kind: ssh                       # local | ssh
server_alias: gpu-a             # 对应 env-records / SSH alias
project_root: /path/to/project
output_root: /path/to/results
executor:
  kind: shell                   # shell | slurm
environment_bindings:
  training: env-name
```

执行器只能使用 schema 定义的字段；`password`、`token`、`private_key`、任意 `command` 和未知字段应
被拒绝。主机、用户、端口和凭据继续由 SSH 配置或 `env-records` 管理。

### 6.4 Artifact Manifest

Artifact manifest 同时记录“是什么”和“怎样保存”：

- `role`：report、metrics、parameters、point-cloud、image、video、checkpoint、log、intermediate 等；
- `retention`：`local-required`、`local-selected`、`manifest-only`；
- `source_attempt_id`、相对路径、size、SHA-256、远程来源；
- 晋升到本地的时间和校验回执。

服务器结果复制回项目本地称为 **artifact promotion**。本机只有一份文件不等于已经备份；只有第二份
独立副本完成校验后，系统才能标记 backup verified。

### 6.5 实验管理能力边界

持续的实验生命周期不塞进 `init-project`。本批采用宿主中立的确定性 CLI，并由现有
`init-project` 文档说明实验档案入口；不新增 standalone `manage-experiment` skill：

```text
experiment new-run
experiment new-attempt
experiment finalize-attempt
experiment validate
experiment promote
experiment index
experiment migrate-plan
```

首批命令只建档、校验、索引和回收成果，不启动训练、不生成任意远程 shell。Skill 只保留路径、schema、
精确命令和安全边界，不重复教授模型如何分析实验。

## 7. 本地保存与备份分层

| 层级 | 内容 | 默认处理 |
|---|---|---|
| A：本地必留 | 源码/Git 历史、Run/Attempt 元数据、脚本、resolved config、报告、指标、参数、环境摘要 | 本地保留；纳入后续校验备份 |
| B：选择性晋升 | 最终点云、代表性渲染图/视频、关键 checkpoint、必要中间物 | 人工选择后 promotion，记录哈希和来源 |
| C：仅清单 | 可重算但巨大的中间文件、非关键 checkpoint、完整远程输出 | 本地只留 manifest、生成 Run/Attempt 和远程位置 |
| D：临时 | cache、重复日志、下载缓存 | 可淘汰，不作为研究成果 |

公开、可重新下载的数据可不复制，但必须保留来源、版本、许可、checksum 和准备流程。备份介质、周期、
保留代数和异地副本尚未决定，因此首批实现不能声称“本地保存即完成备份”。

## 8. `init-project` v2 设计

### 8.1 声明式布局

当前脚本中的单一 `DIRECTORIES` 常量应拆为：

1. 共同的 tracked source layout；
2. 共同的 local-only layout；
3. 一个主 source profile；
4. 零到多个 addon；
5. 版本化 project-layout manifest。

Profile catalog 的每个路径同时带职责说明，以同一数据源生成初始 `AGENTS.md` 职责表。任何重复路径只有
职责完全一致时才可合并；职责冲突必须在全量 preflight 后停止。

### 8.2 CLI 形态

保持现有 `plan TARGET` / `apply TARGET` 兼容，并增加显式参数：

```bash
python3 skills/init-project/scripts/init_project.py plan TARGET \
  --source-profile multi-stage-3d \
  --package project_name \
  --addon native-kernels

python3 skills/init-project/scripts/init_project.py apply TARGET \
  --source-profile multi-stage-3d \
  --package project_name \
  --addon native-kernels
```

同时规划只读的 `profiles` 和 `migrate-plan` 模式。初始化器不提供 `--auto-profile`。

### 8.3 保留的安全性质

- `plan` 零写入；`apply` 只增不覆。
- 全部目录、文件、symlink 和 manifest 冲突在第一次写入前完成检查。
- 不删除、不移动、不重命名、不 stage、不 commit、不 push。
- 不生成 `.claude/`、`.codex/`、自定义 agent 或 hook。
- 已有 `AGENTS.md` 只报告建议 patch，不自动改写。
- 已有 `.gitignore` 只报告本地边界缺口，取得用户逐项目确认后才修改。
- Profile 改变走显式 migration plan，不是普通 `apply`。

## 9. 旧结构迁移

| 旧结构 | v2 目标 | 自动化边界 |
|---|---|---|
| `dataset/raw`、`dataset/metadata` | 分配到各 `dataset/<dataset-id>/...` | 无法可靠判断 dataset，默认只诊断 |
| 顶层 `dataset_toolkits/` | `src/utils/dataset_toolkit/` | 可提出候选映射，不自动移动 |
| `env/server/` | env-records / target profile / `env/` / Attempt | 必须逐项分类 |
| `experiments/<id>/` | 原地补 Run + `attempts/` | 不增加 `runs/` 层，不移动旧 output/log |
| tracked `docs/`、`experiments/` | local-only | 只报告，不自动 untrack |

旧实验迁移流程：

1. 扫描并输出只读 migration plan；
2. 只把单一报告、单一脚本、明显 config/output/log 作为候选；
3. 多脚本、多 config、未知 commit 或语义不明时标记 unresolved，零写入；
4. 用户补齐后，只新增 `run.yaml` 与 `attempts/legacy-01/attempt.yaml`；
5. 旧文件原地保留，通过相对路径引用；
6. 资料不足时使用 `record_state: incomplete_legacy`；
7. 重跑逐字节不改变已有内容。

外部的旧 `project-document settings` 模板只有在本计划批准并实现后才更新；其他真实项目逐个讨论。

## 10. 实施阶段与退出条件

### Phase A — 决策冻结与契约守护

交付：GOALS/HANDOFF/BACKLOG 对齐；Run、Attempt、Target、Artifact、Project Layout schema 草案；eval
用例先行。

退出条件：所有“待决策”均有明确结论；schema 可表达两个 Run 共用 commit、一个 Run 多 Attempt。

### Phase B — `init-project` v2 共同基座

交付：声明式 base layout、local-only 边界、project manifest、legacy diagnostics 和全量 preflight。

退出条件：保留现有幂等/不覆盖测试；新项目不再生成旧 dataset/toolkit/env-server 结构；旧项目零破坏。

### Phase C — 源码与配置 Profiles

交付：六个主 profile、首批 addons、profile catalog/schema、动态职责表和双语文档。

退出条件：每个 profile 的 plan 零写入、apply 幂等；profile 无法声明四类外层路径；既有源码逐字节保留。

### Phase D — 实验档案能力

交付：experiment CLI、薄 skill、Run/Attempt/Target 校验、冻结规则、可重建索引和 legacy migration plan。

退出条件：同一 recipe 可在 local/SSH 形成一 Run 两 Attempt；recipe 变化不能追加到冻结 Run。

### Phase E — Artifact Promotion

交付：显式选择、原子复制、SHA-256 校验、防覆盖、manifest-only 支持和 promotion receipt。

退出条件：中断不留半成品；同 hash 重跑幂等；不同内容拒绝覆盖；路径逃逸和 symlink fail closed。

### Phase F — 实盘迁移与发布

交付：先用临时项目验证，再选一个真实项目由用户确认后迁移；双宿主文档、manifest、CHANGELOG、版本和
release snapshot 对齐。

退出条件：完整 unit/contract/eval 通过；release 含新增 catalog/schema；旧模板和真实项目没有被静默改写。

## 11. 测试矩阵

至少增加以下守护：

- 六个 source profile catalog 均通过 schema；profile 路径不能越过 source/config allowlist。
- 每个 profile 与 addon 的 plan 零写入、apply 幂等、合并顺序稳定。
- manifest 与 CLI 请求不一致、未知 profile、非法 package、职责冲突、symlink 均在写前拒绝。
- 新项目不生成 `.claude/`、`.codex/`、agent/hook，不 stage/commit/push。
- 两个 Run 可共用 commit；修改脚本/config/dataset split/seed/环境定义产生新 recipe hash。
- 只换 Target/GPU/服务器/重试不改变 recipe hash，只新增 Attempt。
- Attempt 引用不存在的 Run/Target 时拒绝；Target 含 secret、command 或未知字段时拒绝。
- Artifact promotion 拒绝绝对路径、`..`、symlink 和同名不同内容；原子复制可恢复。
- Legacy 多脚本/未知 commit 情况只报告 unresolved；重跑迁移不改变旧字节。
- 新项目创建实验记录后，源码 Git 不出现 `docs/`、`experiments/` 和 `dataset/` 内容。
- 已跟踪的旧目录只报告，不自动 untrack。
- release snapshot 包含所有新增 schema、profile catalog、skill 和 CLI 资源。

## 12. 预计改动面

规划中的主要新增文件：

```text
contracts/project-layout.schema.json
contracts/experiment-run.schema.json
contracts/experiment-attempt.schema.json
contracts/experiment-target.schema.json
contracts/experiment-artifact.schema.json
skills/init-project/references/source-profiles.json
skills/init-project/references/source-layout.md
skills/<experiment-skill>/...
tests/contract/test_init_project_profiles.py
tests/contract/test_experiment_contracts.py
```

主要修改面：

```text
skills/init-project/
src/scholar_workflow/cli.py
src/scholar_workflow/<experiment modules>
tests/unit/test_init_project.py
evals/{routing,safety,outcomes}.json
AGENT.md
planning/{GOALS,HANDOFF,BACKLOG}.md
README.md
README.zh-CN.md
CHANGELOG.md
.claude-plugin/plugin.json
.codex-plugin/plugin.json
```

`scripts/make-release.sh` 当前已整体纳入 `skills/` 和 `contracts/`，实现时仍须通过 release 内容测试确认。

## 13. 已冻结决策与外部决策门

| ID | 决策项 | 状态 | 已冻结结果 |
|---|---|---|---|
| D1 | 实验工作流入口 | 已冻结 | 本批不新增 standalone skill；确定性能力进入 `scholar-workflow experiment`，初始化和项目契约继续由 `init-project` skill 说明 |
| D2 | Run ID | 已冻结 | `YYYYMMDD-HHMM-<slug>`；冲突时拒绝并要求显式新 ID |
| D3 | 实验文档格式 | 已冻结 | YAML 供人读，JSON Schema 校验解析后的对象 |
| D4 | dirty worktree | 已冻结 | 正式 Run 要求 clean；显式 draft 可保存 patch，不能冒充 frozen Run |
| D5 | project manifest | 已冻结 | `project-layout.json`，`schema_version: 2`；`project_id` 是初始化时生成一次的规范小写 UUID，复制/重跑保持不变且不含主机路径 |
| D6 | profile 扩展目录 | 已冻结 | `extensions/`，避免与“项目”概念混淆 |
| D7 | 备份介质与频率 | 外部决策门 | 未确定前只实现 promotion 和 `backup_pending`，不得声明 verified |
| D8 | 大产物默认阈值 | 已冻结 | 类型默认 + 人工覆盖，首版不设通用大小阈值 |
| D9 | 首个真实迁移项目 | 外部决策门 | 只完成临时 fixture；真实项目由用户以后逐项选择 |
| P-D10 | 项目 `docs/` 与全局知识 Vault 的衔接 | 已冻结 | 显式独立复制；目标获得新身份并独立演化，无实时同步、托管链接或强制 provenance |

## 14. 完成定义

系统改造只有同时满足以下条件才算完成：

1. 新项目共同契约与已锁定共识一致；
2. 源码 profile 不污染数据、实验、环境或文档边界；
3. Run/Attempt/Target 的身份和可变性由 schema 与测试守护；
4. 本地 promotion 与真正 backup 在状态上明确区分；
5. 旧项目无静默移动、删除、覆盖、untrack 或 profile 猜测；
6. 每个真实项目的配置和迁移都经过用户单独确认；
7. Claude Code 与 Codex 安装得到同一套能力与契约。
8. 项目 `docs/` 与全局知识 Vault 不形成静默双真源；跨域内容只经显式复制，副本拥有独立身份，
   不依赖持续来源关系才能读写或演化。
