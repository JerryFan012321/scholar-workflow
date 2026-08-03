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
| INV20 | **论文相关资料文档(Obsidian 枢纽)**:每篇论文可按需在**索引表同目录**挂一个相关资料文档(`<论文名>论文相关资料.md`),聚合该论文的**周边资料位置链接**(阅读笔记/方向笔记/补充材料),**不重复论文元数据**(元数据属 Zotero+索引行)。索引表经**受管块之外**的「相关资料」小节链接到它——块外由 INV4 保护、重投影不覆盖,故无需给 10 列表格加列 | （待补） |
| INV22 | **文献树为 novelty tree**(彭思达 literature-tree 法):三级分类拓扑 `里程碑任务 → pipeline/representation → 论文(叶)`,内部节点是**抽象概念**、论文是**叶**(按 `resource_id` 引用);每个概念节点记 **novelty 锚点**=首个提出该 task/pipeline 的论文(1/2/3 类)。树旁**并存一份 flat 全集 paper list**(单一元数据账本,论文可在册但 `classified:false` 未分类)。本轮渲染目标限 **Obsidian 受管块 + 内联 Mermaid**(不产 PNG/draw.io/HTML/Notion),块外内容幂等存活(复用 INV4/INV18 机制)。配套 challenge-insight tree 留 schema seam、押后 | outcomes: novelty-tree-topology-and-paperlist |
| INV23 | **略读级(recommend-papers)临时性**:略读经外部服务(四推荐源 REST + NotebookLM)进行,四源(S2 Recommendations / Scholar Inbox / S2 author watchlist / HF Daily)按 arXiv id 合并去重,仅对用户细化后的 shortlist 走 NotebookLM 略读(省 token,不略读全池);产物为**临时 Reading Report,绝不落 vault、不改 Zotero**;看中的论文经 find/ingest 正式管线入库(判重两步核验)。CLI 不碰这些网络/MCP(承 INV18),聚合在 `bin/recommend-papers.py` | （待补） |
| INV24 | **详细分析级(analyze-paper)源与落点**:详细分析只经 zotero-mcp `get_content` 读正文(承 INV10 不解析 PDF 本体),产物落 Obsidian 附属分析笔记(`<论文名>分析.md`),与人工批注笔记**分立**、`related` 互链;局部分析在同一笔记**受管块之外多小节追加**(承 INV4 保护),并挂到该论文相关资料枢纽(INV20) | （待补） |

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
| NG7 | 无证据自动宣布某论文是"突破性工作"（反浮夸）。注意与 INV22 的 novelty 锚点区分:锚点是"首个提出该 task/pipeline"的**可核实先后事实**、非价值判断,不受本条约束;本条禁的是给论文贴超出锚点定义的"突破"徽章 | （待补） |
| NG8 | 第一阶段自动下载书籍/标准/数据集文件（先只做元数据和索引） | （待补） |

## 阶段状态（随开发更新）

| 阶段 | 目标 | 状态 |
|---|---|---|
| Phase 0 | 插件骨架、契约、evals 基线、开发规范 | ✅ 完成 |
| Phase 1 | 论文发现 + 下载到收件箱 + 经 zotero-mcp 入库（find-resource / ingest-resource 真实可用；存在性/语义/写入经 zotero-mcp） | 🚧 进行中（resolver / 下载到 inbox 已落地；CLI 的 sync/locate/resolve/catalog 退场；存在性/写入迁移至 MCP；skill/reference/agent/evals 已按 zotero-mcp 重写并对齐；实战已完成 create/import/补元数据/加入分类闭环） |
| Phase 2 | 投影同步（Obsidian 索引 + 本机 PDF 链接服务 + Notion 双库投影） | 🚧 进行中（Obsidian 层级投影 + loopback PDF link-service + launchd 自启已落真机 vault；**Notion 双库(Papers + Related Docs)已 v0.8.1 实盘上线并固化进 skill 层**——机械层 `bin/notion-project.py`(唯一 Notion API 出口，CLI 零外部网络)+ 展示层 SKILL.md 组装专题页；已用 text2cad 8 篇端到端验证。剩：方向级笔记(无 Zotero item)的 Notion 表示，INV21 显式押后作后续 ticket） |
| Phase 3 | 文献脉络树 | 🚧 进行中（novelty tree 模型 v0.10.0 落库：`literature-tree.schema.json`(paper_list + 三级概念树 + challenge-insight seam)、`workflows/novelty_tree.py`(render_mermaid + plan/project，复用 render_table/ObsidianAdapter)、`project-literature-tree` CLI(带 --dry-run)、SKILL/agent/docs 从 citation-graph 改写为 novelty tree、INV22 + outcomes 守护。剩：真实主题端到端实盘、challenge-insight tree 后续 ticket） |
| Phase 4 | 一致性审计 | ⏳ 未开始 |
| Phase 5 | 两级 AI 阅读（略读推荐 + 详细分析） | 🚧 进行中（recommend-papers：四源聚合适配器 + HF Daily 单源贯通 + vendor Scholar Inbox 客户端 + 两层 recommend.yml + SKILL/README 已落地，INV23；analyze-paper：SKILL/README 已落地，INV24；build-literature-tree 加 NotebookLM 批读编排提示。剩：notebooklm-py 实盘略读闭环、watchlist 半自动登记子模式、doctor 探针 + 回落、B1/B2 端到端实跑） |

## 未来项（记录待办，暂不实现）

| ID | 事项 | 说明 |
|---|---|---|
| F1 | 给文章标题加入重要程度批注 | 在展示/索引论文标题时附一个推荐重要程度的批注，辅助人工判断优先级。待 Zotero 元数据读取链路稳定后再设计。 |
| F2 | ~~Zotero 官方本地写 API 落地后重启程序化写入~~ **已兑现** | 由 zotero-mcp（第三方 MCP）提供本地读写能力，程序化写入已重启：新增性写入直接执行，破坏性动作须批准（见 G4/G9/INV9/NG5）。原"直至官方提供本地写 API"的前提不再适用。 |
| F3 | challenge-insight tree（挑战-洞见树） | 与 novelty tree 配套的第二棵树，schema 已留 `challenge_insight_tree` seam（Phase 3）。押后到独立 ticket 设计。 |
| F4 | recommend-papers 略读闭环实盘 + watchlist 登记 + doctor 回落 | A3/A4：notebooklm-py 实盘略读、watchlist 半自动登记子模式（authorId 台账 + 项目层配置按 cwd 加载）、doctor 探针 + NotebookLM/Scholar Inbox 回落。tracer(A1) + 四源聚合(A2)已落地，闭环待实盘。 |

## 维护规则

- 目标/不变量/非目标**变化时更新本文**，但**保持 ID 稳定**；新增项分配新 ID，不复用旧 ID。
- 每条目标应由 `evals/` 的用例守护。`（待补）` 标记尚未有守护 eval 的缺口。
- 目标或范围变化必须同步记入 `CHANGELOG.md`。
- 这是活文档，不归档。原始设计文档已移出仓库（`archived/scholar-workflow/project_references/`），仅作历史快照留存。
- **zotero-mcp 转向的下游同步（✅ 已完成对齐）**：全部 4 个顶层 references（security / storage / identity / source）、全部 5 个 SKILL.md、全部 5 个 agents、`evals/safety.json`（`no-zotero-write` 删除 → `no-unapproved-destructive-zotero` + `no-create-without-existence-check`；`no-existence-on-unreachable` 语义迁至 MCP；删除守护已删机制的 `no-unapproved-apply` / `plan-invalidated-on-change`）均已按 zotero-mcp 新模型重写；代码层退场项（`adapters/zotero_local.py`、`workflows/sync.py`、`dedup`、CLI 的 `sync`/`locate`/`resolve`/`catalog`）已删除。
- **审批原则变更（本轮）**：写入审批从"每次写入须批准"改为"新增性写入直接执行、仅破坏性动作须批准"（G4/G9/INV9/NG5），并同步至 `~/.claude/CLAUDE.md` 与 `references/security-policy.md`。
- **INV16 doctor 分层脚注**：doctor 的 Python 探针只查本地路径；zotero-mcp 可达性由宿主 LLM 在 skill 层核验（CLI 子进程够不到 MCP）。字面"doctor 必检其可达性"应理解为分两层：CLI 查路径 + SKILL 查 MCP。
- **规划文档迁入 `planning/`（本轮）**：`GOALS.md`、`HANDOFF.md` 及 per-phase 规格从仓库根迁入永久、不归档的 `planning/`（区别于将被归档的 `dev-guide/`）。AGENT.md 文档边界表已加 planning 层。历史 CHANGELOG 行不追改。
- **INV17/INV18（Phase 2）**：新增本机 loopback PDF link-service（附件-key glob storage、inline 流原始 PDF、URL 只存不透明 key）与 sync-projections 的规划/执行分离（LLM↔CLI 只经 JSON、CLI 不碰 MCP）。决策记录 DR-1 见 `planning/phase2-sync-projections.md`。
- **INV20（Phase 2，曳光弹验证）**：论文相关资料文档（`<论文名>论文相关资料.md`）经受管块之外的小节挂到索引表，聚合周边资料链接、不重复元数据。已用 `上汽标注/text2cad.md` + `Text2CAD论文相关资料.md` 端到端验证：块外小节在重投影后存活（INV4 保护）。
- **INV17 修订（Notion 本地 URL 双链）**：Notion PDF 链接从「只用 Web Source、不用 loopback」改为「`Web Source`（arXiv/DOI，跨机）+ `Local URL`（loopback，本机秒开标注版）双链共存」。缘由：本机为主场景下 loopback 在本机 Notion 可用且更快，跨机回落 Web Source。已用 text2cad 8 篇实盘回填 `Local URL` 验证。
- **版本 bump 规则放宽（AGENT.md）**：从「每次 skill change 都 bump」改为「按连贯能力批次 bump，0.x 期批次内迭代不单独 bump」。缘由：`0.6→0.7→0.8` 同日三连跳暴露了按 commit bump 的过细粒度。本轮 Notion 双库实盘定为 `0.8.1`（Phase 2 改进，非发布级 minor）。
- **INV19 改写 + INV21 新增（Notion 双库）**：INV19 原「笔记正文渲染为 Notion 原生 page blocks（全文投影）」改为「只投影一段话摘要 + Vault 回跳，正文留 Obsidian」——Notion 定位为简化跨设备前端，不重复本地内容。INV21 确立双库模型（Papers 键 `Resource ID` + Related Docs 键 `Doc ID`，relation 连接，先论文后文档）。代码层：`adapters/notion.py` 的 `upsert_page` 增 `key_property` 参（默认 `Resource ID` 不变）、`config.py` 加 `related_docs_{database,data_source}_id`、契约测试 3→5、`notion-schema.md` 单库→双库。Notion 仍未接线上（无 CLI 命令、config 无 notion 块），属库层就绪，接线上/建真实库/换新 token 为后续 ticket。
- **INV22 新增 + citation-graph 退场（Phase 3, v0.10.0）**：文献树模型由 Phase-0 随手搭的 citation-graph（论文↔论文有向图 + 6 种关系边 + evidence/confidence/review_status）替换为彭思达 literature-tree 法的 **novelty tree**（`task → pipeline → 论文` 三级、概念为内部节点、论文为叶、每概念记 novelty 锚点 + flat paper-list）。缘由：调研彭思达 GAMES003 Notion「literature tree」一手定义确认其树按 novelty 分层归类、非按引用连边；原 citation-graph 从未被 INV 背书、`workflows/lineage.py` 是空 stub，无沉没成本。代码层：`literature-graph.schema.json`→`literature-tree.schema.json`、新 `workflows/novelty_tree.py`（复用 `render_table`/`ObsidianAdapter`）、`project-literature-tree` CLI、删 `edge-evidence.md` + 死 stub、SKILL/agent/README 改写。NG7 澄清：novelty 锚点是可核实先后事实、不受反浮夸约束。challenge-insight tree 留 schema seam、押后作 F 系列 future 项。渲染限 Obsidian 受管块 + 内联 Mermaid（本轮不投 PNG/draw.io/HTML/Notion）。
- **INV23/INV24 新增 + 两级 AI 阅读（Phase 5, feature-ai-reading, v0.11.0）**：新增两个 skill——`recommend-papers`@intake（略读级）+ `analyze-paper`@knowledge（详细分析级）。略读级(INV23)四源聚合(S2 Recommendations / Scholar Inbox / S2 author watchlist / HF Daily)按 arXiv id 合并去重、仅 shortlist 走 NotebookLM 略读、产物临时不落 vault；详细分析级(INV24)经 zotero-mcp `get_content` 读正文落 Obsidian 附属笔记、与批注笔记分立 `related` 互链、局部分析块外多小节追加、挂 INV20 枢纽。代码层：新 `adapters/recommend_sources.py`（HF Daily + S2 recommendations/author + Scholar Inbox 规范化，四源 emit 统一候选、按 arxiv_id 合并）、`config.py` 加 `RecommendConfig` + `load_recommend_config`（两层 recommend.yml，interests/watchlist 追加）、`bin/recommend-papers.py`（唯一网络出口，CLI 零外部网络承 INV18）、vendor sjh `scholar_inbox` 客户端（api/auth/config，MIT 标归属 + THIRD_PARTY_LICENSES）。设计哲学：只编码外来规定（源/落点/格式/网络路径/依赖），不编码内在能力（读/摘/比较/归类）。build-literature-tree 加「批量读料优先经 NotebookLM」编排提示（优化约束、复用略读引擎）。skill 数 7→9（find/ingest/sync/build-tree/check/export/env-setup + recommend-papers + analyze-paper）。剩：略读闭环实盘、watchlist 登记、doctor 回落（记 F4）。
- **survey-topic 编排入口（v0.14.0）**：新增 `survey-topic`@intake（skill 数 9→10），补上「宽泛调研开口无 skill 响应」的缺口——此前"调研世界模型"不触发任何 skill，因九个 skill 全按具体机械动词匹配。定位是**跨 phase 编排入口**：grill 钉死程度/范围/时间窗 → 提有序计划 → 委派给 recommend/find/ingest/build-tree/analyze，**自己不做调研、不落文件、不产物**。设计哲学落点：唯一编码的外来规定是 **depth→skill 映射表**（哪个 skill 服务哪个调研子目标，模型推导不出）；「怎么调研」是内在能力、不编码。边界：**build-literature-tree 保持独立**——"画树"直达它，survey-topic 只是其上游调用者之一，路由过去时交出 scope、让树跑自己的 gate（承 INV22）。不新增 INV：它整体是优化脚手架（模型变强会自己 scope+编排、会贬值），由 `evals/routing.json` 两用例（正向开放式调研 + 负向"画树"动词绕过）+ intake-agent 映射守护即可。借 Matt Pocock writing-great-skills 语汇成文（薄壳编排 + 委派、leading word=survey）。名字 `survey-topic` 为落地初选，无引用绑定、改名成本低。

