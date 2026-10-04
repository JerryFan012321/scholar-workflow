# analyze-paper（论文分析）

为一篇已入库论文生成持久化分析，或为用户选定的一批论文分别生成独立分析文档对。每篇论文都
拥有一份可独立阅读的 Obsidian Markdown 正文和一份可编辑 JSON Canvas 投影。

新论文在所属 Field 内使用 `resources/papers/<稳定论文目录段>/` 单篇目录，集中放论文信息笔记、
分析 Markdown、Canvas 和 sidecar；PDF 仍由 Zotero 管理。目录段与资源 ID 的映射须持久记录。
旧平铺文件继续原位读取，普通分析更新不会顺手搬迁。

## 输出模型

当前要求的输出格式在 Markdown 和 Canvas 中采用用户新提供的五分支框架：

1. **Abstract**——Task、既有方法的技术挑战、关键洞见/动机、技术贡献、Experiment。
2. **Introduction**——任务与应用、既有方法挑战、Our pipeline 下的关键创新/洞见和技术贡献，以及 demos/applications。
3. **Method**——Overview 中的任务/输入/输出、写在一起的分步方法，以及实际 pipeline modules 及其子项。
4. **Experiments**——Comparison experiments 与 Ablation studies；消融分别说明核心贡献/重要组件和各模块设计选择的影响。
5. **Limitation**——局限及原因。

Canvas 按原图把每项 challenge/contribution/module 的具名子项展开为独立可编辑节点，
不以一张合并 details 卡替代。完整新输出规范见 `references/analysis-output-template.md`。
新分析使用 `references/analysis-v5-format.md` 的显式 v5 接口：`schema_version: 5`、
`framework: reference_tree_v5`。生成前检查实际安装工具是否支持它；旧 v4 四分支和合并详情
仅用于既有格式兼容，不能替代新五分支结果。结构符合性不证明科学来源真实或 Obsidian 外观已验收；
工具不支持时明确报告限制，不能把旧输出冒称为新格式通过。

这些是输出的可见层级，不规定阅读或推理顺序。挑战、贡献和模块可按论文实际数量重复；原图中
尚未填入内容的框架位置只保留结构，不据此编造论文事实。分析声明 `en` 或 `zh`，图中的框架
标签、正文、证据、链接文案和反链别名采用同一种语言。旧 IR v1–v3 的「任务/输入/分步流程/
输出/边界」分析仍可读取，但不会被普通更新静默转换为 v4。

局部 v4 更新显式声明章节子集，且须提交每个选中章节的**全部保留主张**；当前更新以整章为
替换单位，未选章节不变。版本化 baseline sidecar 绑定两份产物的 revision；人工正文、Canvas
布局和用户自建节点/边保留。任意一端与可信 baseline 不一致时，返回成对冲突与拟议结果，
不会静默重建基线或覆盖。

证据直接写在对应主张旁边，明确区分作者陈述、分析推断、论文未报告、当前索引正文无法核实和
不适用。Canvas 中每个主张都反向链接到 Markdown 的对应证据块；不再建立独立 Evidence 分区或
节点。
若一个主张含有来源归属不同的陈述，v4 在 Markdown 主张块中保存稳定的逐点证据，并将这些点
逐行投影到该主张的一张可编辑 Canvas 详情文字节点。每个主张和逐点内容都带行内证据；有来源支持时还带原文
链接，以及回到对应 Markdown 块的精确反链。v4 的作者陈述与分析推断必须附来源位置：Zotero
PDF 可跳到物理页或已有批注，已登记的
Vault Markdown 可跳到具体块。原文链接与 Canvas→正文反链同处；页级跳转不冒充逐句选中，来源的
身份、版本和归属核验也不能由结构 conformance 代替。
新分析正文在对应论点或逐点论据下方附**原文摘录**，并链接到同一原文页或段落。
摘录保留原语言和原措辞；中文分析可以引用英文原句，意译或译文不冒充逐字引用。
无法核实原措辞时明确报告来源缺口。Canvas 不重复摘录，保留规定的可编辑树与内容层级。
旧分析不会自动改变；转换须显式请求整篇格式更新，不能只手改受管 Markdown。
完整规范见 `references/analysis-format.md`。
v4/v5 可通过 `reader` 显式选择已登记、核验 Vault 的 ZotFlow Library Reader；Markdown 和 Canvas 均可在
Obsidian 内打开本机 Zotero 附件并定位物理页。不指定时仍生成 Zotero 原生入口。来源身份始终是
结构化 span，页级链接不宣称逐句选中或批注同步；使用该选项前仍须核验插件、本机模式与附件。

历史 v4 Canvas 是简洁、可编辑的树形视图，不是第二份知识正文：单根、四大分支、浅灰框架标签和细线
连接，不使用四张卡片。v4 最多有 40 个生成的 claim/details Canvas 语义节点，包含框架标签和合并详情节点在内的受管 Canvas 节点最多
96 个；用户自建的文本、文件、链接和分组节点不占该预算。生成器提供方角连线提示，已安装的
Advanced Canvas 可呈现相应效果；不安装仍可编辑 `.canvas`，只是连线外观可能不同。手动修改
受管节点的*文字*不会自动反向同步 Markdown；下一次受管更新会报告冲突。安全的人工位置/配色
调整与自建图元会保留。
生成文本框按中文换行估算并在正文下方预留约一行高度，便于点击来源与反链。v4 人类正文和
Canvas 节点不含 `sw-analysis-claim` 机器注释；块锚点、确定性节点 ID 与 sidecar 负责身份。

v5 为每条独立归属的逐点内容生成单独可编辑节点，不合并为详情行。同层对齐、无交叉和无穿框/
遮挡是硬要求，完整几何契约见 `references/analysis-output-template.md`。既有 v4 文档对保留
自己的版本化投影，不静默转换。

旧 joint-placement、provider-bootstrap 与 Field legacy-cutover 入口仍只接受 v4。新 v5 分析
支持不意味着这些迁移入口已支持 v5，也不授权初始化 Field、搬迁或静默降级为 v4。

## 批量一致性门禁

批次中的每篇论文独立暂存和验收。硬契约检查角色覆盖、稳定 ID、行内证据、反向链接、Canvas
完整性、可读尺寸和节点上限，不评价正文风格或模型采用的推理方法。失败项最多接受一次定向修复；
再次失败时先保留结构化诊断，再清理该项的暂存草稿，已合格论文不受影响。Zotero 条目、PDF 和
既有正式知识产物永远不属于回滚范围。

通过门禁的暂存产物仍需经过三文件 CAS 提交才成为正式内容。Markdown、Canvas 和分析 sidecar
共享 journal 与 receipt；base hash 过期或路径含 symlink 时关闭失败，条件回滚不会覆盖并发人工
编辑。生成的确定性 change set 只记录显式提供的关系与投影，不从自由正文链接推断权威关系。

另有严格只读的维护审计：它只接收 manifest 明确列出的知识对象与分析文档对，报告孤儿/重复对象、
模板残留、裸 23128 链接、文档对 conformance 和 catalog 漂移，不会扫描任意目录或修复文件。
是否建立每周调度仍是显式的运维选择，不随论文分析自动启用。

## 来源与安全

论文身份和元数据以 Zotero 为准，论文正文来自 Zotero 索引全文。索引缺失的图、表或公式会记录为
来源缺口。只有用户明确要求时才只读查看论文代码仓库，绝不运行、构建或安装其中内容。

Markdown/Canvas 分析对与批注、文献树保持分立。机器身份只放在薄 frontmatter、sidecar 和 Vault
manifest 中，不淹没人类正文。旧 v1–v3 含标记文件只作兼容读取，不静默重写。
