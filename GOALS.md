# Scholar Workflow — 目标（活文档）

> 这是项目的 north star，持续更新。它高于 `project_references/DESIGN.md` 的实现层。
> 开发一旦展开，DESIGN.md 的架构图/目录布局即为历史快照，不再维护；本文的目标与
> 不变量才是权威对照基准。每条目标带稳定 ID，`evals/` 用 ID 回指来守护它。
>
> 权威关系：目标（本文） → 守护（evals/） → 实现（代码）。
> 校验一条目标是否达成，看它的 eval，而不是看设计文档。

## 上位目标（G）

意图层，不因实现方式改变。改动须谨慎并记入 CHANGELOG。

| ID | 目标 |
|---|---|
| G1 | 管理论文、书籍、技术文档及相关数据；第一阶段优先论文与技术文档 |
| G2 | 每个对象只有一个主存储位置，其他系统只保存索引、投影或管理信息 |
| G3 | 论文 PDF 的自动获取与传递源头只能是 arXiv；其他来源仅用于身份与元数据核验 |
| G4 | 所有外部写入必须先形成计划并获得用户批准 |
| G5 | Zotero、Obsidian Vault、Notion 各司其职，不互相复制主数据 |
| G6 | 大型目录采用分层索引：先读索引，再按需读实体文件 |
| G7 | 插件由 Git 管理，功能必须有评测和回归测试 |
| G8 | 首要宿主是 Claude Code；未来可通过确定性 CLI 或 codex 复用底层能力 |
| G9 | 当前 Zotero 写入必须经自研 Bridge 在 Zotero 进程内完成；仅在官方 Local API 通过完整写能力验证后才允许切换 |

## 长期不变量（INV）

任何实现、任何阶段都必须成立。违反即为回归。

| ID | 不变量 | 守护 eval |
|---|---|---|
| INV1 | 一篇论文最多一个 Zotero 父条目 + 一个主 PDF 附件 | outcomes: zotero-upsert-not-duplicate |
| INV2 | `papers_root` 只放论文 PDF；技术文档即使是 PDF 也进 Vault | routing: file-technical-doc / outcomes: tech-doc-isolation |
| INV3 | PDF 位置迁移只通过配置 + Zotero 附件关系，不在多目录复制 | outcomes: papers-root-remap |
| INV4 | Obsidian 论文表是可重建的派生索引，不是主库 | outcomes: obsidian-human-block-preserved |
| INV5 | Notion 不上传论文/技术文档/图片/数据文件 | safety: no-notion-file-upload |
| INV6 | Notion 机器字段可更新；人工内容不得被同步覆盖 | safety: no-overwrite-human-block |
| INV7 | 状态库只存映射/游标/任务状态/审计，不存知识正文 | （待补） |
| INV8 | 外部程序不得直接写 `zotero.sqlite` | safety: no-sqlite-write |
| INV9 | 当前 Local API 只读；写操作只经自研 Bridge | safety: no-bridge-bypass |
| INV10 | 所有 Zotero 写入经统一 `ZoteroWriteAdapter`；换后端不改业务流程/审批/Contract | （待补） |
| INV11 | 写入后端切换基于能力探测 + 官方文档 + 合同测试，不靠版本号猜测 | （待补） |

## 非目标（NG）

明确不做的事，防止范围蔓延。

| ID | 非目标 | 守护 eval |
|---|---|---|
| NG1 | 从出版社/网盘/搜索引擎/非 arXiv 站点自动下载论文 PDF | safety: no-nonaxiv-pdf / outcomes: no-nonarxiv-autodownload |
| NG2 | 绕过付费墙、验证码、登录或访问控制 | （待补） |
| NG3 | 自动删除、覆盖或合并身份冲突的 Zotero 条目 | outcomes: identity-conflict-stop |
| NG4 | 直接写 Zotero SQLite | safety: no-sqlite-write |
| NG5 | Local API 无写能力时绕过自研插件写入 | safety: no-bridge-bypass |
| NG6 | 把论文全文或技术文件上传到 Notion | safety: no-notion-file-upload |
| NG7 | 无证据自动宣布"里程碑"或"突破性工作" | （待补） |
| NG8 | 第一阶段自动下载书籍/标准/数据集文件（先只做元数据和索引） | （待补） |

## 阶段状态（随开发更新）

| 阶段 | 目标 | 状态 |
|---|---|---|
| Phase 0 | 插件骨架、契约、evals 基线、开发规范 | ✅ 完成 |
| Phase 1 | 论文发现 + 导入（find-resource / ingest-resource 真实可用） | ⏳ 未开始 |
| Phase 2 | 投影同步（Obsidian 索引 + Notion） | ⏳ 未开始 |
| Phase 3 | 文献脉络树 | ⏳ 未开始 |
| Phase 4 | 一致性审计 | ⏳ 未开始 |

## 维护规则

- 目标/不变量/非目标**变化时更新本文**，但**保持 ID 稳定**；新增项分配新 ID，不复用旧 ID。
- 每条目标应由 `evals/` 的用例守护。`（待补）` 标记尚未有守护 eval 的缺口。
- 目标或范围变化必须同步记入 `CHANGELOG.md`。
- 这是活文档，不归档；`project_references/DESIGN.md` 的实现层才是历史快照。

