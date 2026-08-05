# Scholar Workflow — 目标（活文档）

> 这是项目的 north star，持续更新。原始设计文档（DESIGN.md / PROJECT.md）的意图层
> 已提取进本文，源文件已归档到仓库外 `archived/scholar-workflow/project_references/`，
> 不再是仓库的一部分。本文的目标与不变量是权威对照基准。每条目标带稳定 ID，
> `evals/` 用 ID 回指来守护它。
>
> 权威关系：目标（本文） → 守护（evals/） → 实现（代码）。
> 校验一条目标是否达成，看它的 eval，而不是看设计文档。

## 上位目标（G）

意图层，不因实现方式改变。改动须谨慎并记入 CHANGELOG。

| ID | 目标 |
|---|---|
| G1 | 管理论文、书籍、技术文档及相关数据；第一阶段优先论文与技术文档 |
| G2 | 每个对象只有一个主存储位置，其他系统只保存索引、投影或管理信息 |
| G3 | 论文 PDF 的自动获取源头只能是 arXiv；下载后落入收件箱，再经 zotero-mcp 入库，其他来源仅用于身份与元数据核验 |
| G4 | 论文入库经 zotero-mcp 写入完成。新增性写入（下载、create、import、补元数据、加入分类）在用户已下达入库指令时直接执行，不逐一二次批准；仅破坏性/不可逆动作（删除、覆盖冲突条目、合并身份）须逐条批准 |
| G5 | Zotero、Obsidian Vault、Notion 各司其职，不互相复制主数据 |
| G6 | 大型目录采用分层索引：先读索引，再按需读实体文件 |
| G7 | 插件由 Git 管理，功能必须有评测和回归测试 |
| G8 | 首要宿主是 Claude Code。Zotero 的读/写/语义检索能力经 zotero-mcp（MCP server）提供，由宿主 LLM 调用；确定性 CLI 收缩为 arXiv 获取、收件箱、投影等与 Zotero 访问无关的工作流 |
| G9 | Zotero（及其 PDF 存储）是唯一权威主库；元数据、存在性、语义检索经 zotero-mcp 获取。写入经 zotero-mcp 的受控工具完成；新增性写入直接执行，破坏性动作须批准 |

## 长期不变量（INV）

任何实现、任何阶段都必须成立。违反即为回归。

| ID | 不变量 | 守护 eval |
|---|---|---|
| INV1 | 一篇论文在 Zotero 中对应唯一条目（item）；条目可隶属多个分类（collection），分类是对条目的多对一投影，不构成重复身份。判重键为 Zotero 规范身份（DOI / title+authors），arXiv id 仅为下载源标识、非判重键；经 zotero-mcp 两步核验（search_library 召回 → get_item_details 回读字段）防止重复新建；模糊命中只提候选、写路径转冲突交人工裁决（NG3） | outcomes: dedup-exact-collapse |
| INV2 | 论文 PDF 由 Zotero 存储（`~/Zotero/storage`）统一持有；技术文档即使是 PDF 也进 Vault | routing: file-technical-doc / outcomes: tech-doc-isolation |
| INV3 | PDF 位置迁移只通过 Zotero 附件关系 + `link_service.storage_root` 配置，不在多目录复制 | outcomes: papers-root-remap |
| INV4 | Obsidian 论文表是可重建的派生索引，不是主库 | outcomes: obsidian-human-block-preserved |
| INV5 | Notion 不上传论文/技术文档/图片/数据文件 | safety: no-notion-file-upload |
| INV6 | Notion 机器字段可更新；人工内容不得被同步覆盖 | safety: no-overwrite-human-block |
| INV7 | 状态库只存映射/游标/任务状态/审计，不存知识正文 | （待补） |
| INV8 | 外部程序不得直接写 `zotero.sqlite` | safety: no-sqlite-write |
| INV9 | 对 Zotero 的写入只经 zotero-mcp 的受控工具，绝不直接写 sqlite。新增性写入（create/import/补元数据/加入分类/下载）在用户已下达指令时直接执行；破坏性动作（删除、覆盖冲突、合并身份）须逐条批准 | safety: no-unapproved-destructive-zotero |
| INV10 | 库内条目元数据以 zotero-mcp 查询为权威；新增条目的元数据取自权威网源（arXiv abs / CVF / DBLP / 出版社），绝不从 PDF 解析；有正式发表版本时会议名覆盖 arXiv 预印本名头 | （待补） |
| INV11 | 下载的论文 PDF 只落入 `paper_inbox`，入库前不复制到多目录；入库经 zotero-mcp（`write_item` import）完成，由 Zotero 迁入其存储 | （待补） |
| INV12 | 存在性与元数据以 zotero-mcp 查询为权威、实时获取；zotero-mcp 不可达时 fail-fast（退出码 3），绝不因"查不到"判为新建 | safety: no-existence-on-unreachable |
| INV13 | ~~本地 `resources` 缓存是 Zotero 的派生只读镜像~~ **已废止（deprecated）**：取消本地缓存镜像，存在性/元数据/语义检索一律实时委托 zotero-mcp。ID 保留不复用 | — |
| INV14 | 模糊/语义召回委托 zotero-mcp 的 `semantic_search`；不再在本项目内自建或自禁 embedding/向量索引 | （待补） |
| INV15 | 离线解析器对标识符输入不造占位标题（`title` 为 null）；显示用真名由展示层可选补齐（EXACT 经 zotero-mcp 取名、NONE 用对话/抓取），绝不作为判定输入。契约自描述，能力缺失时降级为显示 identifier | resolver: title-null-for-identifier |
| INV16 | scholar-workflow 硬依赖 zotero-mcp 提供 Zotero 读/写/语义检索；doctor 必检其可达性；不可用则 fail-fast（退出码 3），目标层不设降级分支 | （待补） |
| INV17 | 投影中指向论文 PDF 的链接**按投影目标分策略**:**Obsidian**(本机 app)指向 loopback link-service（`127.0.0.1`），按**附件 key** glob `~/Zotero/storage/<附件key>/*.pdf` 解析、inline 流式吐**原始** PDF；URL 只存不透明附件 key，绝不存绝对路径，PDF 仅本机点开。**Notion**(云文档、跨设备)**双链共存**:`Web Source`=arXiv abs / DOI web URL（任意设备/浏览器可开,他机回落用),`Local URL`=loopback link-service（本机浏览器打开 Notion 时秒开标注版 PDF,比绕 arXiv 网页快）。本机为主场景下 loopback 在本机 Notion 可用;跨机时用 Web Source。两条 URL 均只存不透明附件 key,不存绝对路径 | （待补） |
| INV18 | sync-projections 的规划（宿主 LLM 经 zotero-mcp 取字段）与执行（CLI 写文件 / 起 link-service）分离，只经 JSON 消息通信；CLI 不碰 MCP、不读写 `zotero.sqlite`（link-service 只读文件系统） | （待补） |
| INV19 | Notion 投影**单向 本地→Notion**（本地=真相源，机器只推、不回流）；Notion 是**简化跨设备前端**,相关文档只投影**一段话摘要 + 回 Obsidian 的 Vault 回跳链接**,**笔记正文永远留在 Obsidian**、不进 Notion——无正文可传,故 INV5「不上传文件」平凡成立;知识库层次经 `Category` + `Project` relation + 父子页面镜像 Zotero 分类树 | safety: no-notion-writeback / no-notion-full-body |
| INV21 | **Notion 双库模型**:**Papers 库**(每篇论文一行,upsert 键=Zotero 规范身份 `Resource ID`)+ **Related Docs 库**(每篇周边文档一行,upsert 键=vault 相对路径 `Doc ID`,经 `Paper` relation 指回论文)。编排顺序**先 upsert 论文拿 page_id、再 upsert 相关文档带 relation**。本阶段 relation 恰为一篇论文(无论文的方向笔记押后)。镜像 Obsidian 的「论文索引行(INV1)+ 相关资料枢纽(INV20)」两层结构 | outcomes: notion-two-db-relation-order |
| INV20 | **论文相关资料文档(Obsidian 枢纽)**:每篇论文可按需在**索引表同目录**挂一个相关资料文档(`<论文名>论文相关资料.md`),聚合该论文的**周边资料位置链接**(阅读笔记/方向笔记/补充材料),**不重复论文元数据**(元数据属 Zotero+索引行)。(同一论文在不同主题文件夹下各有一份、内容随语境不同,见 INV25)索引表经**受管块之外**的「相关资料」小节链接到它——块外由 INV4 保护、重投影不覆盖,故无需给 10 列表格加列 | （待补） |
| INV22 | **文献树为 novelty tree**(彭思达 literature-tree 法):**可变深度**概念分类拓扑,内部节点是**抽象概念**、论文是**叶**(按 `resource_id` 引用)。**两种同构树共用一套 `concept` 结构与同一渲染器**,靠节点 kind 区分:**技术路线树** `topic → 里程碑任务(task) → pipeline/representation → module(可选) → 论文(叶)`;**挑战洞见树** `topic → challenge → insight → 论文(叶)`。每个概念节点记 **novelty 锚点**=首个提出该概念的论文,按节点类型:**task=类1、pipeline=类2、module=类3**(挑战树中 insight 可选记首提者、challenge 通常不记);**类4=用 module 改进已有 pipeline 的工作**,是**论文级属性**(语境相关),作普通成员挂在被改进节点下、**不设 schema 字段**。一个 doc 一棵树,技术树与挑战树各自编号自含笔记(`02-…技术路线树`、`03-…挑战洞见树`),**共享同一全集**(承 INV25 一文多树)。树旁**并存一份 flat 全集 paper list**(单一元数据账本,论文可在册但 `classified:false` 未分类)。**Vault 布局**:一个主题的全部内容放在一个**以主题命名的文件夹**里(无 `-literature-tree` 外壳);索引文件用**图书馆编码前缀**——`01-Paperlist.md` **固定**是扁平全集账本,每棵树/视图是带编号的自包含笔记(`02-…文献树.md`、`03-…`,创建序,skill 分配编号、CLI 只固定 01 槽)。**一棵树=一个自包含笔记**:内联 Mermaid 概览 + 嵌套 `##`任务/`###`pipeline 小节(各带 novelty 锚点、可选 `内容简介`、`论文列表` subpaperlist);**无 H1**(文件名即标题)。每篇论文另有 `paper_assets/<年>-<第一作者>-<标题>.md` 相关资料笔记,其 `# 相关文献树` 小节反向链接回它在树中的 pipeline 位置(承 INV20 枢纽)。本轮渲染目标限 **Obsidian 受管块 + 内联 Mermaid**(不产 PNG/draw.io/HTML/Notion),块外内容幂等存活(复用 INV4/INV18 机制)。(一文多树与附属分身见 INV25) | outcomes: novelty-tree-topology-and-paperlist / module-level-and-challenge-tree |
| INV23 | **略读级(recommend-papers)临时性**:略读经外部服务(四推荐源 REST + NotebookLM)进行,四源(S2 Recommendations / Scholar Inbox / S2 author watchlist / HF Daily)按 arXiv id 合并去重,仅对用户细化后的 shortlist 走 NotebookLM 略读(省 token,不略读全池);产物为**临时 Reading Report,绝不落 vault、不改 Zotero**;看中的论文经 find/ingest 正式管线入库(判重两步核验)。CLI 不碰这些网络/MCP(承 INV18),聚合在 `bin/recommend-papers.py` | （待补） |
| INV24 | **详细分析级(analyze-paper)源与落点**:详细分析只经 zotero-mcp `get_content` 读正文(承 INV10 不解析 PDF 本体),产物落 Obsidian 附属分析笔记(`<论文名>分析.md`),与人工批注笔记**分立**、`related` 互链;局部分析在同一笔记**受管块之外多小节追加**(承 INV4 保护),并挂到该论文相关资料枢纽(INV20) | （待补） |
| INV25 | **论文↔文献树多对多,附属按主题分身**:同一篇论文(按 `resource_id`/Zotero 规范身份唯一)可被**任意多个概念节点、多棵树**引用——同 topic 内多树(`02-`/`03-`…含技术树+挑战树)、跨不同主题文件夹的树皆可;树节点只**引用**不复制,元数据全局唯一(承 INV10,不因复现而重复)。反链是复数关系:一篇论文的 `# 相关文献树` 小节可同时指向多棵树的多个位置。**附属笔记(`paper_assets/…`)按主题文件夹分身**:同一论文在不同 topic 下各有一份,内容随语境不同(反链指向各自 topic 的树、聚合各自周边资料);`01-Paperlist.md` 是**每个主题文件夹内**的账本,同一论文入多个主题各登记一行(按 topic 隔离,非全局单账本)。绝不加"一个 resource_id 只归一个节点/一棵树"的唯一性检查 | outcomes: paper-in-multiple-trees |

## 非目标（NG）

明确不做的事，防止范围蔓延。

| ID | 非目标 | 守护 eval |
|---|---|---|
| NG1 | 从出版社/网盘/搜索引擎/非 arXiv 站点自动下载论文 PDF | safety: no-nonaxiv-pdf / outcomes: no-nonarxiv-autodownload |
| NG2 | 绕过付费墙、验证码、登录或访问控制 | （待补） |
| NG3 | 自动删除、覆盖或合并身份冲突的 Zotero 条目 | outcomes: identity-conflict-stop |
| NG4 | 直接写 Zotero SQLite | safety: no-sqlite-write |
| NG5 | 未经批准对 Zotero 做破坏性写入（删除、覆盖冲突条目、合并身份）；或跳过存在性核验直接 create 造成重复 | safety: no-unapproved-destructive-zotero / no-create-without-existence-check |
| NG6 | 把论文全文或技术文件上传到 Notion | safety: no-notion-file-upload |
| NG7 | 无证据自动宣布某论文是"突破性工作"（反浮夸）。注意与 INV22 的 novelty 锚点区分:锚点是"首个提出该 task/pipeline/module(类1/2/3)"的**可核实先后事实**、非价值判断,不受本条约束;本条禁的是给论文贴超出锚点定义的"突破"徽章 | （待补） |
| NG8 | 第一阶段自动下载书籍/标准/数据集文件（先只做元数据和索引） | （待补） |

## 阶段状态（随开发更新）

| 阶段 | 目标 | 状态 |
|---|---|---|
| Phase 0 | 插件骨架、契约、evals 基线、开发规范 | ✅ 完成 |
| Phase 1 | 论文发现 + 下载到收件箱 + 经 zotero-mcp 入库（find-resource / ingest-resource 真实可用；存在性/语义/写入经 zotero-mcp） | 🚧 进行中（resolver / 下载到 inbox 已落地；CLI 的 sync/locate/resolve/catalog 退场；存在性/写入迁移至 MCP；skill/reference/agent/evals 已按 zotero-mcp 重写并对齐；实战已完成 create/import/补元数据/加入分类闭环） |
| Phase 2 | 投影同步（Obsidian 索引 + 本机 PDF 链接服务 + Notion 双库投影） | 🚧 进行中（Obsidian 层级投影 + loopback PDF link-service + launchd 自启已落真机 vault；**Notion 双库(Papers + Related Docs)已 v0.8.1 实盘上线并固化进 skill 层**——机械层 `bin/notion-project.py`(唯一 Notion API 出口，CLI 零外部网络)+ 展示层 SKILL.md 组装专题页；已用 text2cad 8 篇端到端验证。剩：方向级笔记(无 Zotero item)的 Notion 表示，INV21 显式押后作后续 ticket） |
| Phase 3 | 文献脉络树 | 🚧 进行中（novelty tree 模型 v0.10.0 落库；**v0.15.0 渲染形态重构**：一棵树=一个自包含笔记(内联 Mermaid + `##`任务/`###`pipeline 分节 + subpaperlist)、`01-Paperlist.md` 独立全集账本、图书馆编码前缀、多树共存、`paper_assets/` 相关资料笔记 `# 相关文献树` 反链(INV20)、无 H1;共享渲染器 `projection.py` 删 DOI 列 + 星级 Importance(连带 sync-projections 变 9 列)。schema:`literature-tree.schema.json`(paper_list + 三级概念树 + summary/asset_note + challenge-insight seam)、`workflows/novelty_tree.py`(render_mermaid + render_tree_note/render_paperlist + plan/project，复用 render_table/ObsidianAdapter)、`project-literature-tree` CLI(带 --dry-run + paperlist_only)、SKILL/agent/docs、INV22 + outcomes 守护。**v0.17.0 模型广义扩展**:novelty 三类→四类(task=1/pipeline=2/module=3 节点锚点、类4=改进型论文作普通成员不入 schema)、拓扑加**可选 module 第四层**(变深度)、**挑战洞见树(challenge→insight→论文)从 schema seam 升为正式落地**——与技术树同构、复用 `concept` 结构与同一渲染器(F3 兑现);`render_mermaid` 由硬编码三层重写为递归 N 层(修 module/insight 被图静默丢弃的 bug)、`_KIND_DEPTH`/`_ANCHOR_LABEL`/classDef 加 module/challenge/insight 表项;新增 INV25(一文多树+附属按主题分身)。实盘端到端已完成(世界模型 39 篇双树)。剩：真实主题更多端到端实盘） |
| Phase 4 | 一致性审计 | ⏳ 未开始 |
| Phase 5 | 两级 AI 阅读（略读推荐 + 详细分析） | 🚧 进行中（recommend-papers：四源聚合适配器 + HF Daily 单源贯通 + vendor Scholar Inbox 客户端 + 两层 recommend.yml + SKILL/README 已落地，INV23；analyze-paper：SKILL/README 已落地，INV24；build-literature-tree 加 NotebookLM 批读编排提示。剩：notebooklm-py 实盘略读闭环、watchlist 半自动登记子模式、doctor 探针 + 回落、B1/B2 端到端实跑） |

## 未来项（记录待办，暂不实现）

| ID | 事项 | 说明 |
|---|---|---|
| F1 | 给文章标题加入重要程度批注 | 在展示/索引论文标题时附一个推荐重要程度的批注，辅助人工判断优先级。待 Zotero 元数据读取链路稳定后再设计。 |
| F2 | ~~Zotero 官方本地写 API 落地后重启程序化写入~~ **已兑现** | 由 zotero-mcp（第三方 MCP）提供本地读写能力，程序化写入已重启：新增性写入直接执行，破坏性动作须批准（见 G4/G9/INV9/NG5）。原"直至官方提供本地写 API"的前提不再适用。 |
| F3 | ~~challenge-insight tree（挑战-洞见树）~~ **已落地（v0.17.0）** | 与技术路线树同构、复用 `concept` 结构与同一渲染器（一个 doc 一棵树），已并入 INV22。原 `challenge_insight_tree` schema seam 退场（不再做平行异构结构）。触发源:世界模型调研实盘已手搭双树。 |
| F4 | recommend-papers 略读闭环实盘 + watchlist 登记 + doctor 回落 | A3/A4：notebooklm-py 实盘略读、watchlist 半自动登记子模式（authorId 台账 + 项目层配置按 cwd 加载）、doctor 探针 + NotebookLM/Scholar Inbox 回落。tracer(A1) + 四源聚合(A2)已落地，闭环待实盘。 |
| F5 | Scholar Inbox 反馈回流（rate / trending / collect） | feed-agent 的 recommend-papers 已吸收 scholar-agent 的「拉取 + NotebookLM 略读」主链，但缺反馈回流：`rate`/`rate-batch`（点赞驯化推荐口味）、`trending`（跨社区热点，独立于个性化 digest）、`collect`（Scholar Inbox 侧收藏）。vendored `scholar_inbox` 目前只含读取侧（api/auth/config）。补法倾向扩 vendored client + recommend-papers 加「反馈」子模式，不原样引入整个 scholar-agent skill（与 recommend-papers 大面积重复）。参考 jiahao-shao1/sjh-skills 的 scholar-agent。 |

## 维护规则

- 目标/不变量/非目标**变化时更新本文**，但**保持 ID 稳定**；新增项分配新 ID，不复用旧 ID。
- 每条目标应由 `evals/` 的用例守护。`（待补）` 标记尚未有守护 eval 的缺口。
- 目标或范围变化必须同步记入 `CHANGELOG.md`。
- 这是活文档，不归档。原始设计文档已移出仓库（`archived/scholar-workflow/project_references/`），仅作历史快照留存。
- **zotero-mcp 转向的下游同步（✅ 已完成对齐）**：全部 4 个顶层 references（security / storage / identity / source）、全部 5 个 SKILL.md、全部 5 个 agents、`evals/safety.json`（`no-zotero-write` 删除 → `no-unapproved-destructive-zotero` + `no-create-without-existence-check`；`no-existence-on-unreachable` 语义迁至 MCP；删除守护已删机制的 `no-unapproved-apply` / `plan-invalidated-on-change`）均已按 zotero-mcp 新模型重写；代码层退场项（`adapters/zotero_local.py`、`workflows/sync.py`、`dedup`、CLI 的 `sync`/`locate`/`resolve`/`catalog`）已删除。
- **审批原则变更（本轮）**：写入审批从"每次写入须批准"改为"新增性写入直接执行、仅破坏性动作须批准"（G4/G9/INV9/NG5），并同步至 `~/.claude/CLAUDE.md` 与 `references/security-policy.md`。
- **INV16 doctor 分层脚注**：doctor 的 Python 探针查两样——本地路径 + `type:http` MCP 端点的 **TCP/HTTP 层可达性**（advisory、不影响退出码，因端点未就绪是高频暂态、非环境损坏）；但 **MCP 语义可达性（工具是否注册）** 仍由宿主 LLM 在 skill 层核验（CLI 子进程够不到 MCP 工具）。字面"doctor 必检其可达性"应理解为分三层：CLI 查路径 + CLI 探端点 TCP/HTTP 层 + SKILL 查 MCP 工具注册。缘由：HTTP-MCP 只在会话启动瞬间注册、端点未起则整会话静默无工具且不自愈；端点探针把"工具神秘消失"变成明确报错 + "重启会话"指引（v0.18.0，见 `security-policy.md` zotero-mcp boundary）。
- **规划文档迁入 `planning/`（本轮）**：`GOALS.md`、`HANDOFF.md` 及 per-phase 规格从仓库根迁入永久、不归档的 `planning/`（区别于将被归档的 `dev-guide/`）。AGENT.md 文档边界表已加 planning 层。历史 CHANGELOG 行不追改。
- **INV17/INV18（Phase 2）**：新增本机 loopback PDF link-service（附件-key glob storage、inline 流原始 PDF、URL 只存不透明 key）与 sync-projections 的规划/执行分离（LLM↔CLI 只经 JSON、CLI 不碰 MCP）。决策记录 DR-1 见 `planning/phase2-sync-projections.md`。
- **INV20（Phase 2，曳光弹验证）**：论文相关资料文档（`<论文名>论文相关资料.md`）经受管块之外的小节挂到索引表，聚合周边资料链接、不重复元数据。已用 `上汽标注/text2cad.md` + `Text2CAD论文相关资料.md` 端到端验证：块外小节在重投影后存活（INV4 保护）。
- **INV17 修订（Notion 本地 URL 双链）**：Notion PDF 链接从「只用 Web Source、不用 loopback」改为「`Web Source`（arXiv/DOI，跨机）+ `Local URL`（loopback，本机秒开标注版）双链共存」。缘由：本机为主场景下 loopback 在本机 Notion 可用且更快，跨机回落 Web Source。已用 text2cad 8 篇实盘回填 `Local URL` 验证。
- **版本 bump 规则放宽（AGENT.md）**：从「每次 skill change 都 bump」改为「按连贯能力批次 bump，0.x 期批次内迭代不单独 bump」。缘由：`0.6→0.7→0.8` 同日三连跳暴露了按 commit bump 的过细粒度。本轮 Notion 双库实盘定为 `0.8.1`（Phase 2 改进，非发布级 minor）。
- **INV19 改写 + INV21 新增（Notion 双库）**：INV19 原「笔记正文渲染为 Notion 原生 page blocks（全文投影）」改为「只投影一段话摘要 + Vault 回跳，正文留 Obsidian」——Notion 定位为简化跨设备前端，不重复本地内容。INV21 确立双库模型（Papers 键 `Resource ID` + Related Docs 键 `Doc ID`，relation 连接，先论文后文档）。代码层：`adapters/notion.py` 的 `upsert_page` 增 `key_property` 参（默认 `Resource ID` 不变）、`config.py` 加 `related_docs_{database,data_source}_id`、契约测试 3→5、`notion-schema.md` 单库→双库。Notion 仍未接线上（无 CLI 命令、config 无 notion 块），属库层就绪，接线上/建真实库/换新 token 为后续 ticket。
- **INV22 新增 + citation-graph 退场（Phase 3, v0.10.0）**：文献树模型由 Phase-0 随手搭的 citation-graph（论文↔论文有向图 + 6 种关系边 + evidence/confidence/review_status）替换为彭思达 literature-tree 法的 **novelty tree**（`task → pipeline → 论文` 三级、概念为内部节点、论文为叶、每概念记 novelty 锚点 + flat paper-list）。缘由：调研彭思达 GAMES003 Notion「literature tree」一手定义确认其树按 novelty 分层归类、非按引用连边；原 citation-graph 从未被 INV 背书、`workflows/lineage.py` 是空 stub，无沉没成本。代码层：`literature-graph.schema.json`→`literature-tree.schema.json`、新 `workflows/novelty_tree.py`（复用 `render_table`/`ObsidianAdapter`）、`project-literature-tree` CLI、删 `edge-evidence.md` + 死 stub、SKILL/agent/README 改写。NG7 澄清：novelty 锚点是可核实先后事实、不受反浮夸约束。challenge-insight tree 留 schema seam、押后作 F 系列 future 项。渲染限 Obsidian 受管块 + 内联 Mermaid（本轮不投 PNG/draw.io/HTML/Notion）。
- **INV23/INV24 新增 + 两级 AI 阅读（Phase 5, feature-ai-reading, v0.11.0）**：新增两个 skill——`recommend-papers`@intake（略读级）+ `analyze-paper`@knowledge（详细分析级）。略读级(INV23)四源聚合(S2 Recommendations / Scholar Inbox / S2 author watchlist / HF Daily)按 arXiv id 合并去重、仅 shortlist 走 NotebookLM 略读、产物临时不落 vault；详细分析级(INV24)经 zotero-mcp `get_content` 读正文落 Obsidian 附属笔记、与批注笔记分立 `related` 互链、局部分析块外多小节追加、挂 INV20 枢纽。代码层：新 `adapters/recommend_sources.py`（HF Daily + S2 recommendations/author + Scholar Inbox 规范化，四源 emit 统一候选、按 arxiv_id 合并）、`config.py` 加 `RecommendConfig` + `load_recommend_config`（两层 recommend.yml，interests/watchlist 追加）、`bin/recommend-papers.py`（唯一网络出口，CLI 零外部网络承 INV18）、vendor sjh `scholar_inbox` 客户端（api/auth/config，MIT 标归属 + THIRD_PARTY_LICENSES）。设计哲学：只编码外来规定（源/落点/格式/网络路径/依赖），不编码内在能力（读/摘/比较/归类）。build-literature-tree 加「批量读料优先经 NotebookLM」编排提示（优化约束、复用略读引擎）。skill 数 7→9（find/ingest/sync/build-tree/check/export/env-setup + recommend-papers + analyze-paper）。剩：略读闭环实盘、watchlist 登记、doctor 回落（记 F4）。
- **survey-topic 编排入口（v0.14.0）**：新增 `survey-topic`@intake（skill 数 9→10），补上「宽泛调研开口无 skill 响应」的缺口——此前"调研世界模型"不触发任何 skill，因九个 skill 全按具体机械动词匹配。定位是**跨 phase 编排入口**：grill 钉死程度/范围/时间窗 → 提有序计划 → 委派给 recommend/find/ingest/build-tree/analyze，**自己不做调研、不落文件、不产物**。设计哲学落点：唯一编码的外来规定是 **depth→skill 映射表**（哪个 skill 服务哪个调研子目标，模型推导不出）；「怎么调研」是内在能力、不编码。边界：**build-literature-tree 保持独立**——"画树"直达它，survey-topic 只是其上游调用者之一，路由过去时交出 scope、让树跑自己的 gate（承 INV22）。不新增 INV：它整体是优化脚手架（模型变强会自己 scope+编排、会贬值），由 `evals/routing.json` 两用例（正向开放式调研 + 负向"画树"动词绕过）+ intake-agent 映射守护即可。借 Matt Pocock writing-great-skills 语汇成文（薄壳编排 + 委派、leading word=survey）。名字 `survey-topic` 为落地初选，无引用绑定、改名成本低。
- **文献树渲染形态重构（Phase 3, v0.15.0）**：按真实世界模型 vault 实践重塑 novelty tree 的落地形态（INV22 渲染子句扩写）。七点外来规定:①主题文件夹以主题命名、无 `-literature-tree` 外壳;②`01-Paperlist.md` 固定为独立扁平全集账本、与树分离(互链);③多棵树/视图可共存,树内论文子集叫 subpaperlist;④索引文件用图书馆编码前缀(01 固定,携带索引/表/Mermaid 的文件才编号 02/03…,skill 分配、CLI 只固定 01 槽);⑤一棵树=一个自包含笔记(内联 Mermaid + 嵌套 `##`任务/`###`pipeline + `内容简介`/`论文列表`),**无 H1**、不重复标题;⑥DOI 留 schema 字段(判重身份)但删表格列,每篇论文加 `paper_assets/<年>-<第一作者>-<标题>.md` 相关资料笔记、每个 `#` 一种资源类型、必含 `# 相关文献树` 小节反链回树的 pipeline 位置(承 INV20 枢纽);⑦Importance 三级文本 `founding`/`milestone`/`representative` + 星级徽章。代码层:schema 加 `summary`(概念内容简介,存 JSON 保幂等)+ `asset_note`(论文资料笔记路径);共享渲染器 `projection.py` 删 DOI 列、Importance 追加星级、Assets 列 opt-in(`assets=True`)——**连带 sync-projections 的 Zotero 镜像也从 10 列变 9 列**(故意共享,一致性);`novelty_tree.py` 由多文件层级重写为单文件分节(`render_tree_note` + `render_paperlist` + `plan/project_*`),`ObsidianAdapter.ensure_managed_block` 支持空 heading(无 H1);`project-literature-tree` CLI 入参加 `filename` + `paperlist_only`,`root` 默认主题名。设计哲学落点:只编码外来规定(布局/编码/形态/字段),不编码内在能力(判归属/写简介/组 Mermaid)。NG7 澄清不变(novelty 锚点是可核实先后事实、非突破徽章)。
- **survey-topic 冷启动广度侦察(v0.15.1)**:真实调研实践暴露一个缺口——冷启动时往往没法盲目界定深浅,得先跑一次快速的 web-inclusive 广度侦察(含非 arXiv 源:无论文的模型、benchmark/项目页、实验室博客)摸出领域轮廓,grill 才有对照可 scope。落地为 survey-topic 三处 prose(身份句不再声称"runs no retrieval"、Grill 段加 Cold-start orientation 小节、Constraints 加"Orientation reads; acquisition is delegated"把获取的 what/where/source 交回 source-policy + ingest-resource 而不复述 arXiv-only)。**Depth→skill 映射表不动**(每行都路由到下游 skill,而侦察不路由到任何 skill、是定向阶段的内部读取)。**并行 fan-out 的机制不编码**(内在能力,承设计哲学)。侦察产物丢弃式(类 recommend-papers 的 Reading Report,INV23),不落 vault、不进库。不新增 INV(优化脚手架、非业务约束);routing.json 不加(侦察是内部模式、非新路由目标)。获取策略经用户澄清定为"仅元数据回落"(无 arXiv 版时只登记元数据+标记,PDF 不自动从他源下),等同现状(NG1),source-policy 不改。
- **文献树模型广义扩展 + 挑战树落地 + INV25(Phase 3, v0.17.0)**:世界模型调研实盘(`0-inbox/世界模型调研经验_20260804.md`,一次真实端到端反馈)驱动的三处扩展。**① novelty 三类→四类**:概念深度轴与论文角色轴分离——1/2/3 类是**概念节点首创**(task/pipeline/**module** 各一级,用现有 `novelty_anchor` 表达,仅新增 module 这一 kind),4 类是**论文级"改进"属性**(用 module 改进已有 pipeline、语境相关),作普通成员挂被改进节点下、**零 schema 字段**(4 类是判断、不编码进数据,承设计哲学"不给无消费者的属性建字段")。**② 拓扑变深度**:加可选 module 第四层,`topic→task→pipeline→module→论文`。**③ 挑战洞见树落地**(F3 兑现):`challenge→insight→论文` 与技术树**同构**,复用同一 `concept` 结构与渲染器、一个 doc 一棵树;原 `challenge_insight_tree` schema seam 退场(不做平行异构结构)。代码层:`concept.kind` 枚举平铺扩举加 `module/challenge/insight`;`render_mermaid` 由硬编码三层(`_emit_task`/`_emit_pipeline` 不递归)重写为**单个递归 `_emit_concept`**——修了 module/insight 及其论文被 Mermaid 图**静默丢弃**的真 bug(文本分节本就递归、图没跟上);`_KIND_DEPTH`(task/challenge=2、pipeline/insight=3、module=4)、`_ANCHOR_LABEL`、classDef 配色各加表项;schema/plan/project/render_table 无结构改动。新增 **INV25 一文多树**:论文↔树多对多(同 resource_id 可跨多节点/多树/含技术树+挑战树)、`paper_assets` 附属按主题文件夹分身、`01-Paperlist.md` 按 topic 隔离、绝不加唯一性检查——实盘双树共享全集(§2.4)直接印证。设计哲学落点:只编码外来规定(四类定义/拓扑/同构/一文多树),不编码内在能力(判归属/首提判断)。NG7 澄清扩到含 module 首创。测试 109→115(novelty_tree 加 module 递归/挑战树同构/一文多树用例,契约 seam 测试替换为 module-depth + challenge-reuse + 退场 seam 拒绝)。实盘打包缺陷(shim/venv 版本漂移/doctor 探针)属独立线,本轮不做。
- **Agent 拓扑重构:按机械动词切 → 按任务级自足单元切(v0.16.0)**:五个 `agents/*.md` 原先①无 YAML frontmatter,Claude Code 从不注册为可委派 subagent,是影子文档;②按机械动作切(发现/入库/投影/建树/审计),而真实任务跨多动作,故每个 agent 是够不着任务的碎片(典型症状:lineage 硬塞一个"只读"find-resource,因为从零建树本就内含搜索)。重切原则:**agent 按「会独立吃大量上下文的用户任务」划分,每个自足拥有完成该任务的全部 skill,skill 可跨 agent 复用、不归属单一 agent**。落地:intake(find+ingest,吸收并删除 library)/ lineage(find+ingest+build-tree,由"只建树"扩为方向级调研)/ **feed**(recommend-papers,新增,从 intake 拆出每日 push 流)/ knowledge(analyze+export+sync,不变)/ audit(check-consistency,不变);全部补 `name`+`description` frontmatter。**Agent 之间不 handoff**——跨 agent 串联由宿主 LLM 或 survey-topic(顶层编排 skill、不挂 agent)编排。连带:①删死链路 `workflows/audit.py` + `cli.py audit`(够不到 MCP 的 stub,check-consistency 实为 skill 层 LLM 执行,stub 曾误导审查报告判其"未实现");②运行期文件清除私有人名归属(彭思达/GAMES003,无路由价值、随 release ship,方法本身不动,出处留 dev 层);③`handoff.schema.json` 正名 `AgentHandoff`→`PreCompactSnapshot`(from/to_agent 硬编码 precompact、唯一生产者是 PreCompact hook,从非 agent 交接;死字段留、契约测试不动)。设计哲学落点:agent 拓扑是优化脚手架(不新增 INV);跨 agent 复用 skill 是特性非 bug。scholar-agent 的反馈回流(rate/trending/collect)记 F5 待办、本轮不做。触发源:codex-review.md 外部审查(P0 frontmatter 阻断 + 影子 agent 层)+ 用户对 lineage 边界的质疑。

