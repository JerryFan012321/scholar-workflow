# Scholar Workflow — 开发规则

## 插件结构

```
5 Agents: intake / lineage / knowledge / feed / audit（任务级自足单元，skill 可跨 agent 复用；无固定单向 handoff，显式跨 agent 协作由宿主 LLM 或 agent-collaboration 编排）
14 Skills: survey-topic（宿主 LLM 顶层编排，不挂 agent）/ find-resource / ingest-resource / sync-projections / build-literature-tree / check-consistency / export-annotations / recommend-papers / analyze-paper / env-setup / agent-collaboration / init-project / config-setup / project-backlog（agent-collaboration 为所有宿主/agent 共享；其余四者用户直呼）
2 Host manifests: .claude-plugin/plugin.json / .codex-plugin/plugin.json（同名、同版本；共享 skills/hooks，MCP 配置保持等价）
确定性 CLI: src/scholar_workflow/ + bin/(scholar-workflow, zotero-annotations.py, recommend-papers.py)
Zotero 经官方 Local API: 元数据/存在性/索引全文/批注读取/写入(create/import/元数据)均经 `scholar-workflow zotero` 命令;主题召回用 Local API 全字段/全文 quicksearch 后由宿主模型排序,不自建向量库;任何组件都不得直接读取或写入 zotero.sqlite
论文下载: CLI 落入 paper_inbox 收件箱，再经 Zotero Local API 入库
```

## 产品定位与模块职责

以一个科研项目的完整资料上下文为使用中心：代码、相关论文、分析笔记、实验及成果可读、可追溯、
可按需调用。集中展现不等于集中存储或集中执行；现有编辑器、文献管理器、终端与 agent 宿主持有
各自原生能力，插件不再建设研究桌面、模型配置页或 Codex 任务控制面。

| 模块 | 唯一业务责任 |
|---|---|
| `project/` | 项目身份/布局、显式资料引用清单、Run/Attempt/Target/Artifact 档案 |
| `knowledge/` | 知识对象身份、归属、导航、公共知识模型和文档契约 |
| `analysis/` | 论文分析 IR、Markdown/Canvas 渲染、证据、conformance 与分析更新 |
| `adapters/` | 外部工具接口，不拥有项目/知识布局或第二份事实源 |
| `workflows/` | 组合核心能力完成明确任务，不维护另一套权威状态 |
| CLI / agents / skills | 薄调用入口、任务边界和可观察结果契约 |
| `hub/` | 历史服务/UI/任务的兼容边界；不再驱动新能力，不作为核心模块的必要前提 |

新内容核心不得反向依赖 Hub 服务或展示对象。旧导入路径只作兼容，知识模型不得继续放在论文分析
模块中扩展。重构按最小能力切片实施，不因目录归属纠偏删除恢复 journal、安全检查或人工内容。

## 运行边界

- **Project System** 持有便携 `project_id`、共同项目布局、源码/config profile 和
  Run/Attempt/Target/Artifact 档案；主机项目根只进入显式 host registry。
- **Knowledge System** 持有 Vault 核心文档、原子资源、附属产物、analysis result contract 和
  knowledge relations；批量产物逐项通过 conformance gate，失败不得记成功。
- 知识库以纲领、梳理和目录文档组织主题；论文、重要技术文档和 Blog/Web article 是原子资源，
  分析、批注、Canvas 和补充材料是附属产物。Paperlist 或文献树只是一种视图，不能定义整个知识库。
  持久论述应以可独立阅读的人类 Markdown 为主，机器身份与关系放在薄 frontmatter、manifest、
  sidecar 或可重建投影中，不淹没正文；Canvas 等非正文产物由 owner Markdown 说明。
- 需持续审阅并在 Obsidian 展示的知识实验和迁移候选放在独立 `test` Vault，`/tmp` 仅存可丢弃
  中间物；实验副本不自动注册正式 Field、不与正式 Vault 同步，也不代表迁移或发布验收获批。
- **历史 Hub** 的 `HubDirectory`、v1/v2 派生投影和浏览器安全规则继续保护实际兼容路径；
  它不是项目资料整合的权威，也不是新内容操作的前置条件。不自动停止已有服务或 worker。
- Project 可拥有显式的 `project-context.json` 资料引用清单，关联代码、Zotero/Vault 资料和项目实验
  成果；原文不复制、不代管，不建立自动同步、跨域覆盖、级联删除或强制来源追踪。引用不可用仅报告。
  人或 agent 显式复制内容时，副本仍获得目标 identity 并独立演化。具体契约见
  `references/project-context.md`，不把清单塞入只管布局的 `project-layout.json`。
- cmux 原生 workspace 只决定窗口打开位置。agent 在用户授权范围内直接使用原生 cmux/CLI，
  Codex 包括 `codex exec` 由外部工具持有配置、会话与生命周期。不得把 Hub 的 destination/target/
  recipe 登记推广为 agent 使用工具的通用前提，文件权限仍服从宿主与所选文件夹边界。
- 历史 Hub 项目文件写操作只限显式注册项目的 `docs/`，请求只接受 `project_id + docs 相对路径`；删除进入
  `.scholar-workflow/trash/docs/`，Hub 不执行 Git 写操作。Destination 的选择不得改变该授权结果。
- Knowledge Source/Field 必须动态登记：用户选择 Vault/目录后先生成零写入 preview，每次明确选择并
  确认一个 Field，才创建或追加 `.scholar-workflow/fields.yml`；选择整个 Vault 不等于批量登记全部
  候选。已有便携 manifest 但尚未登记到本机时，须另行预览并明确确认整份现有 Source；只写 host
  registry，保留 manifest、Field ID 和正文原样，不把它伪装成新 Field 的批量初始化。不得固定
  Field 枚举或要求唯一 `research_vault_root`。
- 真实 Field 多文件迁移只可在外部编辑器/同步器停写窗口中执行，靠逐文件 CAS、持久 journal 和条件恢复
  达成可恢复的逻辑事务；不能宣称文件系统硬原子或把恢复快照称为已验证备份。旧论文分析改写须同时
  守恒旧 Markdown 未标记正文及每个字段、旧 Canvas 节点/边，并让候选 Markdown/Canvas/sidecar 通过
  正式 conformance；未经可信人工批准的同一合成摘要不得放行。用户已原则批准调整经核实为纯机器生成的
  世界模型旧稿，无须再逐字段请求内容裁决；这不免除原件保留、当前字节绑定、科学来源核验和事务审批。
  其他同级集合须先只读确定边界并核实机器来源，不得据此批量自动迁移。首次登记含旧分析或旧链接的 Field
  须把 manifest、host registry、内容、导航和链接作为同一事务审议，不能先用旧网页确认身份；新导航
  不得静默遗漏预览中的旧文档。受管分析 Markdown/Canvas/sidecar 不得经单文件 Hub 编辑器改写。
  本地操作员的事务入口虽已接入开发树，真实 JEPA 的 Provider+Field 联合事务及停写验收仍未完成，
  不能仅凭上述内容批准据此迁移。
- 兼容命令 `scholar-workflow open-hub` 从已安装包启动或安全重启受管服务，经 mode 0600 discovery 发现动态端口，
  并把调用者当前 cmux workspace 记为默认打开位置（若存在）。服务不得依赖 code repo root；
  `hub start/status/stop/restart/doctor` 必须显示并核验真实 executable、build、PID、generation 与日志。
  受管进程的启停身份握手不得依赖 Zotero、其他 provider 或 cmux 路由的健康；详细能力诊断与
  生命周期身份探针分离，慢速诊断不能让存活的 HTTP 服务被误判为未知进程。
- 论文/PDF/Field 使用稳定 EntityRef/PdfRef 直接生成动作；正常 UI 和新文档不得经过人类可见
  paper/attachment/document landing，也不得产生固定 loopback URL。旧 landing 只作一版本兼容解析。
- Zotero 是正式批注唯一权威，ZotFlow 是唯一可持有 Zotero Web API 读写密钥的客户端且密钥只留在
  Obsidian SecretStorage；Hub、CLI、agent、配置、环境和日志不得获取它。Scholar Workflow 只经 Local
  API 读取批注形成只读 AnnotationIR；ZotFlow Source Note、Better Notes 与 Scholar 分析目录 writer 分离。
- Hub 与 ZotFlow 阅读论文 PDF 不得依赖 Zotero Web API/WebDAV 附件下载。ZotFlow 已审计版本、
  本机 Zotero storage 模式和对应附件必须在动作执行时得到非秘密的正向验证；验证失败即拒绝打开，
  不回退云端文件端点。
  元数据/批注的 Web API 同步可以继续；不得为验证本机模式读取 ZotFlow 的密钥或完整秘密配置。
- 新论文分析的作者事实与分析推断须在每个 claim/point 的行内证据旁提供可验证原文位置；Zotero PDF
  使用 attachment identity、内容 hash、物理页索引与可选的真实批注 key，Vault Markdown 使用已登记文档
  identity 与块锚点。Canvas 同点保留原文入口和对应正文反链。页级跳转不得冒称逐句/批注定位；结构
  conformance 不等于来源存在性、归属与版本核验。cmux PDF surface 仅本机只读预览，不能冒称嵌入
  Zotero 原生 reader 或正式批注写回；Zotero 深链打开独立应用。
  新正文的原语言逐字短摘录与同点来源链接遵守 `skills/analyze-paper/references/analysis-format.md`；
  Canvas 不重复摘录，旧格式不静默刷新。
- 新生成的论文分析正文和解析树以最新通用参考图的完整五分支及展开子槽位为输出契约，
  详细规范唯一持于 `skills/analyze-paper/references/analysis-output-template.md`，不规定阅读或推理顺序。
  当前 v4 四分支/合并 details 与 v1–v3 旧框架仅属各自版本的兼容接口；生成器尚未适配新图，
  不得用旧格式测试通过冒充新输出规范已实现，也不因修订规范重新分析或批量迁移已有论文。
  英文内容使用英文结构标签，中文内容使用中文标签；空槽位不编造论文事实。Canvas 必须保留可编辑
  JSON text 节点和直角无箭头连接，逐点证据、原文入口及对应正文反链不得因紧凑排版丢失。正式 Vault
  旧分析迁移仍需独立审议，test Vault 样张不能冒充真实论文验收。Advanced Canvas 自动添加的
  受限 `metadata`（`version`/`frontmatter`）须被校验并保留，但不能当作 Scholar 对象身份或放行任意顶层字段。
- v4 人类 Markdown 与 Canvas 节点正文不输出 `sw-analysis-claim` 机器注释；块锚点、确定性节点 ID 与
  sidecar 承担身份。Canvas 文本框按中文换行留出约一行点击空间，仍守护整体长宽比。来源 span 身份与
  阅读器入口分离：在已核验 Vault 可显式选择 ZotFlow Library Reader 页级投影，Markdown/Canvas
  同步渲染并成对校验；未核验时保留 Zotero 原生入口，不手改其中一个文件。
- 新论文的资料笔记、分析 Markdown、Canvas 和 sidecar 同处 Field 内
  `resources/papers/<stable-paper-segment>/`；PDF 仍归 Zotero。目录段须与资源 ID 持久映射，旧平铺
  产物只原位兼容，正式搬迁需显式 CAS/恢复事务及链接清理，不能靠普通分析更新顺手移动。
- 历史 Hub TaskRecipe 只接受 allowlisted target、已验证的上下文 EntityRef、最多 8 KiB 的 bounded brief、
  已批准的 `model_profile_id` 和该模型支持的 reasoning effort；`fast/standard/deep` 仅作旧请求兼容。
  浏览器不能提交命令、cwd/path、原始 model、sandbox、permission、环境变量或任意 config。
  首次设置另经用户确认安装候选、模型目录、目标及有界的读写策略，不在任务请求中开放权限配置。
  模型目录不是账号可调用性证明；已有线程固定实际模型和思考强度，改变配置须新建或显式 fork。
  这些仅维护旧入口安全，不代表继续建设内置 Codex；不修补本次已被用户取消的非 Git 任务入口。
- 论文卡片相关文件只由 manifest/provider 的明确归属产生，按需加载；同名不证明同一论文。
  缺失文件保留诊断，Markdown 可正文预览及 Obsidian 打开，Canvas 在 Obsidian 编辑；
  ZotFlow 来源笔记与 Scholar 分析分属不同 writer。cmux 原 PDF 动作明确不含 Zotero 数据库批注。
  任务只自动选择唯一匹配的 recipe/target；歧义须选择，无目标须登记，禁止任取列表首项。

## 设计哲学(上位准则)

所有下游规则(skill / reference / INV / NG / 约束)都服从这两条。冲突时,本节优先。

### 只为「外来规定」写约束,不为模型的内在能力写约束

落笔任何约束前,先判断它属于哪一类:

- **内在能力** —— 「一无所有的模型」本就会做的事:判断两篇论文是否相似、写摘要、
  跨论文比较、决定文档归哪个分类、理解用户意图、组装 JSON / markdown / 表格。
  **不要**把这些写进 skill / reference / 约束 —— 那是在教模型它本就会的事,是冗余,
  会变成限制、诱发过度思考、拖慢执行。
- **外来规定** —— 模型无法自行推导、项目 / 环境 / 领域特定的事实:判重键 =
  DOI / title+authors 而非 arXiv id;只从 arXiv 下载 PDF;Zotero 为唯一权威库、
  附件保持 imported;Notion data-source 用 `in_trash` 而非 `archived`;破坏性操作要审批。
  **只有这一类值得写下来。**

自检句:「这条是在编码模型推导不出的外来规定,还是在复述它的内在能力?」后者一律不写。
此判据同样用于**做减法** —— 审视现存约束,凡属内在能力类的,精简掉。

运行期 skill 遵守全局「Skill 边界原则」：管理真实流程（如有）与末端呈现，不管理内部思考。
有明确业务/工具操作流程时，描述输入、依赖、操作分支、交接、安全权限和完成条件；
探索性任务没有固定流程时，不人为规定阅读、分析、分类或推理顺序。
本项目的末端契约是**硬规则**：文件/schema、章节层级、Canvas 节点与连线、语言、证据、链接、
存储位置和完成状态必须满足各自产物规范。不能为省事或适配当前生成器合并/省略必备子项；
不合格式即不通过，能力未实现即明确报告，不用近似输出冒充合格。具体模板仍只由对应 reference 持有。

### 开发验证与真实执行分离

必须安装后才能验证的 Hub/CLI/插件集成，遵守全局安装态验收原则：在独立
`codex/hotfix-<scope>` 分支上迭代，每轮实机验收前安装该分支的候选构建，标明
分支、source SHA/build、安装包和实际服务身份，保留上一安装版本的回退方式。
hotfix 按可正式发布的独立版本打包并通过正常安装/更新入口部署到实际使用环境；
必须有可识别版本、确定源码提交和完整 runtime-only 产物，临时 venv 或源码直跑不算
产品安装。hotfix 发布/安装与 main 合并分离，约定验收通过后才合并；不得在验收前
冒称稳定主线已完成。发布脚本从当前已提交且干净的开发分支生成 runtime-only release，
可用于 hotfix，不得为发布而提前合并。测试范围与安装/服务切换影响先按测试独立原则展示并获批；
只复验受影响的单对象功能及必要回归，不重做仍有效的整批业务验收。

开发或迭代 skill、CLI、Hub 契约时，内循环先用合成 fixture 和一个受控对象
（一篇论文、一个仓库或一个 `test` Vault 样本）验证路由、格式、安全和失败恢复；
按风险补充定向边界用例，不把真实批量入库、整库扫描或正式迁移反复用作调试循环。
运行期 skill 仍须完整执行用户实际要求的范围，这条开发规则不能成为缩小用户任务的理由。
需要真实全集验收的发布门禁，在实现稳定后按已批准范围进行一次完整预览和受控执行；
代码或输入变化使摘要失效时重新生成并审议，不沿用旧结果，也不因节省验证成本跳过安全门禁。

### 约束分两类:业务约束稳定维护,优化约束随能力做减法

过了上一条筛子(非内在能力冗余)的真实约束,再分两类,增删逻辑相反:

- **业务约束** —— 用户对交互内容定的规矩:文件格式、功能要求、判重键、存储位置、
  arXiv-only、安全边界。这是用户意志的编码,**不随模型能力淘汰**;按用户需求增长
  是健康的,不受「简化」压制。

- **优化约束** —— 帮 agent 更高效执行的脚手架:编排提示(先 X 再 Y)、token 与功能
  发现的优化、流程门禁、计划文档的详细度。这类**随模型增强而贬值** —— 今天靠提示
  才做对的编排,更强的模型自己就会。定期 ablation:拿掉后行为不变,即删。

「复杂度趋势 / 做减法」只作用于优化约束;业务约束该稳定维护。区分二者的自检句:
「这条是用户对结果的要求(业务),还是我对 agent 过程的引导(优化)?」

## Conventions

### Skill Anatomy

每个 skill 目录须包含：

```
skills/<name>/
├── SKILL.md          # Required — frontmatter (name, description) + observable result, interfaces, constraints
├── README.md         # English documentation
├── README.zh-CN.md   # Chinese documentation
├── scripts/          # Executable scripts (if any)
└── references/       # Skill-specific operational docs, loaded on demand
```

SKILL.md 的 `description` 字段是宿主判断是否触发该 skill 的主要机制，触发词准确性直接影响路由质量。
正文以可复现的**最终结果契约**为主：产物归属与身份、文件/schema 字段、内容层级、证据和链接、
可读呈现、完成/失败状态及验收标准。有真实操作流程时写清必要步骤与分支；探索性问题不硬套
流程，通用的研究、分析、分类、排序、总结和写作方法不写进运行期 skill。末端格式严格执行，详细格式放入
按需加载的 reference，不把单篇样本的事实或节点数推广成通用模板。运行期安全约束写在各
SKILL.md 的 Constraints 小节，不放本文。
面向人呈现的笔记、Canvas、报告、Hub 和 CLI 文本共同遵守 `references/human-presentation.md`；
该文件只约束可见结果的可读性、来源、链接和状态，各产物仍由自己的格式契约决定具体结构。

### References: two tiers

- **Top-level `references/`** — canonical cross-skill policies (storage / source /
  identity / security). One source of truth; every skill and agent obeys them.
- **Per-skill `references/`** — operational detail specific to one skill.

Never duplicate a rule across tiers. When a skill needs a shared rule, its own
reference points to the top-level file rather than restating it.

## Documentation boundary

Two disjoint sets of docs. Keep them separated — never mix authoring guidance into
runtime docs or vice versa.

| Set | Location | Audience | Loaded when |
|---|---|---|---|
| **Development docs** | `dev-guide/` | The developer / Claude authoring or iterating a skill | While working in this repo |
| **Planning docs** | `planning/` | The developer / Claude planning a phase | While working in this repo |
| **Runtime docs** | `references/`, `skills/*/references/` | The Claude executing a user task | When a skill fires |

- `dev-guide/` — how to build and evolve skills: `skill-authoring.md`,
  `skill-iteration.md`, `eval-loop.md`. **Never loaded at skill runtime.**
- `planning/` — the living **planning layer**: `GOALS.md` (intent), `HANDOFF.md`
  (session hand-off), and per-phase specs (e.g. `phase2-sync-projections.md`).
  Permanent, **never archived**. Never loaded at skill runtime.

Both `dev-guide/` and `planning/` are permanent, development-time layers. They differ
by content, not lifecycle: `dev-guide/` is the cross-phase **"how to build"**
methodology (stable); `planning/` is the per-phase **"what to build / goals / hand-off"**
(changes with each phase). Neither is loaded at skill runtime.
- Runtime docs describe *what the plugin does*, not *how to develop it*. A skill's
  `## References` section lists exactly which runtime files to load — it must never
  point into `dev-guide/` or `planning/`.
- `planning/GOALS.md` — the living **intent layer**: upstream goals, long-term
  invariants, non-goals, phase status. Continuously updated, never archived. It is
  the north star; `evals/` guards each goal by its stable ID (G/INV/NG).
- Original design docs (DESIGN.md, PROJECT.md) have been **archived out of the repo**
  to `archived/scholar-workflow/project_references/`. Their intent layer lives on in
  `planning/GOALS.md`; the architecture layer is a frozen snapshot — the code is authoritative
  for architecture, so do not restore or sync those docs.

### Language

- **SKILL.md** — Written in English. Chinese trigger words in the `description` field are fine.
- **Agent files (`agents/*.md`)** — English. They are runtime-loaded plugin artifacts, same as SKILL.md.
- **References** (top-level and per-skill) — English.
- **README.md** — English.
- **README.zh-CN.md** — Chinese (use `zh-CN` suffix, not `zh`).
- **Python code, comments, and technical diagnostics** — English. Human-facing renderers (including CLI summaries) may use explicit `en`/`zh` presentation labels; one output must keep its chosen language consistent.

## Behavior Boundaries

### Always Do

- Read `dev-guide/` (skill-authoring / skill-iteration / eval-loop) before authoring or iterating a skill
- Read the existing SKILL.md / agent file before modifying
- Update `CHANGELOG.md` before every commit — group entries under the skill name
- Bump `.claude-plugin/plugin.json` and `.codex-plugin/plugin.json` together **per coherent capability batch, not per commit** — a user-perceivable feature batch is minor, fixes are patch. During the 0.x pre-release phase, iterations *within* one batch (multiple commits refining the same capability) share a version and don't each bump. This avoids same-day triple-jumps like 0.6→0.7→0.8.
- Update `planning/GOALS.md` when a goal, invariant, non-goal, or phase status changes — keep IDs stable, assign new IDs for new items
- Update the Agent → Skill mapping table when adding or renaming a skill
- Test skill triggering by reviewing the `description` field — it's the primary routing mechanism
- Write contract test before modifying any adapter interface
- Update `contracts/handoff.schema.json` before modifying the state machine
- Before committing, propose the `pytest tests/unit tests/contract` test plan with its
  inputs, expected results, impact, and artifacts; run it only after user approval.
  Do not treat an untested change as validated or ready to commit.

### Ask First

- Renaming a skill or agent directory (breaks existing references)
- Removing a skill from the plugin
- Changing the `description` field format or triggering strategy
- Adding any destructive Zotero operation (delete, overwrite-conflict, merge) to a skill/agent — additive writes via Local API are the normal path and need no gate
- Modifying hook interception rules
- Adding external dependencies to a skill's `scripts/`

### Never Do

- Hardcode API keys, tokens, or user-specific absolute paths in any file
- Write SKILL.md body in Chinese (trigger words in `description` are fine)
- Use `README.zh.md` naming — always use `README.zh-CN.md`
- Skip contract tests when modifying adapter interfaces
- Commit test artifacts, secrets, or sensitive absolute paths to Git

## Agent → Skill 映射

Agent 按「会独立吃掉大量上下文的用户任务」切分，每个自足拥有完成该任务的全部 skill；
skill 可跨 agent 复用（如 find/ingest 同时服务 intake 与 lineage），不归属单一 agent。
Agent 之间没有固定 handoff 图。默认完成自己的任务并把结果交回调用方；当用户或既定工作流
明确要求多 agent 协作时，任一宿主/agent 都可通过 agent-collaboration 双向委派边界清楚的
子任务，由调用方统一整合与验证。

| Agent | 任务 | 可用 Skills |
|---|---|---|
| intake | 定向获取（找 + 入库） | find-resource, ingest-resource |
| lineage | 方向级调研 + 建文献树 | find-resource, ingest-resource, build-literature-tree |
| knowledge | 单篇知识投影（分析 / 批注 / 索引） | analyze-paper, export-annotations, sync-projections |
| feed | 每日推荐流（略读 + watchlist） | recommend-papers |
| audit | 跨系统一致性审计（只读） | check-consistency |
| （宿主 LLM 顶层编排，不挂 agent） | 开放式调研的 scope + 委派 | survey-topic |
| （所有宿主与 agent 共享） | 跨 agent 双向协作、任务委派与接力 | agent-collaboration |
| （无 agent，用户直呼） | 环境台账 | env-setup |
| （无 agent，用户直呼） | 宿主中立的 Git 项目骨架初始化 | init-project |
| （无 agent，用户直呼） | 插件配置（config.yml 读写 + 初始化） | config-setup |
| （无 agent，用户直呼） | 项目工作队列（planning/BACKLOG.md） | project-backlog |

## CLI 退出码

0 完成 | 2 输入错误 | 3 依赖未运行 | 5 身份冲突 | 6 部分完成可恢复 | 7 安全拒绝 | 8 外部服务错误

审批(exit 4)已退场:CLI 的 apply 只下载 PDF 到收件箱(纯新增、可幂等),破坏性动作的审批在 skill 层由宿主 LLM 逐条执行,CLI 无触发路径。码位 4 保留不复用。

## Changelog

`CHANGELOG.md` follows [Keep a Changelog](https://keepachangelog.com/). Every change must be recorded before committing:

- **Added** — new skills, features, scripts
- **Changed** — rewrites, refactors, behavior changes
- **Fixed** — bug fixes
- **Removed** — deleted features or skills

Bump the version in `plugin.json` when releasing a coherent set of changes. Use semver: major (breaking), minor (new skill or feature), patch (fixes and improvements).

## Release branch

Two branches, disjoint by purpose:

- **`main`** — the development branch. Everything lives here: runtime code **plus** the
  development layer (`planning/`, `dev-guide/`, `tests/`, `evals/`, `AGENT.md`, `CLAUDE.md`).
- **`release`** — an **orphan** branch (independent history) that ships to users. It
contains **only runtime files**: `.agents/plugins/marketplace.json`, `.claude-plugin/`,
  `.codex-plugin/`, `agents/`, `bin/`, `contracts/`,
  `hooks/`, `references/`, `skills/`, `src/`, `scripts/guard-sqlite.sh`, `.gitignore`,
  `CHANGELOG.md`, `README.md`, `README.zh-CN.md`, `pyproject.toml`. No dev docs, no tests,
  no `AGENT.md`/`CLAUDE.md` (the latter references a private `@RTK.md`).

**Never commit to `release` by hand.** Build it from `main` with `scripts/make-release.sh`
(idempotent; each release commit records the source `main` SHA). Flow: land changes on
`main` or an approved hotfix branch → run the script → review `release` → push `release`. Keep the runtime manifest in
the script and the boundary in both READMEs' "Development" section in sync. Personal data
(machine paths, proxy ports, real tokens/interests) must never reach runtime files, since
those ship — audit before releasing.
