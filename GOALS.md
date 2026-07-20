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
| G3 | 论文 PDF 的自动获取源头只能是 arXiv；下载后落入收件箱待人工导入，其他来源仅用于身份与元数据核验 |
| G4 | 论文的自动下载必须先形成计划并获得用户批准；Zotero 导入由人工完成，不做程序化外部写入 |
| G5 | Zotero、Obsidian Vault、Notion 各司其职，不互相复制主数据 |
| G6 | 大型目录采用分层索引：先读索引，再按需读实体文件 |
| G7 | 插件由 Git 管理，功能必须有评测和回归测试 |
| G8 | 首要宿主是 Claude Code；未来可通过确定性 CLI 或 codex 复用底层能力 |
| G9 | Zotero（及其 PDF 存储）是唯一权威主库；元数据与存在性经 Zotero Local API 只读获取。Zotero 无本地写 API，论文导入暂由人工完成 |

## 长期不变量（INV）

任何实现、任何阶段都必须成立。违反即为回归。

| ID | 不变量 | 守护 eval |
|---|---|---|
| INV1 | 一篇论文在 Zotero 中对应唯一条目（item）；条目可隶属多个分类（collection），分类是对条目的多对一投影，不构成重复身份。按 DOI / arXiv 基础 id 精确判重防止重复新建；模糊命中只提候选、写路径转冲突交人工裁决（NG3） | outcomes: dedup-exact-collapse |
| INV2 | `papers_root` 只放论文 PDF；技术文档即使是 PDF 也进 Vault | routing: file-technical-doc / outcomes: tech-doc-isolation |
| INV3 | PDF 位置迁移只通过配置 + Zotero 附件关系，不在多目录复制 | outcomes: papers-root-remap |
| INV4 | Obsidian 论文表是可重建的派生索引，不是主库 | outcomes: obsidian-human-block-preserved |
| INV5 | Notion 不上传论文/技术文档/图片/数据文件 | safety: no-notion-file-upload |
| INV6 | Notion 机器字段可更新；人工内容不得被同步覆盖 | safety: no-overwrite-human-block |
| INV7 | 状态库只存映射/游标/任务状态/审计，不存知识正文 | （待补） |
| INV8 | 外部程序不得直接写 `zotero.sqlite` | safety: no-sqlite-write |
| INV9 | 插件不对 Zotero 做任何程序化写入；Local API 仅用于只读查询 | safety: no-zotero-write |
| INV10 | 元数据（标题/作者/年份）以 Zotero Local API 为权威来源，不从 arXiv 解析 | （待补） |
| INV11 | 下载的论文 PDF 只落入 `paper_inbox`，不代替人工写入 Zotero 库或复制到多目录 | （待补） |
| INV12 | 存在性判定以 Zotero Local API 为权威、实时查询；Zotero 不可达时失败关闭（退出码 3），绝不因"查不到"判为新建 | safety: no-existence-on-unreachable |
| INV13 | 本地 `resources` 缓存是 Zotero 的派生只读镜像，仅经 Local API 单向同步（用户触发），不反向影响 Zotero | （待补） |
| INV14 | 模糊/语义召回由宿主 LLM 读目录投影（标题+摘要）完成，不生成 embedding、不建向量索引 | （待补） |
| INV15 | 离线解析器对标识符输入不造占位标题（`title` 为 null）；显示用真名由展示层可选补齐（EXACT 读 catalog、NONE 用对话/抓取），绝不作为判定输入。契约自描述，能力缺失时降级为显示 identifier | resolver: title-null-for-identifier |

## 非目标（NG）

明确不做的事，防止范围蔓延。

| ID | 非目标 | 守护 eval |
|---|---|---|
| NG1 | 从出版社/网盘/搜索引擎/非 arXiv 站点自动下载论文 PDF | safety: no-nonaxiv-pdf / outcomes: no-nonarxiv-autodownload |
| NG2 | 绕过付费墙、验证码、登录或访问控制 | （待补） |
| NG3 | 自动删除、覆盖或合并身份冲突的 Zotero 条目 | outcomes: identity-conflict-stop |
| NG4 | 直接写 Zotero SQLite | safety: no-sqlite-write |
| NG5 | 对 Zotero 做任何程序化写入（导入由人工完成，直至官方提供本地写 API） | safety: no-zotero-write |
| NG6 | 把论文全文或技术文件上传到 Notion | safety: no-notion-file-upload |
| NG7 | 无证据自动宣布"里程碑"或"突破性工作" | （待补） |
| NG8 | 第一阶段自动下载书籍/标准/数据集文件（先只做元数据和索引） | （待补） |

## 阶段状态（随开发更新）

| 阶段 | 目标 | 状态 |
|---|---|---|
| Phase 0 | 插件骨架、契约、evals 基线、开发规范 | ✅ 完成 |
| Phase 1 | 论文发现 + 下载到收件箱（find-resource / ingest-resource 真实可用；Zotero 导入人工） | 🚧 进行中（resolver / dedup / locate / 下载到 inbox 已落地） |
| Phase 2 | 投影同步（Obsidian 索引 + Notion） | ⏳ 未开始 |
| Phase 3 | 文献脉络树 | ⏳ 未开始 |
| Phase 4 | 一致性审计 | ⏳ 未开始 |

## 未来项（记录待办，暂不实现）

| ID | 事项 | 说明 |
|---|---|---|
| F1 | 给文章标题加入重要程度批注 | 在展示/索引论文标题时附一个推荐重要程度的批注，辅助人工判断优先级。待 Zotero 元数据读取链路稳定后再设计。 |
| F2 | Zotero 官方本地写 API 落地后重启程序化写入 | 一旦官方提供可靠本地写能力，重新评估自动导入，替换当前人工导入流程（对应 G9/NG5）。 |

## 维护规则

- 目标/不变量/非目标**变化时更新本文**，但**保持 ID 稳定**；新增项分配新 ID，不复用旧 ID。
- 每条目标应由 `evals/` 的用例守护。`（待补）` 标记尚未有守护 eval 的缺口。
- 目标或范围变化必须同步记入 `CHANGELOG.md`。
- 这是活文档，不归档。原始设计文档已移出仓库（`archived/scholar-workflow/project_references/`），仅作历史快照留存。

