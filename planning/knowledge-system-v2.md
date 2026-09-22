# 科研知识系统 v2 — 改造计划

> 状态：Accepted 0.2，2026-09-22。用户已授权实施知识对象、分析结果接口与批量 conformance；
> 现有 Vault、JEPA 真实产物和 23128 服务仍不得在本批静默迁移或切换。
>
> 本文与 `project-system-v2.md`、`hub-control-plane-v2.md` 是并列规格：项目系统管理项目源码、数据、
> 环境与实验档案；知识系统管理跨项目复用的知识对象和阅读产物；Hub 负责聚合与受控操作。Knowledge
> 与 Project 只通过人或 agent 显式复制内容衔接，副本获得目标系统身份并独立演化。

## 1. 触发背景与实物证据

2026-09-21 对真实 V-JEPA 2 分析产物的只读检查暴露出四类系统性问题，而非单篇生成质量问题：

1. **知识对象没有统一上位模型**：同一论文同时出现在主题目录、两棵文献树、`paper_assets/`
   原子卡、分析 Markdown、Canvas 与 Canvas manifest 中；各层身份和关系并不统一。
2. **机器同步格式压倒人类正文**：分析笔记共 476 行，其中 194 行是逐字段
   `sw-analysis-field` 注释；正文又以中英字段清单和重复状态后缀展开，难以连续阅读。
3. **解析树把 schema 逐字段绘制成图**：Canvas 有 194 个文本节点、193 条边，边界约为
   `2220 × 35940`；25 个独立 Evidence 节点重复正文已有证据，5 个“对应挑战 / 贡献”节点并非原图要求，
   方法步骤也被逐字段拆散。Fit-to-content 后文字必然过小。
4. **入口与服务身份不清**：三个主题级目录文档共硬编码 122 个
   `127.0.0.1:23128/open/paper/...` 链接；审计时占用正式端口的是旧版 `serve-links` 常驻服务，
   旧 PDF 路由可用而 `/hub/` 与 Hub API 不可用。当前源码已有统一 Hub，但服务升级和所有权没有收口。

这些事实同时否定两种修补方式：不能只美化一个 Canvas，也不能只把更多字段塞进现有 HubCatalog。
需要先固定知识系统的对象模型、人类投影和入口契约，再改运行时。

## 2. 目标与范围

知识系统 v2 提供五个相互分离、可组合的能力：

1. **知识空间契约**：以一组纲领性、梳理性和目录性核心文档组织一个主题。
2. **原子资源契约**：论文、重要技术文档和 Blog/Web article 是可独立引用的资源原子。
3. **附属产物契约**：分析、批注、Canvas、阅读笔记、代码笔记和补充材料明确隶属于资源或主题。
4. **人类/机器双投影**：人类可读 Markdown 是必备正文；机器身份、关系和更新状态使用薄 metadata、
   manifest 或 sidecar，不反向污染正文。
5. **统一资源入口**：Hub、Obsidian、Zotero、cmux 与 Web Source 从稳定资源身份派生动作；
   loopback 端口是实现细节和兼容层，不是知识文档的上位标识。

本阶段不重新发明 Zotero、Obsidian 或 Hub，不把 Hub 变成数据库，也不批量重排 Vault。

## 3. 决策优先级与权威边界

发生冲突时按以下顺序处理：

1. 根 `AGENT.md` 及其导入规则；
2. `planning/GOALS.md` 中的 G/INV/NG；
3. 已同步进入 GOALS 的、本文标为“已锁定”的用户要求；
4. 本文的共同知识契约；
5. 单类资源或产物的 profile；
6. 单个主题经用户确认的布局覆盖；
7. 既有文件名、旧端口 URL 或历史生成模板。

新的用户共识必须先同步到 `GOALS.md` 与 `CHANGELOG.md`，phase spec 只细化、不得覆盖上位 G/INV/NG。

权威分配保持不变：

| 对象 | 权威存储 | 说明 |
|---|---|---|
| 论文 library/work identity、书目信息、PDF、正式批注 | Zotero | DOI / title+authors 决定 work 判重，item/attachment key 指向库内对象 |
| Vault 原生技术文档、Blog 快照、人类知识正文、Canvas | Obsidian Vault | 原始 Web URL 保留为来源；归档版本记录抓取时间与哈希 |
| 稳定投影 ID 与映射 | 版本化 manifest / registration | 现有 `resource_id` 是离线投影/命名 ID，不是 Zotero 判重身份；显式映射到 item key 与 artifact ID |
| 跨知识对象关系声明 | 版本化 Vault manifest/provider | workflow payload 只是校验过的 transport；持久声明原子落盘后 knowledge catalog 才能汇编，不拥有关系真源 |
| Notion | 单向简化投影 | 不成为正文或文件真源 |
| 项目内工作文档与实验报告 | 对应项目 `docs/` / `experiments/` | 不属于知识对象；显式复制/归档后在 Vault 创建新的独立技术文档身份 |

## 4. 三层知识对象模型

### 4.1 核心文档层

一个 Knowledge Space 对应一个主题，可拥有多份核心文档。核心是“人如何进入和理解这个主题”，
不是某个目录名。首版定义三种可重复角色：

- **charter / 纲领**：主题边界、核心问题、术语、当前判断、维护状态和推荐阅读路径。
- **survey / 梳理**：技术路线、挑战—洞见、时间线、比较或其他综合视图；同一主题可有多份。
- **catalog / 目录**：该主题纳入的全部原子资源账本，可按资源类型形成不同视图。

新主题的推荐最小集合是一个可作为入口的 charter，以及一个覆盖全部原子的 catalog；既有主题只在
显式迁移时补齐。文献树是 survey 的一种，`01-Paperlist.md` 是 paper-only catalog 的历史形态；
二者不再代表整个知识库的顶层模型。

### 4.2 原子资源层

首版原子类型：

- `paper`：library/work identity 由 Zotero Local API 核验的 DOI、无 DOI 时的 title+authors 确定；
  Zotero item key 指向库内对象。跨 Vault/Hub/Notion 的现有 `resource_id` 继续使用
  `make_resource_id` 的 arXiv→DOI→metadata-hash 离线命名规则，它是稳定投影 ID、绝不参与 create/skip
  判重。manifest/workflow payload 必须显式保存 `resource_id ↔ zotero_item_key ↔ work identifiers` 映射；
  本计划不重算或批量替换既有 `resource_id`。论文可属于多个主题。
- `technical-document`：正文真源在 Vault。项目 `docs/` 中的文件在被显式归档前不是全局知识资源；
  归档后创建新的 Vault-native identity，与项目副本独立演化，不维持托管链接或强制 provenance。
- `blog-post`：以 canonical URL 标识来源；需要长期保留时，把带抓取时间与哈希的快照归档到 Vault。

以上是人类可读的逻辑名；实现若扩展现有 Python `ResourceKind`，沿用其 underscore value 风格，使用
`technical_document` 与 `blog_post`，不同时维护第二套语义不同的枚举。

当前 Python `ResourceKind` 还包含 `snapshot`、`drawio`、`image`、`dataset`，它混合了语义资源与文件形态，
不能直接当作新三层模型。K1 实现时推荐显式迁移映射：`paper` / `technical_document` 保持原子类型，新增
`blog_post`；`snapshot` 变成资源 rendition，`drawio` / `image` 默认成为 owner 下的 asset，`dataset`
默认成为附属 data asset 或 unresolved legacy kind。只有人工明确登记为可独立阅读的重要文档时，图或数据说明才提升为
`technical_document`。旧枚举值在非破坏迁移期间继续可读并带 schema version，不静默重分类或删值。

原子资源是可单独引用、检索和打开的对象。主题内可有人类易读的 resource hub/card 来说明其在该主题
中的位置，但不得复制 Zotero 元数据或原文形成第二份真源。

### 4.3 附属产物层

附属产物必须有一个主 owner：某个原子资源或 Knowledge Space / topic。产物可以另外用 `attached_to`
指向某份核心文档，但这不改变其唯一主 owner。首版包括：

- analysis note / analysis canvas；
- annotations / reading note；
- code note / reproduction note；
- supplement / image / data asset。

附属产物可以通过 `related` 关联其他对象，但其主 owner 唯一。删除原子资源、topic 或被关联的核心文档时
不得级联删除附属文件；只报告悬空关系并等待人工处理。

resource-owned 的 canonical analysis / Canvas 不随 topic 分身：同一论文即使属于多个主题，也只维护一份
规范分析对，各主题的 resource hub 只链接它。主题特有的解读、比较或方向笔记是独立的 topic-owned
context artifact，不冒充第二份 canonical paper analysis。

### 4.4 关系图

```text
Knowledge Space / Topic
├── Core documents
│   ├── charter
│   ├── catalog
│   └── survey(s)
├── Atomic resources
│   ├── paper
│   ├── technical-document
│   └── blog-post
└── Attached artifacts
    ├── resource-owned: analysis / annotations / canvas / supplement
    └── topic-owned: glossary / direction note / comparison / map
```

关系使用稳定 ID；权威对象旁的版本化 manifest/provider 保存关系声明，`knowledge_catalog` 从这些声明汇编
可重建的共享接口快照，既不拥有关系真源，也不从文件名、自由 Markdown 或 wikilink 猜语义。正文里的
wikilink 只承担人类导航。

通过 schema 校验的 workflow payload 只是声明 transport，不是跨进程真源。任何需要在下一次运行重建的
ID mapping 或关系，必须先以原子替换写入版本化 manifest/registration；落盘失败则本次 catalog 更新失败，
不能只留在内存或把临时 stdin 当权威。Hub 重启时只从权威系统与这些持久声明重建。

多来源 assembler 的 merge 必须确定且 fail closed：同一 resource/topic/artifact ID 只有在 immutable
identity、kind、authority、locator 与 owner 字段一致时才能合并，并只 union 可多值的 relations。
任一来源给出冲突的 work/item mapping、kind、authority mode、locator、owner 或 artifact role 时，整次
catalog build 停止并报告 ID、字段和所有声明来源；绝不按输入顺序、时间或 incoming-wins 静默择一。

## 5. 推荐 Vault 投影

逻辑角色是硬契约，路径只是新主题的推荐默认值。实现前不自动重命名现有 `paper_assets/` 或
`01-Paperlist.md`：

```text
<knowledge-root>/
├── resources/                          # 跨 topic 的 canonical resource-owned 产物
│   ├── papers/<resource-segment>/
│   │   └── attachments/
│   │       ├── analysis.md
│   │       ├── analysis.canvas
│   │       └── annotations.md
│   ├── documents/<resource-segment>/
│   └── blogs/<resource-segment>/
└── topics/<topic>/
    ├── 00-<topic>-导览.md              # charter / 人类入口
    ├── 01-资源目录.md                  # catalog：论文、文档、Blog 全集
    ├── 02-<view>-梳理.md               # survey，可重复
    ├── 03-<view>-文献树.md             # survey，可重复
    ├── resource-links/                 # topic-local hub / 语境入口，只链接 canonical 产物
    └── attachments/                    # 只放 topic-owned context artifacts
```

兼容迁移时可把既有 `paper_assets/` 视为 `resource-links/` 的历史布局，不立即移动，也不就地复制其中链接的
canonical analysis。`knowledge_catalog` 由显式 manifest/provider 中的 role、kind 和 ID 汇编，不依赖上面的
英文目录名或编号；具体根目录仍由 config 决定，不把这个示意路径硬编码进 runtime。

`resource-segment` 不是原始 `resource_id`。现有 ID 可能含 `:`，DOI 分支还可能含 `/`，因此实现必须
生成跨平台 path-safe 的 encoded/hashed segment，并在 manifest 保存 `resource_id ↔ resource-segment`
映射。拒绝空段、`.`、`..`、路径分隔符、绝对路径和正规化后逃逸；在目标文件系统的 Unicode/case
正规化规则下检测碰撞，碰撞时 fail closed 或加入确定性 hash 后缀，绝不修改原 `resource_id`。

## 6. 人类正文优先契约

### 6.1 必备的人类版本

每个承载论述、分析或梳理的持久知识产物必须有一个脱离 Hub、sidecar 和 Canvas 后仍可独立理解的
Markdown 正文。Canvas、图片、数据等非正文字节不必各自复制成 Markdown，但其 owner 文档必须用人类
语言说明它们是什么、为何存在以及如何使用。正文允许表格、公式、Mermaid、脚注与 Obsidian 链接，
但不能要求读者理解 canonical path、baseline hash、JSON 字段或内部状态机。

允许的机器层：

- 文档头部的薄 `sw_*` 身份字段；
- `.scholar-workflow/artifacts.yml` / `assets.yml` 关系 manifest；
- 为增量更新保存 section/claim/node baseline 的隐藏 sidecar；
- 可随时从权威数据重建的 `knowledge_catalog` 和结构化导出。

禁止把逐字段 hash 注释、关系边或状态表复制到正文。机器版不得成为第二份需要人工同步的知识正文。

### 6.2 更新与冲突保护

现有逐字段 `sw-analysis-field` 标记移出正文。推荐 sidecar 保存：

```text
analysis artifact id
Markdown section / claim id -> last generated hash
Canvas node id -> mapped claim id + last generated hash
generated edge ids
```

只有被 Canvas 或外部产物精确引用的关键主张，才在 Markdown 使用短小的 Obsidian block ID；不再为
每个标题和字段插一行机器注释。focused update 以语义小节或 claim 为边界：发现人工修改时保留正文并
给出拟议 patch，不静默覆盖；Canvas 用户节点、位置、尺寸与自建边继续保留。

sidecar 缺失、损坏、版本不兼容或与 Markdown/Canvas revision 不一致时，更新必须零写入。只允许从
可验证的旧 generated snapshot / journal 恢复；没有可信基线时，系统只能输出拟议 patch，或等待用户
显式执行 adopt/rebaseline，把当前人工内容登记为新基线。不得从当前正文静默重建 baseline 后继续更新。
一次 focused/whole update 实际触及的 Markdown、Canvas 与 sidecar 构成一个逻辑事务；中断后只能依据
可信 journal 完成或回滚整组变更，否则保持零写入并输出 patch，不能留下任一文件领先的半提交状态。

## 7. 论文分析 v2

### 7.1 Markdown 是详细真源

分析笔记从“字段清单”改为连续、可阅读的解释。全文 profile 固定覆盖五个语义角色；每个角色内的
段落和 claim 数量可按论文内容伸缩：

1. **任务**：论文解决什么问题、处在端到端工作流的哪个位置。
2. **输入**：方法消费什么观测、表示、先验或上下文，以及必要前提。
3. **分步流程**：一段总体说明 + 连续编号流程；每一步把“做什么、产生什么中间状态、为何有效、证据”写在一起。
4. **输出**：方法直接产出什么、如何使用或评估，不能把潜在下游用途冒充论文输出。
5. **边界**：局限、未覆盖条件与能力边界，区分作者陈述和分析推断，并说明影响范围。

无法核实的内容仍必须区分“论文未报告”“当前正文通道无法核实”“不适用”，但只在相关主张处说明，
不在每个字段重复状态后缀，也不为了填满模板制造空字段。

### 7.2 证据与反链

- 证据紧跟对应主张，使用短括注、脚注或链接，例如 `（§3.2，Figure 4）`。
- 不再生成独立 Evidence 小节、Evidence 节点或 field-to-anchor 重复索引。
- Markdown 脚注的回跳承担 evidence → claim 反链；Canvas 节点通过
  `[[<分析笔记>#^<claim-id>|正文与证据]]` 回到对应主张。
- 论文证据与实现代码证据继续分层；代码行不能替代论文内锚点。

### 7.3 Canvas 是概览投影

Canvas 不再逐字段复制 Markdown，而是让人快速理解论文：

- 固定按“任务 → 输入 → 分步流程 → 输出 → 边界”组织五个顶层导航分支；
- 每个节点对应一个完整语义单元，而不是一个字段标签；
- 分步流程使用一个连续流程区，步骤按阅读顺序排列，每步在同一节点中合并做法、作用和证据；
- 删除 pipeline 中的“对应挑战 / 贡献”，也不为它们另造解析树分支；
- 证据写在主张节点内，并链接到 Markdown 的正文与证据；不单独占节点；
- 生成的文字节点必须使用标准 JSON Canvas `type: "text"` 与 `text` 字段；保留的人工节点也必须是
  合法的 `text/file/link/group` 节点，但不计入系统生成节点预算、尺寸或重叠规则；
- Canvas 节点不得携带 `sw-analysis-field` marker，机器状态放 sidecar；
- 细节超出概览容量时留在 Markdown，不继续拆节点。

视觉默认值：

- 分支标题和节点标题使用 Markdown heading 提升字号，不依赖私有 Canvas 样式字段；
- 内容节点建议宽 420–560、高 180–320，节点间距不少于 80；
- 使用 group 或清晰泳道组织五个分支，避免单列无限向下延伸；
- 以 V-JEPA 2 为 golden case 时，全部生成语义节点默认不超过 40 个，且不牺牲五个导航分支；
- 必须做真实 Obsidian 截图验收：常用窗口下标题可读、节点无重叠，分步流程无需来回跳列。

JSON Canvas 1.0 没有可移植的 `font-size` 字段。首版通过 heading、节点尺寸、文本密度与布局解决字号，
不把私有 CSS 设为必需依赖；若仍不足，再单独决定是否提供可选受管 CSS。

## 8. Hub、PDF 与资源入口

### 8.1 稳定入口不是端口 URL

长期契约只保存稳定资源/产物身份和安全 locator：Zotero item/attachment key、Vault artifact ID 与
canonical Web URL。Project identity 属于 Projects Library，不进入知识关系或知识 locator。
具体打开方式由服务端在运行时派生：

- 论文条目与本机 PDF：Zotero 原生动作；
- 浏览器 PDF 预览：Hub 从 attachment key 注册 opaque action；
- Vault Markdown/Canvas：Obsidian 原生动作或 Hub 安全预览；
- Blog/Web article：只从 catalog 中已登记的 canonical HTTPS URL 生成 allowlisted action；
- Notion：Web Source 用于跨设备；本机入口只指向带稳定 resource/artifact ID 的 Hub
  landing route，不把 raw PDF endpoint 或 opaque action handle 当知识身份。

opaque action ID 是单个 Hub 进程内的短期 capability，禁止写入 Markdown、manifest、Notion 或其他
持久投影。landing route 打开后，服务端用稳定 ID 回读当前 catalog、重新校验 locator，再为本次进程
生成动作。Hub 重启后旧 opaque action 必须失效，但持久 landing 仍能解析并获得新动作；landing 的
origin/port 是可刷新部署投影，不进入资源 identity 字段。

现有 `/open/paper/<attachment-key>` 保留为兼容路由和内部预览能力，但新正文不再把
`127.0.0.1:<port>` 作为规范资源标识批量写入。

### 8.2 Hub 接口边界

服务 owner、Library、workspace、TaskRecipe、Projects/Tools registry 和 UI 属于
`hub-control-plane-v2.md`。知识系统只提供版本化 `knowledge_catalog` provider，并要求：

- `HubDirectory` 是唯一公共根；旧 `HubCatalog` 只是 `knowledge_catalog` 的兼容投影；
- knowledge provider 汇编论文、Vault-native 技术文档、Blog、核心文档和显式 manifest，不读取项目正文；
- Canvas 如果不在 Hub 图形化渲染，就交给 Obsidian 原生视图，不能把 raw JSON 称为人类预览；
- 旧常驻服务只作为迁移 fixture；本知识规格不负责停止、替换或升级它。

## 9. 与科研项目系统 v2 的接口

项目 `docs/` 是项目本地工作正文；全局 Vault 持有跨项目核心文档、知识关系与 Vault-native 产物。
二者没有自动同步或托管引用：

1. Knowledge→Project 由人或 agent 显式选择 Markdown/Canvas/owned assets，复制到已注册项目的 `docs/`；
2. 复制时移除 `sw_*`、sidecar、baseline marker 和知识关系，目标冲突时拒绝；
3. Project→Knowledge 由人或 agent 显式归档，创建新的 Vault-native technical document 和 identity；
4. 系统不要求保存跨副本语义 provenance；通用安全审计不得变成持续关系；
5. Run/Attempt 报告仍归实验档案，复制其人类可读内容不改变实验身份或保存规则。

## 10. 迁移原则

- 先扫描、再输出 migration plan；默认零写入。
- 旧 Markdown、Canvas、布局、自建节点和现有链接原样保留，迁移生成新版本或显式 patch。
- 扫描同一 work/resource 在多个 topic 下的 analysis/Canvas 副本：content hash 相同只提出 alias/dedup
  计划，仍不自动删除；hash 不同则标记 unresolved，逐份保留，并提出“一份 canonical + 其余
  topic-owned context artifact”的候选拆分。canonical 选择、重命名、合并或删除必须逐项由用户确认，
  绝不按时间、路径、mtime 或输入顺序自动择一或覆盖。
- 先用临时 fixture 验证，再把 V-JEPA 2 作为首个真实 golden case；其他主题逐个确认。
- `paper_assets/`、`01-Paperlist.md` 与旧 raw port 链接只在用户批准后迁移，不批量机械替换。
- 新 runtime 发布与真实 Vault 迁移分开记账；通过测试不等于用户数据已迁移。

## 11. 实施阶段与退出条件

### K-A — 契约冻结与 eval 设计

交付：本规格、GOALS/HANDOFF/BACKLOG 对齐；知识对象、关系、人类正文和入口 eval 草案。

退出：K1–K6 有明确结论；没有修改 runtime 或 Vault。

### K-B — 知识模型与 Catalog assembler

交付：resource/artifact roles、Blog 类型、旧 kind 兼容映射、核心/原子/附属关系 schema、技术文档与 Blog assembler。

退出：稳定 ID、权威来源、正反向关系有 contract tests；Hub 不从自由 Markdown 猜语义。

### K-C — 人类可读分析与机器 sidecar

交付：分析 Markdown v2、section/claim baseline sidecar、focused update 与冲突回执。

退出：去掉 frontmatter 后正文仍可独立理解；无逐字段 marker 或重复 Evidence 表；人工修改不被覆盖。

### K-D — 解析树 v2

交付：概览 Canvas、连续 Method 流、内联证据与 claim backlink、视觉 fixture。

退出：JEPA golden case 满足节点预算和截图验收；无独立 Evidence 节点、无“对应挑战 / 贡献”。

### K-E — knowledge catalog provider 与稳定入口

交付：版本化 `knowledge_catalog` provider、统一资源身份与 landing/action 映射、旧 HubCatalog 兼容投影。

退出：新投影不持久化 raw loopback URL，Hub 重启后可从稳定 identity 重建 action；PDF Range/HEAD、
Vault 冲突保护和 opaque action 安全测试不回归。服务生命周期由 Hub Control Plane v2 验收。

### K-F — 批量 conformance 与维护审计

交付：analysis profile/IR 校验、逐篇状态机、一次修复上限、失败清理/隔离和周期性知识库审计。

退出：模板、证据、Canvas 图和节点预算不合格的条目不能进入 validated；单项失败不污染其他条目；
维护命令默认只报告和生成修复计划。

### K-G — 显式迁移与发布

交付：临时 fixture、JEPA migration plan、经确认的迁移、双宿主文档与 release snapshot。

退出：迁移前后人工正文、布局、自建节点和反链保留；完整 unit/contract/eval 与真实视觉验收通过；
CHANGELOG 清楚区分规划、实现和数据迁移。

## 12. 测试矩阵

至少增加以下守护：

- 核心文档、原子资源和附属产物关系无悬空、无重复 ID，可反向查询。
- 既有 paper `resource_id` 保持不变，并显式映射 Zotero item key/work identity；Hub/Notion/分析产物不把
  arXiv-first 投影 ID 当成 DOI/title+authors 判重键，也不因元数据补全静默生成第二个投影对象。
- 原始 `resource_id` 不直接插入路径；resource-segment 编码在 POSIX/Windows、Unicode/case 正规化下
  无分隔符、`.`/`..`、越界或碰撞，并能经 manifest 唯一回查原 ID。
- 多来源对同一 resource/topic/artifact ID 的相同 immutable 声明可合并并 union relations；identity、kind、
  authority、locator、owner 或 role 任一冲突必须 fail closed 并列出来源，不能 incoming-wins。
- workflow payload 只作 transport；持久关系/ID mapping 必须先原子写入带 schema version 的
  manifest/registration。模拟写入中断后不得出现仅内存可见或半写状态，重启可完整重建同一 catalog。
- 同一 resource 的 canonical analysis / Canvas 在多 topic 引用下仍只有一个 owner/path；topic context artifact
  使用不同 kind/ID，不与 canonical 分析互相覆盖。
- paper / technical-document / blog-post 使用各自权威存储，不复制主数据。
- 旧 `snapshot/drawio/image/dataset` 能按 schema version 无损读取并输出显式迁移计划，未确认时不重分类。
- Markdown 去掉 frontmatter/sidecar 后仍含完整论点与证据出处。
- 分析正文不含逐字段 baseline marker、独立 Evidence 索引或强制空字段。
- focused update 只改目标 section/claim；人工内容冲突时返回 patch 而非覆盖。
- sidecar 必须绑定目标 Markdown/Canvas revision 或 content hash；本次触及的 Markdown、Canvas 与 sidecar
  构成一个逻辑事务。对每个文件替换边界做 fault injection：中断后只凭可信 journal 完成或回滚整组
  变更，否则零写入并输出 patch。sidecar 缺失、损坏、版本不兼容或映射漂移时也只能从可信旧 generated
  snapshot / journal 恢复，或等待用户显式 adopt/rebaseline，绝不从当前人工正文静默生成 baseline。
- Canvas 无 dangling edge、节点/边 ID 唯一，节点具备标准 JSON Canvas type 与对应内容字段，用户布局与
  合法自建节点保留。
- JEPA golden Canvas 不超过 40 个生成内容节点，无独立 Evidence 节点和“对应挑战 / 贡献”。
- Obsidian 截图在默认主题、常用窗口下标题可读、节点不重叠、Method 连续。
- 技术文档和 Blog 能进入 `knowledge_catalog` 并获得 allowlisted 打开动作。
- Knowledge→Project 显式复制只选择人类产物及明确 owned assets，剥离 `sw_*`/sidecar/managed relation；
  同名目标拒绝，复制后不产生同步或托管来源关系。Project→Knowledge 归档创建新 identity。
- whole-paper profile 覆盖五个角色；focused profile 只更新声明子集。
- batch item 逐项经历 queued/running/validated/failed/repaired，失败至多修复一次，失败临时产物被清理且
  不能影响其他 item。
- 新投影不持久化 raw loopback URL 作为资源身份；legacy `/open/paper/` 仍兼容。
- 持久 Hub landing 只含稳定 ID；Hub 重启后仍可从 catalog 解析并生成新 opaque action。旧 action handle
  必须失效，且 Markdown/manifest/Notion 中从未出现进程内 action ID。
- Hub service status 能识别正确版本、旧版本、错误 capability、端口冲突和多个 owner。
- 旧服务切换不破坏 PDF HEAD/Range、Vault 原子保存、CSRF/Origin 与 opaque action 边界。
- migration plan 零写入，未确认时 JEPA 和其他 Vault 文件逐字节不变。
- 多 topic analysis 副本同 hash 时只建议 alias/dedup、不删除；不同 hash 时全部保留为 unresolved，并把
  canonical/context 候选及差异交用户逐项裁定，不按时间、路径或输入顺序自动选择。

## 13. 决策门与推荐

| ID | 决策 | 状态 | 当前推荐 |
|---|---|---|---|
| K1 | 核心/原子/附属对象类型与关系 | schema、旧 kind 兼容映射和 provider CAS apply 已在 0.28.0 工作树实现；真实迁移未完成 | core=`charter/survey/catalog`；resource=`paper/technical-document/blog-post`；保留现有 `resource_id` 投影 ID，并显式映射 Zotero work/item identity，路径另用受检 `resource-segment`；同 ID 冲突 fail closed；resource-owned canonical artifact 不随 topic 分身；旧 file-like kinds 迁到 rendition/asset 层 |
| K2 | 人类正文与机器状态的真源 | 人类正文优先已锁定 | Markdown 为必备正文；复杂身份、hash 与 edge 移入 manifest/sidecar；Canvas 不是第二份正文 |
| K3 | 证据与反链 | 证据内联、不独立列已锁定 | 主张内短锚点/脚注；脚注回跳 + Canvas 到 claim block link；不生成 Evidence 节点 |
| K4 | Canvas 拓扑与字号 | 连续流程、删对应挑战/贡献、增大可读性已锁定 | 任务/输入/分步流程/输出/边界 + 语义节点；heading/大节点/低密度/截图验收；首版不依赖私有 CSS |
| K5 | Hub 接口 | 已冻结 | 输出版本化 `knowledge_catalog`；唯一根、service owner 和启动体验由 Hub Control Plane v2 决定 |
| K6 | 首个真实迁移对象 | 外部决策门 | 临时 fixture 后用 V-JEPA 2 作为 golden case；确认 patch 后才改真实 Vault |
| K7 | 批量校验与维护 | 已冻结 | 每篇独立校验、最多一次修复、失败隔离；周期审计默认只读并生成计划 |

项目系统接口门 **P-D10** 已冻结为显式独立复制：不登记托管链接，不维持同步或强制 provenance。

## 14. 完成定义

只有同时满足以下条件，知识系统 v2 才算完成：

1. 每个主题有清晰的人类入口、资源目录和可重复的综合视图；
2. 论文、重要文档、Blog 与附属产物有稳定身份和明确权威来源；
3. 所有承载论述、分析或梳理的持久产物都有独立可读的人类正文；Canvas、图片与数据由 owner 正文说明，
   机器状态不淹没正文；
4. 解析树是可读概览，不是字段 schema 的逐格绘图；
5. 证据与主张共处并可反向导航；
6. PDF/文档从稳定资源身份打开，用户无需理解或维护 raw 端口 URL；
7. 单篇和批量输出都必须通过相同 conformance gate，失败不能被记作成功；
8. Hub 能从稳定 identity 消费 knowledge provider，而 knowledge 系统不承担 service/workspace/task 所有权；
9. 既有 Vault 未经逐主题确认不移动、不覆盖、不批量改写。
