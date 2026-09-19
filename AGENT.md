# Scholar Workflow — 开发规则

## 插件结构

```
5 Agents: intake / lineage / knowledge / feed / audit（任务级自足单元，skill 可跨 agent 复用；无固定单向 handoff，显式跨 agent 协作由宿主 LLM 或 agent-collaboration 编排）
14 Skills: survey-topic（宿主 LLM 顶层编排，不挂 agent）/ find-resource / ingest-resource / sync-projections / build-literature-tree / check-consistency / export-annotations / recommend-papers / analyze-paper / env-setup / agent-collaboration / init-project / config-setup / project-backlog（agent-collaboration 为所有宿主/agent 共享；其余四者用户直呼）
2 Host manifests: .claude-plugin/plugin.json / .codex-plugin/plugin.json（同名、同版本；共享 skills/hooks，MCP 配置保持等价）
确定性 CLI: src/scholar_workflow/ + bin/(scholar-workflow, zotero-annotations.py, recommend-papers.py)
Zotero 经官方 Local API: 元数据/存在性/索引全文/写入(create/import/元数据)均经 `scholar-workflow zotero` 命令;主题召回用 Local API 全字段/全文 quicksearch 后由宿主模型排序,不自建向量库;唯一例外——批注导出允许 bin/zotero-annotations.py 以只读(mode=ro&immutable=1)直读本地 DB,绝不用于元数据判定或任何写入
论文下载: CLI 落入 paper_inbox 收件箱，再经 Zotero Local API 入库
```

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
├── SKILL.md          # Required — frontmatter (name, description) + trigger, steps, constraints
├── README.md         # English documentation
├── README.zh-CN.md   # Chinese documentation
├── scripts/          # Executable scripts (if any)
└── references/       # Skill-specific operational docs, loaded on demand
```

SKILL.md 的 `description` 字段是宿主判断是否触发该 skill 的主要机制，触发词准确性直接影响路由质量。
正文只保留项目特定的路由、精确工具调用、产物格式、环境事实与安全/权限边界；通用的研究、分析、
分类、排序、总结和写作方法不写进运行期 skill。运行期安全约束写在各 SKILL.md 的 Constraints
小节，不放本文。

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
- **Python code, comments, and user-facing string literals** — English.

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
- Run `pytest tests/unit tests/contract` before committing

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
`main` → run the script → review `release` → push `release`. Keep the runtime manifest in
the script and the boundary in both READMEs' "Development" section in sync. Personal data
(machine paths, proxy ports, real tokens/interests) must never reach runtime files, since
those ship — audit before releasing.
