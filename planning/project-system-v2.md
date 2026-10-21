# 科研项目系统 v2 — 改造计划

> 状态：Accepted 0.6，2026-10-16。用户已确认完整本地研究总项目与远端执行子项目的管理方式（§3.6、§4、§15）；
> 2026-10-18交付更新：双角色/登记/本地接收与读取/更新恢复/代码材料留存已随0.46.0正式发布，
> 当前正常安装0.46.1为说明修正版；一个test合成项目自动检查完成，原生显示与人工待评。
> 具体安装与有限验收事实唯一见0.46.0-release.md；不代表远端部署/采集或授权真实迁移。
> 此前本地保留Primary开发clone的设想被替代。
> 本规格继续持有 `init-project`、项目身份和实验档案，
> 新增资料关联与职责边界由 [`project-centered-refactor.md`](project-centered-refactor.md) 细化。
> `project-context.json` 独立于布局 manifest；旧 Hub 是兼容实现，不再是项目整合的前置条件。
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

3.1–3.5 均为已锁定的共同契约。P-D10 于 2026-10-01 修订为允许显式导航/上下文引用；
正文复制仍独立，引用不形成同步或跨域写权限。

### 3.1 Git 与源码

- 源码 Git 与本地实验档案是两套系统；实验记录引用完整 commit SHA，不管理 branch 或 worktree。
- 在本次确认的总项目/子项目模式中，所有子项目的源码Git工作区均位于远端。本地总项目有独立的
  资料Git，跟踪管理文档和轻量档案但不推送；本地代码恢复副本不是开发clone，也不被当作源码真源。
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
- 本地 `experiments/` 聚合各子项目的执行档案与回传成果；远端子项目也必须登记自身实验。
  这是显式的实验事实回传，不是知识正文同步；远端执行记录与本地人工分析分开，不互相覆盖。
- `experiments/` 不存试验性源码，数据集和大型执行产物也不默认回传本地。
- 试验性源码如确有需要使用 `prototypes/`，框架型扩展优先使用 `extensions/`。
- 其他既有项目的 `.gitignore`、tracked 文件和目录迁移必须逐项目讨论，不能批量改写。

### 3.5 与全局科研知识系统的接口（已锁定）

- 项目 `docs/` 是项目内独立工作正文；跨项目知识 Vault 的契约见 `knowledge-system-v2.md`。
- 项目用独立 `project-context.json` 关联代码、论文、分析、笔记、实验和结果；清单归 Project，
  外部正文、附件及其 owner 仍归原系统。引用由明确选择产生，不根据同名、目录或扫描自动建立。
- 项目内记录使用安全相对路径，外部记录使用明确 provider/resource 身份与可选稳定 Zotero/Obsidian
  URI；关联不是来源已经可达或内容已核验的证明。删除清单项只删除关联，不删除被引用对象。
- Knowledge→Project 正文交接仍由人或 agent 显式选择内容并复制到项目 `docs/`。复制时移除知识系统
  `sw_*` 身份、sidecar、baseline marker 与托管关系；目标冲突时拒绝，不覆盖、不自动改名。
- Project→Knowledge 由人或 agent 判断内容成熟后显式归档，创建新的 Vault-native 文档和身份。
- 两个副本独立演化；引用和复制均不建立实时同步、级联删除或必须维护的语义 provenance。
- Run/Attempt 报告继续属于实验档案。复制或归档其人类可读内容不会改变 recipe、retention、promotion
  或 backup 状态。

项目中心接口不扩展 `project-layout.json`，不引入运行服务：

- `project-layout.json` schema 2 仍只持有 `project_id`、源码 profile/addon 及版本；
  `project-context.json` schema 1 必须绑定相同 `project_id`，不保存主机绝对路径、秘密或执行配置。
- Project 的只读 overview 从显式清单生成 Markdown；stdout 输出不强制创建首页、登记项目或写回来源。
  外部引用在本批显示 unverified，不以零联网读取宣称已解析 Zotero/Obsidian。
- cmux 和外部 Codex 保持原生使用方式；窗口位置不授予文件权限，不成为清单读取的先决条件。
- 尚未移除的 Hub 项目文件 API 仍只接受 `project_id + docs 相对路径`，守护 no-overwrite、CAS、
  symlink、Git 风险提示与可恢复 trash；本次没有停止服务或放松兼容路径。

### 3.6 本地总项目与远端执行子项目（2026-10-16 已锁定，待实现）

本节适用于插件管理的科研项目，不授权迁移Scholar Workflow插件自身的开发仓库。
运行期skill的共同结果契约唯一持于 `references/project-management.md`，由现有init-project、
organize-project与review-experiments按职责加载；本文继续持有设计决定与实施增量，不作为运行期依赖。

**本地是完整研究管理项目，不是备份目录或实验结果收件箱。** 保留稳定项目身份、资料关联、内部
PROJECT、唯一详细计划、项目知识与轻量文献梳理、agent规则/技能、全子项目实验档案、分析比较、
成果及恢复状态。PROJECT仍在VS Code阅读，先展示现状、计划与结果；README仍是对外说明文档，
不会因为总项目不发布而与PROJECT合并或自动删除。论文单元、Canvas、证据与知识格式不变。

**远端子项目是开发和执行单元。** 每个子项目有稳定身份、总项目归属、自己的Git、代码、
canonical configs、env、tools、tests、按dataset组织的数据及实验登记。不得因裁剪总体管理层，
删掉子项目所需的执行规则、项目技能或实验档案。角色名采用 `primary`（Primary Subproject）；
baseline/探索/验证等用途按实际情况说明，不强制固定一套子项目类别或数量。

Git与发布边界：

- 所有人工及agent代码修改都在远端完成，本地不保留任何子项目的日常开发clone。
- 总项目的本地Git管理其研究资料与轻量实验档案，不推送；各远端子项目独立Git。
- 只有primary可以向项目自有GitHub仓库推送开发历史；其他子项目不上传自己的修改，但可以
  读取/clone/fetch其原作者上游。GitHub可见性与正式发布仍分别决定，不自动创建仓库或推送。
- 同一子项目可在多服务器执行，但明确主要开发位置；并行修改用独立分支/工作目录，执行使用固定
  commit的独立目录，运行中不更新。主分支整合不自动force-push，不以最后写入覆盖冲突。
- 本地最简代码恢复材料应覆盖需保留的实验引用提交及必要非秘密恢复信息，不是第二套开发真源；
  未提交/未跟踪原创内容不能假称已经包含在Git包中。备份状态仍服从§7与WI-041。

实验登记与归档边界：

- 远端各子项目登记全部实验，包括失败和中断；本地按 `experiments/<subproject>/<run>/attempts/<attempt>/`
  归档，分析、比较和综合在本地进行。Run/Attempt身份及其科学语义不变，目标主机不进入recipe身份。
- 关联使用总项目/子项目的稳定身份，不以可改的目录名、服务器路径或仓库显示名充当身份。子项目内
  Run引用须限定子项目范围，同一Run在不同位置的执行使用不同Attempt，避免回传相互覆盖。
- 回传包含代码commit、入口与实际配置/环境快照、数据版本、状态、指标、必要成果及清单；不因
  “只有最简源码备份”省掉解释比较结果所需的配方证据，不默认复制整套数据或大型checkpoint。
- 接收按明确身份与内容校验：同版本同内容幂等，冲突或来源改变时拒绝覆盖；后续执行状态更新须
  校验已知基线并留下回执，不能把仍在增长的文件伪装成不可变快照。本地分析不写回远端执行事实。
- 比较条件与结果同处，明确baseline/variant的共同条件、差异和未核实因素；沿用既有实验呈现契约。

agent与原生工具边界：

- 本地agent可通过SSH操作远端，也可在远端运行CLI agent；不强制搬迁所有agent或建设新的控制面。
  人工使用VS Code Remote-SSH，cmux仅承载原生窗口/终端，不授予文件或服务器权限。
- 远端规则/skills必须实际可达；本地全局规则、插件、登录和会话不能视为已经自动继承。按任务提供
  必要目标/约束/资料，不复制整个本地知识库或凭证；服务器凭据继续留在既有私有台账/SSH机制中。
- 资料关联需增补受控远端代码定位及原生打开约定；当前schema 1只支持本地project-file及
  Zotero/Obsidian外部对象，不能把任意SSH URL塞进现有URI冒充支持。资料引用不是执行授权。

## 4. 目标结构

以下为2026-10-16确认的职责结构，尚非当前初始化器的输出。具体子项目清单及恢复目录的存储形式在
WI-055契约切片中确定，不因示意强制新增多个管理文件。`project-layout.json`继续持有便携身份；
总项目/子项目关联和主机定位须各司其职，不能把个人主机路径或凭据塞入便携manifest。

```text
local-research-project/
├── .git/                              # 研究资料的本地Git，不推送
├── PROJECT.md                         # 内部现状、计划、结果与直接导航
├── README.md                          # 对外说明，不发布内部PROJECT
├── SCHEDULE.md                        # 可选；与既有计划择一，不建第二份详细计划
├── AGENTS.md
├── CLAUDE.md
├── AGENT.md
├── project-layout.json                 # 稳定身份；当前schema 2，新双角色表达待实现
├── project-context.json                # 资料关联；当前schema 1，远端代码定位待实现
├── .agents/skills/                     # 总项目规则与技能，不是自动会话记忆管理器
├── docs/
│   ├── notes/                         # 项目知识、设计判断、轻量文献分工
│   ├── plan/                          # 规划材料；任务计划只有一个权威
│   └── report/                        # 本地分析、跨实验比较与综合成果
├── assets/                            # 项目说明所需展示素材
├── experiments/
│   ├── profiles/targets/              # 无凭证的执行位置与能力
│   ├── <subproject-segment>/          # 稳定身份映射，不以目录名充当身份
│   │   └── <run-id>/
│   │       ├── run.yaml               # 远端配方及快照的受控回传
│   │       ├── run.sh                 # 实际入口快照，不是本地训练启动器
│   │       ├── inputs/
│   │       ├── report.md              # 本地分析，与执行事实分开
│   │       ├── notes.md
│   │       ├── artifacts.yaml
│   │       ├── artifacts/
│   │       └── attempts/<attempt-id>/
│   └── index.yaml                     # 可重建，跨子项目引用须限定身份
└── backups/code/                      # 示意最简恢复副本；非开发clone，不进入资料Git

remote-execution-subproject/
├── .git/                              # 每子项目独立；只有primary可连接GitHub
├── AGENTS.md / CLAUDE.md / AGENT.md     # 适用的执行规则与引用入口
├── .agents/skills/                     # 该子项目需要的实际技能
├── <identity-and-parent-declaration>   # 概念占位，具体schema/文件名尚未确定
├── src/
│   ├── <package>/                      # profile 展开区
│   └── utils/
│       └── dataset_toolkit/
├── configs/                            # canonical components/recipes
├── tools/                              # 薄入口
├── tests/
├── env/                                # 机器无关环境定义
├── dataset/                            # 执行主机物化，不进入源码Git或默认回传
│   └── <dataset-id>/
│       ├── source/
│       ├── intermediate/
│       ├── prepared/
│       └── metadata/
└── experiments/                        # 子项目自己的执行事实，不进入源码Git
    ├── profiles/targets/               # 所需执行位置声明，不含凭据
    ├── <run-id>/
    │   ├── run.yaml
    │   ├── run.sh
    │   ├── inputs/
    │   ├── artifacts.yaml
    │   ├── artifacts/
    │   └── attempts/
    │       └── <attempt-id>/
    └── index.yaml                      # 子项目可重建索引
```

总项目资料Git可跟踪docs与轻量实验记录；远端源码Git仍排除数据/大产物及执行档案。不能把现有
“忽略整个docs/experiments”的源码策略机械用于本地总项目。当前扁平Run目录保持旧版兼容，
不会静默搬到新分层；已跟踪内容的untrack、目录移动和ignore变更仍需逐项目确认。

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
  "schema_version": 2,
  "project_id": "11111111-1111-4111-8111-111111111111",
  "language": "python",
  "package": "my_project",
  "source_profile": {"id": "multi-stage-3d", "version": 1},
  "addons": [{"id": "native-kernels", "version": 1}]
}
```

- 它只记录稳定项目身份与源码布局选择，不记录资料引用、dataset、Run、Target、服务器或凭据；
  示例UUID仅为说明，初始化器必须为新项目生成一次独立身份。
- Profile/addon 版本固定，插件升级不得静默向既有项目添加目录。
- 无 manifest、无 profile 参数时只创建共同基座，不猜项目类型。
- 现有源码可产生候选 profile 诊断，但只有用户确认后才能写 manifest。
- 请求与既有 manifest 不一致时，必须在任何写入前停止并生成迁移计划。

插件内部由一个版本化、机器可读的 profile catalog 同时驱动初始化器、职责说明和测试，避免 Python、
Markdown 与测试各维护一份目录清单。

## 6. 实验档案模型

以下Run/Attempt/Target/Artifact语义保留。远端子项目创建、冻结执行配方，本地接收并按子项目
归档；接收时必须保留子项目源码commit，不能用本地总项目的资料Git HEAD重新生成配方。
当前CLI没有该远端接收模式，仍是 `experiments/<run-id>`；新分层与聚合由WI-055另行实现。

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
| A：本地必留 | 最简代码恢复材料（含需保留的实验引用提交）、Run/Attempt 元数据、脚本、resolved config、报告、指标、参数、环境摘要 | 本地保留；不建立日常源码clone，纳入后续校验备份 |
| B：选择性晋升 | 最终点云、代表性渲染图/视频、关键 checkpoint、必要中间物 | 人工选择后 promotion，记录哈希和来源 |
| C：仅清单 | 可重算但巨大的中间文件、非关键 checkpoint、完整远程输出 | 本地只留 manifest、生成 Run/Attempt 和远程位置 |
| D：临时 | cache、重复日志、下载缓存 | 可淘汰，不作为研究成果 |

公开、可重新下载的数据可不复制，但必须保留来源、版本、许可、checksum 和准备流程。备份介质、周期、
保留代数和异地副本尚未决定，因此首批实现不能声称“本地保存即完成备份”。
最简Git恢复包不包含全部工作区状态；未提交/未跟踪原创内容要单独处理。复制成功或Git包校验不等于
独立介质恢复演练通过，不能绕过当前runtime/schema对verified状态的拒绝。

## 8. `init-project` v2 设计

§8–§12保留原v2实施基线与兼容要求；新双角色初始化及分层回传的增量见§15，不冒称旧接口已经支持。

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
| `experiments/<id>/` | 旧版原地兼容；新总项目按子项目归档 | 不增加 `runs/` 层，不自动搬迁旧 output/log；新分层先做显式迁移预览 |
| tracked `docs/`、`experiments/` | 本地总项目可跟踪管理记录；远端源码Git仍排除执行档案 | 只报告角色与差异，不自动 untrack或批量改ignore |

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
- 远端源码Git不纳入总项目正文、执行档案或dataset；本地资料Git允许跟踪docs及轻量实验记录，
  不跟踪源码开发clone、大产物和代码恢复包。旧通用初始化器的测试继续守护其历史接口。
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
| P-D10 | 项目 `docs/` 与全局知识 Vault 的衔接 | 2026-10-01 已修订 | 允许项目用薄清单显式引用稳定资料身份，正文仍归原系统；复制/归档仍产生独立身份，无同步、跨域覆盖、级联删除或强制 provenance |
| P-D11 | 开发与研究管理位置 | 2026-10-16 已锁定，待实现 | 本地保留完整研究总项目；所有子项目代码/Git/配置开发与执行均在远端，本地不留Primary等日常开发clone |
| P-D12 | 版本管理与发布 | 2026-10-16 已锁定，待实现 | 总项目本地Git不推送；各子项目独立远端Git，只有primary可向项目自有GitHub推送；不禁止其他子项目读取作者上游，并行目录隔离、实验固定commit |
| P-D13 | 全量实验登记与回传 | 2026-10-16 已锁定，待实现 | 所有子项目含失败/中断实验均登记，本地按子项目/Run/Attempt归档；轻量配方/指标/必要成果回传，大数据可只留清单，事实与本地分析分开 |
| P-D14 | 本地源码保存 | 2026-10-16 已锁定；备份策略仍待D7 | 最简可恢复材料，不是开发工作区；包含实验引用提交和必要恢复信息，未提交内容不假称已备份，verified仍需独立恢复验收 |
| P-D15 | agent与工具 | 2026-10-16 已锁定，待实现 | 本地SSH或远端CLI均可；不自动继承规则/登录/会话，不复制秘密或整库，不再建设Hub控制面；远端代码导航需新契约 |

## 14. 完成定义

系统改造只有同时满足以下条件才算完成：

1. 新项目共同契约与已锁定共识一致；
2. 源码 profile 不污染数据、实验、环境或文档边界；
3. Run/Attempt/Target 的身份和可变性由 schema 与测试守护；
4. 本地 promotion 与真正 backup 在状态上明确区分；
5. 旧项目无静默移动、删除、覆盖、untrack 或 profile 猜测；
6. 每个真实项目的配置和迁移都经过用户单独确认；
7. Claude Code 与 Codex 安装得到同一套能力与契约。
8. 项目 `docs/` 与全局知识 Vault 不形成静默双真源；项目导航引用不托管正文或授予外部写权限，
   跨域正文副本仍通过显式复制/归档获得独立身份，不依赖持续来源关系才能读写或演化。

本批 context/overview 的完成标准独立记录在 `project-centered-refactor.md`；不因新定位就宣称旧项目迁移、
真实实验或 verified backup 完成，也不以已经取消的 Hub 前端/worker 门禁阻挡独立内容能力的验收。

## 15. 本地研究总项目／远端子项目实施增量（WI-055，已安装、部分验收）

2026-10-21补充契约：所有实验在登记、开始、重要进展及成功/失败/中断终态及时回传
轻量档案，长实验在原任务/计划明确更新间隔和责任人。大成果按实际体积/成本例外留远端
并列入既有成果清单，不省略必要小证据；断线区分最后确认版本/时间与待回传内容，终态
轻量材料未收齐不得关闭交付。远端子项目按既有角色骨架、显式source profile及
Run/Attempt/Target格式检查，不用任意clone或角色声明冒充就绪；原生记录保留，旧格式
映射/迁移单独审议。完整运行细则唯一见references/project-management.md。
这次是未发布的skill契约改进，不实现传输、调度或新的全树validator；刚展示的详细目录
仍为建议，不据此操作真实工程。当前正常安装0.47.0及最新实证以HANDOFF为准。

当前0.46.1及同一test对象的实际结果见0.46.0-release.md。以下各开发切片保留各自时点，
其中“未安装/后续实现”不是现用能力结论；远端身份/部署/采集、原生打开与人工评鉴仍未完成。

2026-10-18开发切片：新增独立`project-management.json` schema1，不扩展只持有身份和源码
布局的layout schema2。总项目声明kind=research-parent、同layout的project_id和children；
每项包含子项目project_id、唯一archive_segment及primary布尔值，至多一个primary，允许
尚未选择primary。子项目声明kind=execution-child、自己的project_id、parent_project_id和
primary；双方须互认。归档目录段只作稳定映射，不代替身份；profiles保留给Target配置。
禁止自关联、重复ID/目录、未知字段或个人定位信息；schema定义字段结构，运行validator
另核跨行唯一及互认。只读`project validate-management --project-root <child>
--parent-root <parent>`可核对显式两根，不扫描、不写入、不联网；缺少声明不会自动推断。
单根仅核本地声明，不能称父子互认。该接口仍属未安装开发能力，不证明Git权限、实际部署
或执行位置；角色初始化、接收及恢复仍按后续切片实现。测试结果另见
project-management-identity-test-results.md，不据此重跑既有论文或实验验收。

同日续行：helper显式--role research-parent/execution-child已可为新空根生成不同骨架，
管理声明独立于layout；已有角色重复执行保留，非空通用项目/角色变化/祖先Git拒绝。
总项目有干净的空六节PROJECT（唯一内嵌计划）、README及空context，资料和轻量档案
不被整体忽略，恢复材料不进入Git；子项目有源码profile/toolkit和执行结构，无总体文档。
初始化子项目不反写总项目children，不宣称双方登记或远端可用。旧new-run在总项目上
于锁/写入前拒绝，防止误记管理commit。131项定向检查通过，未发布安装；后续接收、
定位、恢复与正式部署仍未实现。新角色骨架不是详尽资料整理或用户人工验收。

同日登记续行：`project register-child`默认零写入预览，apply绑定父子实际字节摘要，只追加
总项目children，不改子项目、主机台账或实验档案。同内容unchanged，过期/忙锁/冲突拒绝，
落盘不确定返回partial；239项相关检查通过。外部声明编辑在apply期间须停写，不声称
跨机器硬事务。未正常安装，也不证明远端部署/权限或档案接收。
同日新增只读collection-plan，显式单Run验证源快照、配方、五种Attempt状态、Target和
本地成果，保留原commit，提出远端report/notes与本地分析分离的映射（execution-report.md/
execution-notes.md）。115项定向检查通过；文件未接收，后续writer/CAS生命周期更新、
恢复与派生索引仍待。预检资源上限明确失败，不截断记录数量或冒充完整回传。
最新首次接收：receive-run凭三份摘要实际写入qualified Run，source记录不改写，本地分析
保留，机器receipt持有文件映射/hash/size/mode。stage读回后原生exclusive发布，同内容重试
验证后unchanged；不同版本拒绝而非覆盖。macOS已实测，Linux路径未验。115项相关回归
和末轮43项复验通过；曾发现publish后fsync异常分类错误，已修正并保留partial/retry证据。
CAS生命周期更新、显式crash恢复、qualified reader/index与正常安装仍待。
最新只读collected索引已实现，独立于source child读取并核验本地receipt/证据/原始路径映射，
Markdown条件与记录结果入口同表，JSON保留限定身份/范围与问题状态。128项定向检查通过；
不写第二份权威索引、不作科学比较或执行认证。版本更新/crash恢复、远端引用与安装态仍待。
最新update-plan已实现精确只读变化及旧receipt/新证据基线，固定配方与旧历史，保护人工
文件；待恢复标记使reader/replay失败关闭，不冒充活worker。124项回归、末轮70项通过；
apply/journal恢复仍未实现，不使用覆盖替代。真实对象/安装态及完整阶段边界不变。
最新内部恢复材料准备已实现：四摘要绑定，before/after与receipt落盘读回、记录原文件
身份，176项相关检查通过。只准备包，不改归档、不激活事务；未来writer须重新检查包语义
及当前归属，prepared/schema不授予覆盖权限。apply/commit/rollback仍待，未正常安装。
最新源码已有四摘要update-run与local-only recovery-plan/recover-update，先核验双方完整
版本/精确归属，再持久pending后写入，receipt最后。中断可显式提交/回滚，未知改动拒绝；
同内容重试也重做目录同步，不编造verified backup。205项相关检查通过，完整回归/当前
边界见同一test-results；尚未安装或做原生/人工验收，远端引用与源码恢复仍待。
最新context schema1新增execution-code，仅child UUID/安全相对代码位置/可选commit，
不是主机注册。remote-code-plan按所选既有SSH Target+ledger只读组合位置并核对当前字节；
不确认远端身份、版本、访问或SSH配置，不产生假原生链接。27新增/191相关检查通过；
尚未安装，原生远端验证与源码恢复仍待；完整阶段范围和旧人工/科学门禁不变。
最新本地源码恢复切片：code-recovery-plan检查明确提供的自包含SHA-1 bundle及所选
child全部已收集Run提交；retain-code凭计划摘要保存一份child/hash材料与独立覆盖记录。
23项新增及相关117项通过，严格machine schema不允许verified备份状态；中断保留明确
位置，不覆盖冲突，不联网/checkout/执行源码。未认证真实远端来源，也不捕获未提交/
未跟踪、LFS/子仓库payload或外部依赖；自动远端采集、安装态与原生/人工仍独立未完成。
交付审查补unchanged目录同步失败测试，首次红测证实错误分类5而非partial6，已最小修复；
24专项/118相关与当前完整3072项通过，11既有警告，138.79秒，不沿用旧快照。
正常安装后的单项目输入和可见评鉴要求见0.46.0-installed-acceptance-plan.md，尚未执行。

保留WI-020至WI-023的历史发布事实，不以本次设计反写为未完成。新增能力按以下小切片推进：

1. 固化总项目/子项目稳定身份、父子归属、角色、执行位置、归档限定引用与兼容版本契约；主机定位
   复用现有资产/Target机制，不建另一套服务器台账，不把child关联混成知识同步。
2. 分开总项目与执行子项目的初始化职责和Git策略，保留source/config profiles、数据toolkit和指令拓扑；
   不因选择角色创建远端机器、推送Git、安装agent、改动既有项目或生成虚假业务正文。
3. 实现远端登记与本地按子项目接收/索引，正确保存远端源码commit与配方快照；当前new-run依赖
   所选项目根的Git HEAD，不能在本地总项目调用它冒充远端Run登记。接收覆盖全部实验状态，
   幂等/CAS/来源变化/并发身份冲突/中断恢复均有明确回执，本地分析不被执行记录更新覆盖。
4. 增补受控远端代码定位和VS Code原生导航，让PROJECT继续展示代码模块与资料关系；
   不开放任意命令URI，不把可点击入口冒充连接成功、权限验证或实际运行。
5. 建立最简代码恢复材料的采集/清单边界，保护实验引用提交与未提交原创内容；不启用verified
   backup writer，不因存在恢复包宣称WI-041完成。
6. 先准备独立合成总项目/单子项目及输入、预期、失败分支，只做受影响定向验证；需要安装态验证时，
   再按独立hotfix正常发布/安装后验收。可见资料样例在test Vault，不重复批量论文或正式项目操作。

2026-10-16决定记录当时只完成规划一致性：没有修改runtime/schema/skill模板、运行实验、连接服务器、
迁移项目、发布安装或切换服务。真实服务器位置、迁移项目及备份介质/保留策略仍在各自授权边界内。
