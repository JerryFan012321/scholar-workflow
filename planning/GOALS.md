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
| G1 | 管理论文、书籍、技术文档、Blog/Web article 及相关数据；第一阶段优先论文与技术文档 |
| G2 | 每个对象只有一个主存储位置，其他系统只保存索引、投影或管理信息 |
| G3 | 论文 PDF 的自动获取源头只能是 arXiv；下载后落入收件箱，再经 Zotero Local API 入库，其他来源仅用于身份与元数据核验 |
| G4 | 论文入库经 Zotero Local API 写入完成。新增性写入（下载、create、import、补元数据、加入分类）在用户已下达入库指令时直接执行，不逐一二次批准；仅破坏性/不可逆动作（删除、覆盖冲突条目、合并身份）须逐条批准 |
| G5 | Zotero、Obsidian Vault、Notion 各司其职，不互相复制主数据 |
| G6 | 大型目录采用分层索引：先读索引，再按需读实体文件 |
| G7 | 插件由 Git 管理，功能必须有评测和回归测试 |
| G8 | 支持 Claude Code 与 Codex 两个宿主，共用同一套 skills、hooks 与宿主中立 CLI；宿主与 agent 可通过统一 handoff 协议双向协作，同一机制可扩展到其他真实可用的 agent。Zotero 的读/写/索引全文能力经官方 Local API 提供，不依赖某一宿主的 MCP 注册 |
| G9 | Zotero（及其 PDF 存储）是唯一权威主库；元数据、存在性与索引全文经 Local API 获取。主题召回由 Local API quicksearch + 宿主模型排序完成；新增性写入直接执行，破坏性动作须批准 |
| G10 | **历史目标，2026-10-01 退役**：曾建设本机 Hub 统一入口；不再以自建网页作为科研资料管理的产品中心。既有实现只在显式退场前保持兼容和安全，不因目标取消宣称旧门禁通过 |
| G11 | 为 AI 科研项目提供宿主中立、可分型的项目初始化与实验档案契约：共同的数据/环境/文档/本地保存边界保持稳定，源码和配置按项目类型选择显式 profile，实验以可复现的 Run 和可追踪的 Attempt 管理；既有项目只在逐项目确认后迁移 |
| G12 | 建立人类阅读优先的科研知识系统：以纲领/梳理/目录类核心文档组织主题，以论文、重要技术文档和 Blog/Web article 为原子资源，以分析、批注、Canvas 和补充材料为附属产物；机器身份与关系服务于人类正文和统一资源入口，不能反向淹没正文 |
| G13 | 让单篇和批量知识生产都服从同一可执行结果契约：每篇论文独立校验、失败隔离、至多一次受控修复，未通过模板、证据或可读性门禁的产物不得记为成功；知识库通过周期性审计而非人工记忆维持一致性 |
| G14 | **历史目标，2026-10-01 退役**：Hub Control Plane v2 的既有发布与安全结果保留为追溯记录；仍存在的 HTTP、文件操作和 worker 路径继续守护原安全边界，不再扩展控制面 |
| G15 | **历史目标，2026-10-01 退役**：Hub v3 的独立前端、任务控制与服务产品方向由 G16 取代。Hub 专属未完成验收应 retired，而非 pass；动态知识身份、稳定来源链接和文件安全属于保留能力，不能随 UI 一并删除 |
| G16 | 以科研项目的完整资料上下文为中心：集中展现并显式关联项目代码、论文、分析笔记、实验档案与成果，内容留在各权威来源；人和 agent 不启动 Hub 也能读取、导航和调用。Project 持有薄关联清单，Knowledge 持有可复用正文与资料归属，Analysis 持有分析结果，Adapters 对接原生工具，Workflows 组合任务，CLI/agent/skill 是薄入口与结果契约；不再内置 Codex 任务控制产品 |
| G17 | 构造稳定、可靠、易用且严格满足呈现契约的学术、知识库和实验 skills；第一阶段交付可复现的模范 Vault、模范项目和实验文件夹，以及可复用的外部工具交互。复现是运行期 skill 的明确能力，不只是开发记录：从明确输入经已安装产品入口得到符合版本化契约的产物；单篇样本、合成测试或规划完成不能冒称整个阶段完成。具体交付与证据见 `reproducible-exemplars-stage1.md` |

G17 摘录证据强调增量（2026-10-08，开发未部署）：用户要求直接证据突出；现已明确批准
0.41.7正式发布、正常安装与test中一篇非canonical候选，不合并main或覆盖原稿。通过独立
quote_emphasis保留完整原句并仅在Markdown加粗支撑片段，推断依据明确区分。Canvas和
旧默认保持，人类revision继续冲突停止。合成输入/手写预期先于实现，用户批准合成与必要
回归，不写Vault/Zotero、不发布安装。开发结果及安装态/人工边界分别记录于
quote-emphasis-test-results.md；不据此宣称全G17完成或重开此前Canvas批准。

G17 正文图片安装态（2026-10-08）：用户批准后，0.41.6 source26a2284/runtime852f983
已正常发布安装，CLI固定runtime且cache全部244文件一致。独立单篇公开stage一次validated，
命名展示check conformant；69内容108节点107边、完整Canvas/原句/分析/源图保持，
正文只加两题注源页行；22保护文件不变，未覆盖原稿。新增阅读效果仍待人工，旧Canvas
批准不重开；不重做业务、合并main或冒称全G17完成。见markdown-source-images-test-results.md。

以下为当前发布前历史：
G17 本地发布准备（2026-10-08）：已验证补图实现的源码版本统一至0.41.6；仅准备本地
runtime快照与构建检查，不代表远程发布、正常安装或真实单对象新字段验证。当前安装
仍0.41.5，发布安装授权和正文/其他人类便利性待确认，完整G17不因此完成。
独立范围见markdown-source-images-test-plan.md本地打包节。

G17 阅读入口收尾（2026-10-08）：installed0.41.5核对单Source15文件/6资产，三份普通说明
更新当前正文三图、Canvas已审两图及项目8项生效资料；其他12文件、7项保护及知识身份
保持，14Obsidian导航链接解析。没有新生成/复制/恢复/实验或GUI点击，不新发布安装。
新正文阅读体验及其他人类便利性独立待确认，旧人工批准保留；完整G17未达成。
见exemplar-navigation-results.md当前节；下述旧进度仍保留作历史。

G17 正文图片鲁棒性增量（2026-10-08，未发布）：新增v5显式Markdown来源图片投影，
让选定流程图/实验表自动跟随正文记录，缺图/错位/题注与源页变化不能validated。
旧默认/baseline兼容、focused保留、Canvas完整图保持；合成独立验证，未改真实Vault、
未新发布安装。安装0.41.5已完成的手工IR单篇补图及旧人工批准保持，开发测试不替代
该新字段的安装态验证或新增正文阅读评鉴。见markdown-source-images-test-results.md。

G17 当前核对（2026-10-08）：用户明确图片通过并允许更新，旧人工/覆盖许可阻塞已解除。
0.41.4已正常发布安装，原15文件binding-only合法恢复、单篇已审图2/表2canonical成对采用/
provider应用完成。0.41.5（045085e/65d0754）修复nested正文路径诊断后1857完整回归通过，
正常发布安装的CLI/pipx/cache字节已核。唯一新根在隔离状态public restore完成，15文件/原
导出摘要保持；随后成对更新71正文反链及sidecar，13其他文件保持。108节点107边，正文、
科学内容/原句/图片、旧几何/样式/边及原Source/生产registry/provider/PDF均保持，完整15
文件6资产可再次导出。解锁后新副本两图实际显示及两次正文准确块点击通过，四张当前截图
独立留证（不是71链接逐一点击）。Obsidian重编码两已开Canvas，完整图保持，各自14其他文件
不变；installed公开metadata acknowledgement确认provider新hash，没有重写Vault文档。
用户新增正文图要求：仅原test正文补图2，已有表2/局限图保留，Canvas完整JSON/旧文字/摘录
和来源保持；installed成对更新及最终15文件导出通过。新增正文阅读体验待人，旧图评鉴不重开。
全篇科学支持未认证，显式空缺及其他工具便利性边界保持，完整G17未达成。详见
source-rebinding-results.md。此次不重分析/裁剪/实验、不合并main/迁移其他集合/切换服务。

2026-10-08修复前历史：
installed0.41.3保留原件后采用模范项目既有8项清单并重建根总览；代码/指标保持，未重跑实验。
Source原4资产保持、只新增图2和独立图片复现输入，6项hash/大小符合声明。正式成对提交
因目录device从16777232变为16777230而安全拒绝；路径及inode相同。公开导出亦拒绝旧绑定，
原pair/provider保持字节，20项其他保护输入保持、原包public check通过。没有手改provider
或绕过身份保护；当时正式Canvas尚未加两图。该技术阻断现已由上述0.41.4/0.41.5解除，
历史详情保留于HANDOFF.md及stage1-current-state-audit.md，不作为当前阻断重问用户。

G17 发布安装结果（2026-10-06）：0.41.3正常发布安装（ae3c5a1/2e8228f），完整1829回归通过。
test同篇新候选的图2/表2原生显示与实际正文点击均准确到新文件/块；69内容/108节点/107边，
完整正文与几何/样式/边保持，仅71正文反链变为确切路径。Canvas图片只实验表/关键流程图。
候选public check与独立比较通过；人工图片评鉴、带图canonical归属复现、项目覆盖授权仍pending，
不合并main或迁移正式内容；完整G17继续active。详见canvas-companion-links-results.md。

G17 发布前复核（2026-10-06）：0.41.2图2/表2原生显示已取得当前截图，但Canvas正文反链
实际跳到旧同名候选；独立A/B合成鼠标点击确认短名失败、明确Vault路径正确。不是第三方
具体根因的证明。当前hotfix窄修复v5配对正文显示路由，不改已认可树/正文/权限；安装版仍
0.41.2，0.41.3新代码完整1829项回归通过，尚未安装或实机验收。Canvas图片仍仅实验表和关键流程图，人工评鉴、正式
带图归属复现与项目覆盖确认独立待完成；完整G17继续active。见canvas-companion-links-plan.md。

G17 当前补充：0.41.2已正常发布安装并完成单篇完整句修订的public成对提交/归属登记，
69内容/106节点/105边、全部几何/样式/边保持，只有两处旧重复页链接去重；13文件复现
输入仅三受管文件变化。GUI因Mac锁屏未显示新摘录，人工阅读、图片评鉴和项目覆盖权限
仍pending，G17整体active。见canvas-unique-sources-results.md；以下保留历史冻结状态。

G17 当前增量（2026-10-06）：installed0.41.1图2/表2候选原生显示、正文反链与ZotFlow
物理4/14页已核；图片裁剪/美观仍待人工确认且未canonical提交。来源复核发现单点
拼接摘录缺句首，已有完整句stage但重复Canvas页链接而未提交。0.41.2以显式v5投影
修复同目标重复，保留旧默认和所有独立正文证据，16项合成及完整1773项通过；正常发布安装
与单篇成对修订尚待执行。项目入口覆盖确认仍独立pending，G17完整四类目标未完成。
详见canvas-unique-sources-plan.md；以下旧版本段落保留历史证据，不覆盖当前状态。

G17 当前证据：0.32.3 已生成完整论文候选，现有安装入口已验证模范项目/实验的新目录重建；
0.33.0 已正常发布安装可移植模板和显式复现入口；完整1441回归通过，安装缓存创建单示例与
同源码新克隆重建成功，源码/配方/结果有实际记录，见 `hotfix-0.33.0-results.md`。
0.34.0已正常发布安装无Hub的零写入knowledge preview，完整1453回归通过，单篇安装态预览
和Obsidian可见说明/链接取得真实证据；正式Source/Field登记和v5联合事务仍未完成。
预览不能替代登记、科学支持或人工可读性评鉴，见 `hotfix-0.34.0-results.md`。
0.35.0已正常安装独立只读成对格式/基线检查，完整1482通过；单篇实测68内容/105节点/104边，
原件与registry不变，中文报告和实际资料入口在test。Mac锁屏阻止当前GUI评鉴，旧截图不作证据。
检查不能替代正式Source/Field事务；具体 `hotfix-0.35.0-results.md`，不重复已有效检查。
人类可读性/Canvas评鉴、完整 Source/Field 与外部工具交互证据仍须逐项确认；G17 未完成。
0.36.0独立单Field登记/显式portable Source attach已正常发布安装，完整1508通过；旧稿门禁复用
knowledge核心而非Hub。安装版仅登记test新清洁对象，一个Source/Field和完整两文档导航真实存在，
原文/图不变，9条native links解析；GUI因锁屏pending。已有论文provider与v5联合归档仍未完成，
不把该切片代替完整模范Vault，详见 `hotfix-0.36.0-results.md`。
下一切片0.37.0分离Source文件范围与包含它的Obsidian reader Vault，并提供无Hub的原生笔记/Canvas
打开。完整论文provider归属和人工评鉴仍独立待完成，不以打开请求代替canonical提交。
0.37.1已正常安装，完整1535通过；修编码后原生打开的backend文件状态确为指定Source笔记，
test可读入口四条链接解析。锁屏导致实际截图陈旧，已排除；GUI/人工及完整论文归属继续pending。
0.38.0已正常发布安装单篇paper-plan/register-paper与可恢复owner/导航/provider登记；
最终1561回归通过。安装版在既有清洁test Source/Field新建一个V-JEPA2目录，真实owner登记、
完整v5 paired commit及provider apply成功；68摘录匹配当前附件对应页，68正文block反链和
4资料入口原生解析。旧正文与registry不变，旧Canvas仅编辑器允许metadata变化，节点/边一致。
这是真正的单篇test归属切片，不是正式Vault迁移或G17全阶段完成；锁屏下新GUI/人工审美、
实际点击、逐项科学支持及剩余完整交付仍pending。具体见hotfix-0.38.0-results.md。

2026-10-05新增已查证缺口：test Source缺artifacts.yml，Canvas身份仍仅本机provider持有。
单篇便携声明的公开plan/register开发实现已通过28定向和1604完整合成测试；安装态验收未执行，
不证明整份Vault已能跨机恢复。用户新增完整原句/必要语境的Markdown摘录要求已写唯一规范，
Canvas格式不改；既有V-JEPA2短摘录修订与内容评鉴仍pending。G17继续进行。
正文quote容量随后最小扩至1600，合成v4/v5摘录修订保留Canvas完整数据；127定向及最终
1620完整unit/contract通过，11既有警告。0.38.3准备正常发布安装；真实摘录与便携声明尚未应用。
后续0.38.3已正常安装source12f0540/runtime8f2cdac，实际span容量1600；installed单篇便携
声明完成且回执字段值可重放，受保护六文件hash不变。此更新覆盖上段“尚未应用”中的便携声明，
不覆盖真实摘录待修订/评鉴；完整跨机provider恢复、项目整合和G17仍待完成。

最新：installed0.38.3已在现有test V-JEPA2成对提交70处完整摘录及跨页标签，provider明确登记；
36claims/69内容和完整106节点/105边图数据不变，最终conformance零findings。此记录覆盖上段
“真实摘录待修订”，不覆盖新摘录人工阅读待确认、跨机provider恢复或G17其他未完成项。

后续归属复现输入导出已在开发树实现：explicit Source/provider→portable package及文件hash，
导出26项、恢复30项合成测试通过；公开restore-plan/restore可在显式新主机目标独占创建provider，
保留全部内容、身份及旧源，只写本机恢复journal；reader重绑定、科学/人工验收分别报告。
后续0.39.0 source907c3f9/runtime63a29f1已正常发布安装；在test新目录使用隔离host状态
模拟新主机，public attach/restore恢复同一Source/Field/provider归属。8文件完全保留、
同摘要回执幂等、目的地导出摘要与原包一致，旧源/主机registry/provider/PDF保护hash不变。
最终三文件conformant，69内容/106节点/105边；native正文/Canvas backend载入。Mac锁屏，
截图与当前backend不一致，全部排除出本轮GUI证据；reader身份匹配，
新摘录人工阅读、新副本来源/反链点击及科学全项仍pending，不冒称物理另一台主机实测。
上述覆盖“正常安装/单对象重建未完成”，不代表完整模范Vault或G17完成。

最新项目整合切片：0.40.0开发树新增只读--context-file预览明确根JSON候选，沿用项目身份和
有界拒symlink reader；不覆盖旧清单，默认输出不变。独立candidate19项和旧project/eval组合
105通过；完整1695回归通过、11既有warnings。source52ac731/runtimeaa1861d正常发布安装0.40.0，
public单项目候选8项明确未应用；实际Markdown已保存为项目根“项目资料-0.40.0预览.md”，
test“项目资料整合-0.40.0”保存可读说明、机器回执及四项原件hash保护。真实model-project-0330旧清单仍
未替换，覆盖确认已在会话询问；既有实验档案无需重跑。cmux已安装但当前无live socket，
原生窗口动作未通过；G17继续按完整四类对象标准核验，不能用预览能力替代资料实际整合。

后续只读来源核对9个关键父论点，表2/3/6与局限原文支持当前数值及条件；发现3处
已有摘录不足以呈现全部对应论据，test独立报告及原文补充建议已保存。未改已认可的格式，
正文/Canvas/sidecar hash守恒；69内容全项科学审阅仍未完成，不能把局部核对充当全项通过。
用户已反馈满意0.39.0结果；此呈现反馈不代表0.40资料清单已应用。单对象原生PDF区域
演示保存两个证据样例、原文/论点入口和裁剪配方；同工具/参数重放PNG字节一致，原件
四hash不变。它是agent调用既有工具的可见示例，尚未成为插件截图接口或论文强制输出
规范；新截图人工评鉴与G17剩余交付独立，不因新增样例宣称全阶段完成。
后续只读核对方法模块1/2的8子项，主要事实有原文依据，但两处方法摘录待补，含第5页
数据/参数规模及3D-RoPE定位；保留设计解释与推断的区别，图5全程高分辨率对照为估计时间。
test独立可读报告与机器记录已存，原件四hash不变；不把该范围或字符串匹配外推为全篇通过。

用户随后明确要求正文加入截图；Canvas仅询问能力，不扩大为新增图片节点。
0.40.1修复assets.yml及显式附件在归属复现中的遗漏，保持既有三文件更新契约和Canvas投影。
17附件合成边界/恢复及28项v5组合通过，完整1713通过；source b644f82/runtime21c29a7已正常发布安装。
安装版已在原test单篇成对提交正文两图及完整方法摘录，登记归属，check-bundle零findings。
36claims/69内容/106节点/105边守恒，几何/样式/连线不改，仅方法模块2新增一个页级入口。
带图13文件/4附件的独立host-state归属恢复已执行，再导出摘要与原包相同；真实图片hash一致。
不冒称物理新机、verified backup或reader点击已通过。新截图人工阅读仍pending；G17整体继续active，
项目资料生效、外部原生交互和全篇科学验收不由附件复现替代。详见evidence-images-results.md。

原生交互后续实证：installed0.40.1核Local API附件位置，cmux0.64.25原生PDF文件预览已在一个
独立工作区实际显示V-JEPA2的48页。外部CLI在child-only控制模式下拒绝，原生界面新建终端中
identify/open成功，不变更安全设置或已有用户终端；原PDF/正文/Canvas/sidecar四hash不变。
test已保存最短操作及失败诊断，详见native-tool-interaction-results.md。这覆盖旧cmux不可用状态，
不代表批注同步、翻页/缩放人工便利性或全部外部能力通过；G17及其他独立未完成项仍保持。

原生操作规则后续：0.40.2已正常发布安装，将上述已验证步骤放入find-resource的运行期reference，
按需提供本机enclosure、当前/明确cmux目的地和child-only失败交接；不再只放开发记录。
触发描述、源文件、Canvas和业务接口不变。合成回归、正常发行安装身份与人工便利性
分别验证，未发生的结果不记成功；见native-tool-runtime-contract.md。G17仍active。
实际CLI/pipx runtime commit/双cache manifest一致，安装规则字节与提交相同；完整1712项通过
和版本修正后11项复验共同覆盖原1713项。四业务文件hash不变，原生显示旧证据不重跑；
人工便利性仍pending，不以本轮安装缩小四类对象的阶段完成标准。

来源覆盖后续：installed0.40.1只读审阅当前V-JEPA2全部69条内容，35条限定支持、33条需补
同点摘录/页范围/推断限定、1条保留来源空缺。test独立报告已实际显示，34个正文块反链解析、
33问题行四列，原件四hash不变；不是33个错误结论或全文通过。下一步仅定点成对补证据，
不改已认可Canvas布局、不重跑分析/实验或新增runtime发布。详见source-coverage-review-results.md；
G17与其他独立pending项保持。

上述33项后续已通过安装版stage-update/commit-bundle及明确provider apply定点提交，当前
pair零findings；所有106节点几何/非文本字段和105边精确保持，PDF/两截图不变。仅4条
限定文字和对应证据更新，不重分析/布局/实验。当前13文件归属包零写入导出，仅受管三文件
hash变、其他10不变；旧审阅报告保留历史输入。新摘录阅读与入口仍待人工，不以结构通过
或来源补充宣称整个G17完成。详见source-coverage-review-results.md及test独立变化说明。

当前导航后续：installed0.40.2独立核一个项目候选的四外部身份/归属/版本，公开preview仍保留
unverified边界；修正模范Source的01/02/Paper三份滞后说明。Obsidian解析12链接及现有副本
上下文3相对入口，主要导航不再指旧候选或固定原目录；不冒称新版实际复制/恢复或GUI点击。
13文件归属包只三说明hash变，其余10及registry/provider保持；原件快照、PDF和项目保护项
保持，完整成对格式仍通过。旧历史记录保留且明确不属于该包。人工体验与项目生效覆盖授权
仍独立pending；无新版本/服务/主线变化，G17仍active。见exemplar-navigation-results.md。

当前Canvas图片切片：规则限定实验数据表和关键流程图，正文摘录截图不进入Canvas。
0.41.0已正常发布安装；唯一真实V-JEPA2的新增图卡stage因末列碰撞拒绝，原三文件保持且
check-bundle通过。0.41.1最小列定位修复的169项定向检查通过，安装后复验与原生/人工评鉴
仍pending；不合并main、不迁移正式库、不以局部进展宣称G17完成。详见canvas-selected-images-plan.md。

## 长期不变量（INV）

已激活的不变量对任何实现、任何阶段都必须成立，违反即为回归。标为**目标态（未激活）**的条目记录
已经接受、但尚待对应 WI 实现的未来契约；它们不用于把当前已知旧 runtime 误报为新回归。目标态只有在
实现、守护 eval、文档与 release 同步完成后才能激活，并须保留同一 INV ID。`（待补）` 但未标目标态
表示规则已经生效、只是守护 eval 尚缺。

| ID | 不变量 | 状态 / 守护 eval |
|---|---|---|
| INV1 | 一篇论文在 Zotero 中对应唯一条目（item）；条目可隶属多个分类（collection），分类是对条目的多对一投影，不构成重复身份。判重键为 Zotero 规范身份（DOI / title+authors），arXiv id 仅为下载源标识、非判重键；Local API 搜索召回后回读字段确认，且 `zotero ingest` 在写前重复精确核验；模糊命中只提候选、写路径转冲突交人工裁决（NG3） | outcomes: dedup-exact-collapse |
| INV2 | 论文 PDF 由 Zotero 存储（`~/Zotero/storage`）统一持有；Vault-native 或需要全局归档的技术文档即使是 PDF 也进入 Vault。项目 `docs/` 是独立的项目正文域：正文跨域仍须显式复制/归档，副本获得目标身份并独立演化；允许 Project 持有只用于导航与上下文调用的明确资料引用，不因此复制正文、同步或获得外部写权限 | 已激活：routing: file-technical-doc / outcomes: tech-doc-isolation；独立复制见 INV46，新增显式引用目标态见 INV59 |
| INV3 | PDF 定位只通过 Zotero Local API 的 item/attachment 关系与 `PdfRef`，不猜测 storage 路径、不在多目录复制；其他阅读器只消费显式生成且带源/批注哈希的独立 snapshot | outcomes: papers-root-remap（v3 Local API locator/snapshot 守护待补） |
| INV4 | Obsidian 论文表是可重建的派生索引，不是主库 | outcomes: obsidian-human-block-preserved |
| INV5 | Notion 不上传论文/技术文档/图片/数据文件 | safety: no-notion-file-upload |
| INV6 | Notion 机器字段可更新；人工内容不得被同步覆盖 | safety: no-overwrite-human-block |
| INV7 | 状态库只存映射/游标/任务状态/审计，不存知识正文 | （待补） |
| INV8 | 外部程序不得直接写 `zotero.sqlite` | safety: no-sqlite-write |
| INV9 | 对 Zotero 的写入只经官方 Local API，绝不直接写 sqlite。新增性写入（create/import/补元数据/加入分类/下载）在用户已下达指令时直接执行；破坏性动作（删除、覆盖冲突、合并身份）须逐条批准 | safety: no-unapproved-destructive-zotero |
| INV10 | 库内条目元数据以 Zotero Local API 查询为权威；新增条目的元数据取自权威网源（arXiv abs / CVF / DBLP / 出版社），绝不从 PDF 解析；有正式发表版本时会议名覆盖 arXiv 预印本名头 | （待补） |
| INV11 | 下载的论文 PDF 只落入 `paper_inbox`，入库前不复制到多目录；入库经 Zotero Local API 三阶段上传完成，由 Zotero 管理其存储 | （待补） |
| INV12 | 存在性与元数据以 Zotero Local API 查询为权威、实时获取；Local API 不可达时 fail-fast（退出码 3），绝不因"查不到"判为新建 | safety: no-existence-on-unreachable |
| INV13 | ~~本地 `resources` 缓存是 Zotero 的派生只读镜像~~ **已废止（deprecated）**：取消本地缓存镜像，存在性/元数据/索引全文一律实时委托 Zotero Local API。ID 保留不复用 | — |
| INV14 | 主题/模糊召回使用 Local API 全字段/索引全文 quicksearch 产生候选，并输出每个候选的可观察匹配信号；如需排序，必须显示其用户、来源或配置依据。不在本项目自建 embedding/向量索引。候选不得替代 INV1 精确身份确认 | （待补） |
| INV15 | 离线解析器对标识符输入不造占位标题（`title` 为 null）；显示用真名由展示层可选补齐（EXACT 经 Local API 取名、NONE 用对话/抓取），绝不作为判定输入。契约自描述，能力缺失时降级为显示 identifier | resolver: title-null-for-identifier |
| INV16 | scholar-workflow 硬依赖 Zotero 10+ Local API 提供 Zotero 读/写/索引全文。doctor 对配置路径 fail-fast，对 Local API 只做 advisory；每个 Zotero 命令自身不可达时退出 3，绝不把失败解释为无结果。Local API 可在 Zotero 启动后立即重试，不依赖宿主工具注册或重启 agent 会话。写密钥经 `/api/local/authorize` 获取，只存 macOS Keychain，绝不输出或进入配置/git | （待补） |
| INV17 | **PDF/资源入口以稳定身份和受管动作表达，而非以 raw 端口 URL 充当知识身份**：论文持久层只保存 Zotero item/attachment key、`PdfRef` 与 Web Source，Vault artifact 只保存稳定 source/field/artifact ID；ZotFlow、Zotero、cmux、系统阅读器、Obsidian/Canvas 和 allowlisted Web 动作均由运行时从这些身份派生。项目只持有 `project_id` 和主机 registry 的受控定位，项目文档路径不进入全局知识关系。旧 `/hub/item` 与 `/open/paper/<attachment-key>` 只保留一个版本周期的兼容解析；新 UI/正文不得产生它们。任何持久入口都不存绝对路径、动态端口或进程内 action ID | 0.28.x landing 为历史兼容；v3 direct actions 与 168 条旧链接的逐 Field 迁移由 WI-046/WI-048 守护 |
| INV18 | sync-projections 的取数（CLI 经 Local API 读字段与批注）与渲染（CLI 写文件/投影）分离，只经 JSON 消息通信；任何组件都不直接读写 `zotero.sqlite`。新投影保存稳定 attachment URI/PdfRef，不启动或持久化固定端口 link-service URL | （待补） |
| INV19 | Notion 投影**单向 本地→Notion**（本地权威源→Notion，机器只推、不回流）；Notion 是简化跨设备前端，Vault 相关文档只投影一段话摘要与回 Obsidian/Hub 的稳定入口。项目 `docs/` 不通过托管 project-reference 投影进全局知识库；只有显式归档形成的新 Vault 文档才按其新身份投影。进程内 action ID 永不持久化，正文不进入 Notion | 已激活：safety: no-notion-writeback / no-notion-full-body |
| INV21 | **Notion 双库模型**：**Papers 库**每篇论文一行，upsert 键为现有稳定投影 `Resource ID`（显式映射 Zotero item key / work identity，不参与 library 判重）；**Related Docs 库**每个 Vault 附属文档一行，目标 upsert 键为稳定 artifact/resource ID，并经 `Paper` relation 指回论文。v0.27.2 仍以 Vault 相对路径 `Doc ID` 作为 legacy key，迁移必须保留兼容映射。编排顺序仍是先 upsert 论文取得 page_id，再 upsert 相关文档带 relation。Notion 只镜像 Vault/Zotero 的权威关系，不接管 Hub Projects 集合或项目 `docs/` | 已激活：Papers `Resource ID` + legacy Related Docs `Doc ID` + `notion-two-db-relation-order`；stable artifact ID 为**目标态（未激活）** |
| INV20 | **论文类原子资源的主题内 Hub 文档**：每篇论文可按需挂一个相关资料文档，聚合该论文的周边资料位置链接（阅读笔记/分析笔记/方向笔记/补充材料），不重复论文元数据（元数据属 Zotero）。既有统一命名与落点为主题文件夹内 `paper_assets/<年>-<第一作者>-<标题>.md`；它是 INV37 通用 resource hub 的论文类历史布局，不再被视为全知识库的顶层模型。索引行、文献树和 analyze-paper 共用稳定 resource ID 关联该 Hub；同一论文可在不同主题拥有不同语境的 Hub（见 INV25），重投影不得覆盖人工正文 | 已激活：现有 paper hub、稳定关联与人工正文保护；INV37 通用 resource-hub 重解释为**目标态（未激活）** |
| INV22 | **文献树为 novelty tree**(彭思达 literature-tree 法):**可变深度**概念分类拓扑,内部节点是**抽象概念**、论文是**叶**(按 `resource_id` 引用)。**两种同构树共用一套 `concept` 结构与同一渲染器**,靠节点 kind 区分:**技术路线树** `topic → 里程碑任务(task) → pipeline/representation → module(可选) → 论文(叶)`;**挑战洞见树** `topic → challenge → insight → 论文(叶)`。每个概念节点的 **novelty 锚点**只表示**声明语料范围内、有证据支持的最早引入论文**；无法支持该有界优先级主张时保持 unresolved,不得声称全领域首创。按节点类型:**task=类1、pipeline=类2、module=类3**(挑战树中 insight 可选记锚点、challenge 通常不记);**类4=用 module 改进已有 pipeline 的工作**,是**论文级属性**(语境相关),作普通成员挂在被改进节点下、**不设 schema 字段**。一个 doc 一棵树,技术树与挑战树各自编号自含笔记(`02-…技术路线树`、`03-…挑战洞见树`),**共享同一全集**(承 INV25 一文多树)。树旁**并存一份 flat 全集 paper list**(单一元数据账本,论文可在册但 `classified:false` 未分类)。**Vault 布局**:一个主题的全部内容放在一个**以主题命名的文件夹**里(无 `-literature-tree` 外壳);索引文件用**图书馆编码前缀**——`01-Paperlist.md` **固定**是扁平全集账本,每棵树/视图是带编号的自包含笔记(`02-…文献树.md`、`03-…`,创建序,skill 分配编号、CLI 只固定 01 槽)。**一棵树=一个自包含笔记**:内联 Mermaid 概览 + 嵌套 `##`任务/`###`pipeline 小节(各带 novelty 锚点、可选 `内容简介`、`论文列表` subpaperlist);**无 H1**(文件名即标题)。每篇论文另有 `paper_assets/<年>-<第一作者>-<标题>.md` 相关资料笔记,其 `# 相关文献树` 小节反向链接回它在树中的 pipeline 位置(承 INV20 枢纽)。本轮渲染目标限 **Obsidian 受管块 + 内联 Mermaid**(不产 PNG/draw.io/HTML/Notion),块外内容幂等存活(复用 INV4/INV18 机制)。(一文多树与附属分身见 INV25) | outcomes: novelty-tree-topology-and-paperlist / module-level-and-challenge-tree |
| INV23 | **略读级(recommend-papers)临时性**:略读经外部服务(四推荐源 REST + NotebookLM)进行,四源(S2 Recommendations / Scholar Inbox / S2 author watchlist / HF Daily)按 arXiv id 合并去重,仅对用户细化后的 shortlist 走 NotebookLM 略读(省 token,不略读全池);产物为**临时 Reading Report,绝不落 vault、不改 Zotero**;看中的论文经 find/ingest 正式管线入库(精确判重)。推荐聚合器不访问 Zotero,种子由 Local API CLI 注入 | （待补） |
| INV24 | **详细分析级(analyze-paper)源、落点与人类投影**：详细分析只经 Zotero Local API 读取索引全文（承 INV10 不直接解析 PDF 本体），每篇论文按稳定投影 `resource_id`（显式映射 Zotero item/work identity）维护一份 canonical 人类可读 Markdown 分析和一份可编辑概览 Canvas，与人工批注分立并互链；论文进入多个 topic 时，各 topic hub 只链接同一分析对，不复制真源。Markdown 是详细、证据完备的正文真源；新分析使用参考图的 `Abstract / Introduction / Method / Experiments / Limitation` 完整层级和子槽位，Canvas 只保留可编辑、紧凑且与正文同源的主张/逐点投影，不逐字段复制正文。旧“任务 → 输入 → 分步流程 → 输出 → 边界”仅供 IR v1–v3 兼容读取，不能静默重渲染为新框架。Method 呈现实际流程，不添加原图没有的“对应挑战 / 贡献”；不生成独立 Evidence 节点或 field-to-anchor 重复索引。证据与对应 claim/point 同处，提供原文入口和准确正文反链；仍区分作者陈述与分析推断，以及`论文未报告`、`当前正文通道无法核实`、`不适用`。复杂 canonical path、baseline hash 和节点映射进入 manifest/sidecar，不淹没人类正文。局部更新只替换声明的完整分支并保留未选分支、人工正文、自建节点、布局和 stable ID；冲突返回拟议 patch 而不静默覆盖。主题特有解读须另建 topic-owned context artifact，不冒充第二份 canonical 分析 | **v5 已正常发布安装；installed 0.41.1 的现有完整单篇成对检查通过**。五分支与逐点投影已可用；源摘录充分性、人工阅读/审美及正式迁移分别评鉴，安装/结构检查不代替这些验收。 |
| INV25 | **论文↔文献树多对多，主题 Hub 可分身但 canonical 资源产物不分身**：同一篇论文按 Zotero work identity 唯一，并显式映射到现有稳定投影 `resource_id`；它可被任意多个概念节点、多棵树引用——同 topic 内多树（`02-`/`03-`…含技术树+挑战树）、跨不同主题文件夹的树皆可。树节点只引用投影 ID、不复制元数据；`resource_id` 不参与 library 判重。反链是复数关系：一篇论文可同时指向多棵树的多个位置。既有 `paper_assets/…` 是按 topic 分身的语境 Hub，可聚合该 topic 的反链与周边资料位置；它只链接 INV24 的单一 canonical 分析/Canvas。若确需主题特有解读，使用独立 topic-owned context artifact 与新 ID。`01-Paperlist.md` 是每个主题文件夹内的 catalog 视图，同一论文入多个主题可各登记一行。绝不增加“一个 resource_id 只归一个节点/一棵树”的唯一性检查，也绝不因多 topic 复制 resource-owned 正文真源 | 已激活：outcomes: paper-in-multiple-trees；canonical resource artifact 不分身为**目标态（未激活）**，守护待补 |
| INV26 | **跨 agent 委派不扩权**:调用方与目标方地位对称,但目标 agent 的任务范围、工作目录和副作用权限只能等于或窄于用户已授予调用方的范围;破坏性动作、对外发布、凭据访问或任务扩张必须返回调用方走原有决策门禁。调用方负责检查实际产物、整合与最终验证 | safety: no-agent-permission-expansion |
| INV27 | **项目初始化只增不覆且宿主中立**:`init-project` 以 `AGENTS.md` 为项目规则真源,共同基座使用本地标准目录名，源码/config profile 必须显式选择并固定版本，不能自动猜测或随插件升级静默漂移；先 plan 再 apply,已有文件、目录冲突与 symlink 不被静默覆盖。无 Git 管理时只执行 `git init`,不 stage/commit/push;默认不生成 Claude/Codex 自定义 agent 或 hook | safety: no-init-project-clobber / no-init-project-host-automation; outcomes: init-project-idempotent（profile 守护待补） |
| INV28 | **本机 Hub 是无独立知识权威的聚合、路由与受控操作层**：只绑定 loopback，domain/provider、HTTP/UI 与运行控制分层；Zotero 持有论文/PDF/批注，显式 Obsidian Source 持有 Markdown/Canvas/知识关系，项目持有自身 `docs/` 与实验档案，Codex 持有完整线程。Hub 只保存显式 registry、Destination、任务摘要和可重建投影，不扫描磁盘猜测对象，不自动同步权威系统 | contract: hub-http-boundary；v3 扩展见 INV47–INV51 |
| INV29 | **Hub contract 约束各投影格式，而非反向适配自由格式**：唯一根是 `HubDirectory` schema 3；`/api/v1/catalog` 与 `/api/v2/*` 只能从 v3 根派生，不能形成第二事实根。知识关系来自 Zotero/Field manifest/provider，Projects 与 Tools 来自各自显式 registry；Hub 不拥有这些身份、关系或正文。Obsidian 受管文档继续使用薄 `sw_*` frontmatter 和显式 manifest，Hub 不从路径、文件名或自由 Markdown 猜语义 | v2 基线已发布；v3 breaking root 由 WI-042/WI-046 激活 |
| INV30 | **Hub 编辑与 Vault 附件写入必须显式、受控且可检测冲突**：只允许修改由权威 Source/Field manifest/provider 登记、且仍位于对应可信 `folder_id` 根内的 Markdown/Canvas；v1/v2 兼容响应不能成为写入登记根。无自动保存，保存须携带读取时的 content revision，外部已修改则 409 停止，采用原子替换并保护 `sw_*` 身份字段；受管论文分析 Markdown/Canvas/sidecar 必须成对校验更新，不得经单文件 Hub 编辑或旧链接专用迁移拆开改写。论文 PDF/正式批注仍只由 Zotero 管理，Hub 不替换其附件；笔记图片、数据和补充文件属于 Vault asset，以显式 manifest 关联 artifact，客户端不能指定任意目标路径，不从正文 wikilink 猜关系，新增不覆盖同名文件，首版不删除或原地替换附件 | contract: hub-vault-write-boundary / outcomes: hub-explicit-edit-and-vault-assets |
| INV31 | **Hub 只通过预登记任务控制 Codex**：任务请求只提交 allowlisted recipe/target、经核验的对象引用、最多 8 KiB brief、已批准 model_profile_id 和模型支持的 reasoning effort；旧 fast/standard/deep 兼容映射。服务端解析实际 model/cwd/sandbox/permission 与固定 argv，浏览器不能输入原始模型或执行配置。首次设置是独立的安装/目标/有界读写策略确认；只自动选择唯一匹配目标或 recipe，禁止任取首项。线程明确 create/resume/fork，固定实际模型/强度，Default 变化不修改已有线程；禁止 --last 与 merge，完整 transcript 由 Codex 持有。缺少 cmux Destination 不影响独立文件授权 | v2 内部契约已发布；论文入口/Codex 配置增强由 WI-053 实施，独立合成与真实单对象验收 pending |
| INV32 | **科研项目共同边界与源码 profile 分离**：数据固定按 `dataset/<dataset-id>/{source,intermediate,prepared,metadata}` 聚合，离线数据工具位于 `src/utils/dataset_toolkit/`；`env/` 只保存机器无关环境定义，服务器事实归全局 env-records，项目执行路由归 Target profile；`docs/` 与 `experiments/` 本地优先且不作为服务器或源码 Git 的正文真源。源码/config profile 只能影响源码、配置、入口、测试及其直接扩展目录，不能改写这些共同边界 | **0.28.0 已发布并通过 fixture 契约；未迁移真实项目** |
| INV33 | **Run / Attempt / Target 身份分离**：Run 是科学配方，以完整 commit SHA、`run.sh` 内容、resolved config、dataset version/split、seed 和机器无关环境定义确定；多个 Run 可共用 commit。Attempt 是 Run 在一个 Target 上的一次实际执行或重试，Target/GPU/hostname/时间/状态不进入 Run 身份。实验系统不以 branch、worktree 或服务器 checkout 路径替代 commit，也不把 Target 当作 Run 身份 | **0.28.0 已发布并通过 fixture 契约；未运行真实实验** |
| INV34 | **实验档案只记录受控事实且不隐式执行**：Target profile 不保存 credential 或任意 shell command；Run 首次正式 Attempt 后其 recipe 冻结，报告、人工笔记和 artifact manifest 可继续增长。实验档案的创建、校验、索引、成果回收与迁移必须显式、幂等并保留旧文件；首批能力不得因建档或浏览而启动训练 | **0.28.0 已发布确定性档案管理；不含训练执行器** |
| INV35 | **成果晋升与备份状态分离**：源码、Run/Attempt 配方、resolved config、实验报告、指标、参数和环境摘要必须本地保留；点云、代表性图像/视频、关键 checkpoint 等按人工选择晋升并记录来源与哈希；可重算的大中间物可只留 manifest。服务器文件复制回本机称为 artifact promotion，只有第二份独立副本完成校验后才能声明 backup verified | promotion、跨进程 no-overwrite 和故障回滚已随 **0.28.0 发布**；runtime/schema 直接拒绝 verified，直到 WI-041 解锁 |
| INV36 | **运行期 skill 管真实流程与末端呈现，不管内部思考**：任务有明确业务/工具操作流程时，写清输入、依赖、动作、分支、交接、安全权限和完成条件；探索性问题没有固定流程时不人为编造步骤。skill 不规定分析框架、分类方法、思考步骤或推理顺序。末端产物的结构、层级、字段/schema、Canvas 节点/连线、语言、证据、链接、存储位置和完成状态是具体可复现的硬规则；不能为模型偏好、排版方便、生成器限制或旧测试通过而合并/省略必备项。不合格式即不通过，未实现就报告未完成，不能以近似产物冒充合格，也不授权编造事实或扩大范围 | outcomes: runtime-skill-result-contract-only / skill-input-reuse-and-conditional-dependencies / agent-reuses-owning-skill-output-contract（原则及运行文案已更新，独立行为验收 pending；论文生成器适配另项） |
| INV37 | **知识空间采用核心文档—原子资源—附属产物三层模型**：纲领(charter)、目录(catalog)和梳理(survey)类文档构成主题的人类入口；paper、technical-document、blog-post 是可独立引用且可属于多主题的资源原子；analysis、annotations、Canvas、reading/code note 与 supplement/asset 显式隶属于一个资源或主题。Paperlist 与文献树只是 catalog/survey 的论文类视图，不反向定义整个知识库，不强制另造首页。关系使用稳定 ID，由 Knowledge manifest/provider 持有，不从路径、文件名或自由 Markdown 猜语义；Hub 如仍存在，只消费派生投影 | **0.28.0 已发布严格对象/owner schema、显式 change set 及 CAS provider apply**；去除 Hub 反向依赖为 INV60 目标态，真实全库对象迁移仍待 WI-030 |
| INV38 | **承载论述、分析或梳理的持久知识产物必须有人类可读正文，机器状态只能是薄投影**：去掉 frontmatter、manifest/sidecar 与 Hub 后，Markdown 仍须独立表达完整论点和证据出处；Canvas、图片和数据等非正文字节由其 owner Markdown 说明，不要求复制正文。薄 `sw_*` frontmatter、显式 manifest、baseline sidecar 和可重建结构化导出可以存在，但不得把逐字段 hash、关系边、状态清单或机器 schema 混入正文，也不得形成第二份需要人工同步的知识正文。Canvas 是可编辑概览投影，不是唯一的人类版本 | **0.28.0 已发布人类优先渲染与 Markdown/Canvas/sidecar 的 CAS/journal/receipt 提交基座；一般知识文档迁移未开始** |
| INV39 | **Hub 服务必须可识别、可诊断且只有一个受管 owner**：服务只绑定 loopback，动态端口经 mode 0600 discovery 发现；status/health 报告 PID、真实 executable、已安装 Python package/service build、protocol、generation、capability 与日志位置；Codex/Claude plugin manifest 版本另在发布校验中核对，不能由 HTTP health 冒称。`open-hub` 可启动或安全重启仅由 Scholar Workflow 自身证明持有的进程；未知 listener/PID 不得自动终止。raw 端口和兼容路由不是持久知识关系，服务不得依赖源码目录 | v2 health 已发布；v3 lifecycle/discovery 由 INV51/WI-043 激活 |
| INV40 | **论文分析以版本化 profile 和可校验结果接口生成**：当前新 whole-paper 结果须在 Markdown/Canvas 覆盖最新通用参考图的五个完整分支及具名子槽位，focused 只声明并完整更新所选分支。既有 IR v1–v3 与 v4 仍按各自历史接口兼容，普通更新不得静默转版。Evidence 与每个 claim/point 同处，Canvas 是 Markdown 的可编辑紧凑概览；新节点计数须反映实际展开拓扑，不能以旧合并卡计数掩盖节点。v4 的 40 个 claim/details、96 个总受管节点限额仍保护 v4 兼容路径，不据此删掉新模板必备子项；预算冲突须报告而非静默放宽 | **v5 schema/render/conformance/update 已正常发布安装，定向回归与 installed 0.41.1 单篇成对检查通过**；旧版不自动转换，完整真实迁移与人工评鉴仍未完成。 |
| INV41 | **批量知识生产逐项隔离并以验证结果决定成功**：每个输入独立经历 queued/running/validated/failed/repaired 状态；渲染后必须校验 schema、必备角色、证据归属、链接、Canvas 图完整性和节点预算。失败项至多自动修复一次，修复前清理其未提交临时产物，不能污染其他条目；仍失败则保留诊断但不发布产物、不记成功 | **0.28.0 已发布并通过混合批次/故障注入测试** |
| INV42 | **知识库维护是可重复审计而非隐式重写**：周期性审计检查孤儿资源/产物、失效 manifest、重复 canonical analysis、模板版本漂移、raw loopback 身份泄漏和未闭合批任务；默认只报告与生成迁移/修复计划，真实正文、Canvas、项目和 Zotero 条目未经明确任务不得批量改写 | **0.28.0 已发布基于显式 manifest 的全库只读审计**；周度调度与单次显式 repair-plan/apply 仍在 WI-032 |
| INV43 | **HubDirectory v2 typed-library 契约是历史兼容基线**：0.28.x 的 Papers/Projects/Tools Library 与 `library_id + item_type + item_id` 仍需在 v1/v2 compatibility tests 中可由 v3 根派生，但不得继续作为新信息架构或第二事实根 | **0.28.0 已发布；目标态由 INV48 的 Papers/Fields + 平级 Projects/Tools 取代** |
| INV44 | **workspace lease/binding 是历史兼容机制，不再是授权模型**：0.28.1 nonce/generation/fingerprint 的安全属性只用于旧接口回归；v3 不以 binding 决定页面或文件是否可写，cmux 实例身份仅校验 Destination 路由 | **0.28.1 已发布并实机验证；由 INV47/WI-044 取代，不得继续扩展全局只读门禁** |
| INV45 | **Codex 任务由 TaskRecipe、LogicalTask、TaskRun 和明确 thread ID 分层**：浏览器不提交 shell、路径、环境变量、原始 model、sandbox、permission 或任意 config；批准的 model_profile_id 由服务端解析，模型目录不冒充账号权限证明。brief 与选定对象身份只经 stdin，固定 argv 使用 shell=False，worker 先探测 capability，以幂等键、线程互斥、心跳、取消、超时和进程组回收约束运行 | 内部原语随 0.28.0 发布，生产入口随 0.29.0 安装；新设置/profile/上下文逻辑 WI-053 尚未独立测试，真实 Codex 执行待批准 |
| INV46 | **项目资料引用与正文交接分离**：项目 manifest 提供稳定 `project_id`；Project 的薄关联清单显式引用外部资料而不托管正文或授予跨域写权限。正文交接仍是显式独立复制/归档：Knowledge→Project 剥离知识机器身份，Project→Knowledge 创建新 Vault 身份；无同步、级联删除或强制 provenance。仍存在的 Hub 文件 API 只接受 `project_id + docs 相对路径`，删除进入项目 trash 且不执行 Git 写操作 | 旧独立复制与 `docs/` 安全基线保留；新增项目关联由 INV59/WI-054 守护，尚未独立测试 |
| INV47 | **cmux Destination 与文件/执行 Target 完全分离**：Destination 只决定 terminal/browser/Codex/CLI 窗口在哪个 cmux workspace 出现；文件和 cwd 权限只来自登记的 folder/project ExecutionTarget、相对路径、能力、CAS 与 symlink 防护。workspace 消失只使依赖它的 launch 失效，绝不能让 Hub 全局只读或改变同一文件操作的授权结果 | **0.29.0 目标态（实施中）**：WI-042/WI-044；safety: `hub-v3-destination-not-file-authority`；outcome: `hub-v3-destination-target-separation` |
| INV48 | **Papers 与动态 Fields 是仅有的文档 Libraries**：Papers 由 Zotero Local API 实时提供；Fields 来自显式 Obsidian Source registration 与便携 `.scholar-workflow/fields.yml`，一个 Source 可含多个 Field。Projects、Tools 与 Libraries 平级；Field 导航自由定义，内部 owner role 不成为公开复杂分类。含旧分析或旧链接的首次 Field 必须把登记、受管内容、导航、manifest 与链接放进同一份经审议事务，不得先登记再另行迁移；新导航不能静默遗漏预览文档 | **0.29.0 目标态（实施中）**：WI-045/WI-046/WI-048；safety: `hub-v3-field-single-confirm`；outcome: `hub-v3-directory-and-dynamic-fields` |
| INV49 | **稳定身份直接解析动作，禁止把 landing/端口当知识入口**：论文/PDF/Field/项目通过 EntityRef、PdfRef、field_id、project_id 生成预登记动作；论文卡片默认一跳打开经本机附件复验的 Zotero，并可直接选择 cmux、系统阅读器、分析/批注文档及本机模式经验证的 ZotFlow。新 UI/文档不得产生可见 landing 或 raw loopback URL，旧路由只作一版本兼容解析 | **0.29.0 目标态（实施中）**：WI-046/WI-048；outcome: `hub-v3-direct-resource-actions` |
| INV50 | **Zotero 批注是单一权威，ZotFlow 是唯一 Zotero Web API 密钥持有者**：密钥只留在 Obsidian SecretStorage，Hub/CLI/agent/config/env/log/diagnostics 均不得获取。Scholar Workflow 经 Local API 读取批注形成只读 AnnotationIR；ZotFlow Source Note、Better Notes 与 Scholar 分析文件 writer/path 分离。Local API 入库密钥仍按既有 Keychain 策略管理 | **0.29.0 目标态（实施中）**：WI-047；safety: `hub-v3-zotero-annotation-authority` / `hub-v3-no-multiwriter-path`；outcome: `hub-v3-zotero-annotation-authority` |
| INV51 | **Hub 服务可发现、可停止、版本自证且不依赖源码目录**：已安装包在 loopback 动态端口运行，mode 0600 discovery 记录 PID/port/build/protocol/generation/executable/log；`open-hub` 与 `hub start/status/stop/restart/doctor` 只管理经身份握手证明属于 Scholar Workflow 的进程，未知进程 fail closed | **0.29.0 目标态（实施中）**：WI-043/WI-049；safety: `hub-v3-managed-service-identity`；outcome: `hub-v3-installed-service-lifecycle` |
| INV52 | **Hub/ZotFlow 阅读论文 PDF 不依赖云端附件下载**：ZotFlow 的元数据/批注 Web API 同步允许，但 PDF 只从已审计版本、已验证的桌面本机 Zotero storage 读取；本机模式无法由非秘密探针证明或附件缺失/变化时动作失败关闭，不回退 Web API/WebDAV 文件端点。Zotero 原生打开前也复验本机 PdfRef；Hub/agent 不读取 ZotFlow 密钥或完整秘密配置 | **0.29.0 目标态（实施中）**：WI-047/WI-049；V-JEPA 2 本机阅读、用户手工双向批注往返及独立 Preview 快照样本已通过，真实 Hub 卡片仍待验收 |
| INV53 | **论点和逐点论据可追溯到原文具体位置，精度不得虚报**：新论文分析的作者事实与分析推断须在行内证据旁携带结构化来源位置，并在 Markdown/Canvas 生成稳定原文链接和 Canvas→正文反链。Zotero PDF 保存 library/attachment 身份、内容 hash、零基物理页与可选已核实批注 key；无批注时仅承诺页级定位，保留节/图/表/短引提示。已登记 Vault Markdown 以 Source/artifact 身份与块锚点定位；其他格式仅用其已验证的格式特定定位器，不能伪造 PDF 页/坐标。结构 conformance 不代替 Local API、字节版本、批注归属或块存在性核验。cmux 本机 PDF 只读预览不冒充 Zotero 原生 reader 或同步批注器 | **0.29.0 目标态（实施中）**：WI-050；IR v3 结构与渲染已有测试，真实 V-JEPA 来源逐项核验及 cmux GUI 验收待完成 |
| INV54 | **论文分析后的输出忠实投影最新通用参考图并保持可编辑**：Markdown/JSON Canvas 共享 `Abstract / Introduction / Method / Experiments / Limitation` 五分支，完整展开原图的 challenge/contribution/module 具名子项；Introduction 保留 demos/applications，Method Overview 保留任务/输入/输出及合写步骤，Experiments 独立含对比和核心组件/模块设计选择消融。详细输出规范唯一持于 `skills/analyze-paper/references/analysis-output-template.md`，不规定模型阅读或推理步骤。Canvas 为独立可编辑子节点、直角无箭头连线、紧凑布局、点击留白，逐点保留行内证据、原文入口与正文反链；正文附源语言逐字摘录及必要语境，Canvas 不附摘录。Canvas 图片补充仅限实验数据表和关键流程图，段落截图留在正文；图片不取代树形节点或证据。标签语言一致，空槽不编造；旧产物不自动刷新 | **v5 完整框架及对齐、无交叉/穿框门禁已实现并正常安装，科学来源和人工评鉴独立**。选定图片接口在 0.41.0 发布、0.41.1 窄修复后安装；单篇候选 public stage/check 通过，Obsidian 1.14.4 实际显示图2/表2，正文反链及 ZotFlow 物理4/14页点击核验。只加两图，不改旧106节点/105边或正文；裁剪充分性/美观待人工，候选未提交或新增资产登记，不称完整带图归属复现。outcome: `analysis-canvas-selected-source-visuals` |
| INV55 | **v4 人类正文不暴露机器身份注释**：分析 Markdown 与 Canvas text 节点不得输出 `sw-analysis-claim`；可点击块锚点、确定性节点 ID、薄 frontmatter 和 sidecar 承担身份及更新冲突判断。旧 v1–v3 保持兼容，旧 v4 sidecar 不静默重新信任 | 开发树 markerless conformance/update 已实现；test Vault 候选已重生，正式 Vault 未迁移；WI-051 |
| INV56 | **来源身份与阅读器投影分离，点击空间可用**：新 v4 可在已核实的 Vault 上显式选择 ZotFlow Library Reader 页级链接，Markdown/Canvas 成对生成并校验；默认保留 Zotero 原生入口，不能把 URI 当 PdfRef 或批注同步证明。Canvas 文本框按中英文换行估算，并多留约一行高度供点击，整体仍不得单轴过度延伸 | 开发树与 test Vault 候选结构门禁已通过；2026-09-29 用户确认最新版候选链接可用且页码正确。此项不证明逐条论据来源或批注双向同步；WI-051/WI-050 |
| INV57 | **新论文一篇一目录，旧稿搬迁须独立审议**：新 companion note、分析 Markdown、Canvas 与 sidecar 同处 Field 内 `resources/papers/<stable-paper-segment>/`，目录段与 resource ID 须持久映射；PDF 继续在 Zotero。旧 `paper_assets` 与平铺分析对原位兼容，不由普通更新移动；正式搬迁需要带 CAS、journal、条件恢复与链接改写的显式事务 | 开发树 v4 commit 已核对 Vault 身份、锁定的 provider manifest owner、完整 snapshot CAS、目标路径和 Zotero key；旧 provider 需可信绑定且 CLI 尚未解析到指定 Source。普通 Field 文件可在本地受审搬迁；provider+分析三件套的统一事务仍缺，正式 Vault 未改，WI-052 |
| INV58 | **所有面向人的呈现遵守一致的共同结果规范**：笔记、Canvas、树、报告、Hub 和 CLI 文本都明确对象与范围，优先展示可读结论/状态；同一产物的语言和标签一致；论据与可用原文入口贴近所支持的论点、定位精度不夸大；不可点击的入口不伪装成链接；完成、部分完成、失败、冲突与不可用状态不混称，机器身份不淹没正文。共同规范不取代各格式已验收的具体模板 | **目标态（未激活）**：`references/human-presentation.md` 已形成共同文本；outcomes: `human-facing-presentation-consistency` pending。Hub 预览与 CLI 文本仍有待实现和独立验收的缺口 |
| INV59 | **项目资料关联是独立、便携的薄清单**：`project-context.json` 使用自己的 schema/version，并绑定稳定 `project_id`；`project-layout.json` 仍只持有布局与 profile。关联由人或 agent 明确给出，项目内文件用安全相对路径，外部资料用稳定 provider/entity identity；显示名称不证明身份，不自动扫描关联、复制正文、同步或级联删除 | **目标态（未激活）**：WI-054；schema/model/只读CLI已写入开发树，未运行测试或发布，详见 `project-centered-refactor.md` |
| INV60 | **内容核心不依赖网页控制面**：Project/Knowledge/Analysis 不依赖 Hub HTTP、UI、task store 或 workspace registry；Adapters 对接原生外部接口，Workflows 组合核心能力，CLI/agent/skill 只解析与呈现结果。兼容 facade 可暂保留，但不得制造第二份模型或状态真源 | **目标态（未激活）**：WI-054 分批解耦；本批不宣称全部旧依赖已移除 |
| INV61 | **项目整合视图为可重建导航，不是事实或执行控制面**：从显式清单与项目档案生成可读 Markdown；区分已登记引用、已解析对象和未核验来源，显示可用链接、缺失与冲突。不得把登记成功冒充来源验证、实验成功或人工可读性验收；源码、Run/Attempt/Target、promotion 和 backup 状态仍归原权威记录 | **目标态（未激活）**：WI-054；仅单项目合成样本准备，真实项目与人工评鉴未执行 |

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
| NG7 | 无证据自动宣布某论文是"突破性工作"（反浮夸）。注意与 INV22 的 novelty 锚点区分:锚点是"声明语料范围内最早引入该 task/pipeline/module(类1/2/3)"的**有界、可核实先后事实**、非价值判断,不受本条约束;本条禁的是给论文贴超出锚点定义的"突破"徽章 | （待补） |
| NG8 | 第一阶段自动下载书籍/标准/数据集文件（先只做元数据和索引） | （待补） |
| NG9 | `init-project` 默认或隐式安装项目级自定义 agent、自动格式化 hook 或审查/验证 agent | safety: no-init-project-host-automation |
| NG10 | Hub 成为新的论文/笔记数据库，接收任意文件路径、任意 URL、workspace UUID、原始 Codex 配置/权限参数或 shell 命令，向已有 terminal 注入按键，或在页面加载时自动启动外部应用/自动写回权威系统。唯一任务文本入口是 INV31/INV45 定义的受限 brief，唯一文件写入是 INV30/INV46 定义的显式受控操作 | contract: hub-http-boundary / hub-vault-write-boundary / hub-cmux-runtime |
| NG11 | 把 Canvas、字段表、机器 schema、frontmatter 或 sidecar 当成唯一的人类知识产物，或要求读者理解内部 canonical path/hash 才能读懂正文 | （待补） |
| NG12 | 让无法识别 owner、版本、capability、catalog 或日志位置的后台进程/端口成为知识系统唯一入口；或在端口冲突时静默连接旧服务、换端口或打开演示实例 | （待补） |
| NG13 | 扫描磁盘、workspace 或 `$PATH` 自动发现并注册项目、工具或可执行能力；Projects 与 Tools 只能来自显式 manifest/registry | （待补） |
| NG14 | 在 Knowledge 与 Project 之间建立自动同步、跨域覆盖、级联删除、强制 provenance 回执或隐式双真源；显式导航引用不等于同步，跨域副本仍按 INV46 独立演化 | （待补） |
| NG15 | 由浏览器输入原始任务 cwd/model/sandbox/permission/config（批准 profile ID 不属原始配置），使用 `--last` 猜线程，或合并 Codex thread | （待补） |
| NG16 | Hub 首版永久删除项目文档、自动清空项目 trash、自动 archive/delete Codex 历史，或执行 `git add/commit/push` | （待补） |
| NG17 | 用 workspace/binding 作为全局写入门禁、文件权限或知识/项目根身份；cmux 只能路由窗口 | safety: `hub-v3-destination-not-file-authority`；outcome: `hub-v3-destination-target-separation` |
| NG18 | 在 Zotero、PDF 与 Obsidian 之间建立三向隐式同步，让 Hub/agent 持有 Zotero Web API 密钥，或让 ZotFlow、Better Notes 与 Scholar Workflow 多 writer 写同一文件/路径前缀 | safety: `hub-v3-zotero-annotation-authority` / `hub-v3-no-multiwriter-path`；outcome: `hub-v3-zotero-annotation-authority` |
| NG19 | 固定 Field 枚举、把内部 artifact/owner role 暴露为繁琐公共分类，或让论文/附件/文档 landing 成为正常 UI 的必经中间页 | safety: `hub-v3-field-single-confirm`；outcomes: `hub-v3-directory-and-dynamic-fields` / `hub-v3-direct-resource-actions` |
| NG20 | 为 Hub 或 ZotFlow 阅读动作从 Zotero Web API/WebDAV 获取缺失 PDF，或把元数据/批注 Web API 同步误当作用户同意云端 PDF 下载 | INV52；WI-047/WI-049 |
| NG21 | 继续扩建 Scholar 内置 Codex 模型配置、任务页面、线程控制或长期 worker 产品；外部 Codex 保持原生配置与历史，仍存在的兼容执行路径不得绕过旧安全策略 | WI-054；Hub 专属未完成门禁 retired，不冒充 pass |
| NG22 | 要求用户先启动 Hub、绑定 workspace 或新建强制首页才能管理项目资料；为了整合而批量复制、迁移正文或重新组织全部真实项目/Vault | INV59–INV61；真实写入与迁移仍分别授权 |

## 阶段状态（随开发更新）

2026-10-04 最新分析切片：v5 五分支开发实现曾通过 164 项定向合成回归；后续对齐/无交叉
审计补修了额外边、人工遮挡和稀疏单链布局，最新代码尚未测试。精确安全/预算/几何输入及
完整回归方案已准备，执行待新批准；未发布安装、未写 Vault，新样张人工评鉴和科学核验仍独立待做。

| 阶段 | 目标 | 状态 |
|---|---|---|
| Phase 0 | 插件骨架、契约、evals 基线、开发规范 | ✅ 完成（v0.23.0:review 类 skills 退场,跨模型部分重构为双向 agent-collaboration,新增宿主中立 init-project；config-setup 与 project-backlog 保留） |
| Phase 1 | 论文发现 + 下载到收件箱 + 经 Zotero Local API 入库 | 🚧 进行中（Local API 读写/授权/三阶段上传/精确判重已有契约测试；Zotero 10.0.2 实机 probe/search/collections、真实授权/create/imported PDF 上传、重复 ingest 的 DOI 判重与附件复用均已通过；skill/reference/agent/evals 已迁移） |
| Phase 2 | 投影同步（Obsidian 索引 + 本机 Hub/PDF 服务 + Notion 双库投影） | 🚧 进行中（v0.26.0 扩展 loopback Hub，v0.27.0 曾只允许创建空白 native agent-session；该旧任务规则已由 INV31/INV45 的受控 TaskRecipe + bounded brief 取代，且生产任务入口继续禁用。**Notion 双库(Papers + Related Docs)已实盘上线**。旧 0.18.0 `serve-links` LaunchAgent 已由用户显式停止/disabled；0.28.1 曾由手工 cmux 前台 Hub 持有 23128，当前该端口无监听；剩：v3 受管服务正式安装、旧 Vault 显式迁移、方向级笔记的 Notion 表示） |
| Phase 3 | 文献脉络树 | 🚧 进行中（novelty tree 模型 v0.10.0 落库；**v0.15.0 渲染形态重构**：一棵树=一个自包含笔记(内联 Mermaid + `##`任务/`###`pipeline 分节 + subpaperlist)、`01-Paperlist.md` 独立全集账本、图书馆编码前缀、多树共存、`paper_assets/` 相关资料笔记 `# 相关文献树` 反链(INV20)、无 H1;共享渲染器 `projection.py` 删 DOI 列 + 星级 Importance(连带 sync-projections 变 9 列)。schema:`literature-tree.schema.json`(paper_list + 三级概念树 + summary/asset_note + challenge-insight seam)、`workflows/novelty_tree.py`(render_mermaid + render_tree_note/render_paperlist + plan/project，复用 render_table/ObsidianAdapter)、`project-literature-tree` CLI(带 --dry-run + paperlist_only)、SKILL/agent/docs、INV22 + outcomes 守护。**v0.17.0 模型广义扩展**:novelty 三类→四类(task=1/pipeline=2/module=3 节点锚点、类4=改进型论文作普通成员不入 schema)、拓扑加**可选 module 第四层**(变深度)、**挑战洞见树(challenge→insight→论文)从 schema seam 升为正式落地**——与技术树同构、复用 `concept` 结构与同一渲染器(F3 兑现);`render_mermaid` 由硬编码三层重写为递归 N 层(修 module/insight 被图静默丢弃的 bug)、`_KIND_DEPTH`/`_ANCHOR_LABEL`/classDef 加 module/challenge/insight 表项;新增 INV25(一文多树+topic-local Hub 分身；2026-09-21 进一步明确 canonical resource artifact 不分身)。实盘端到端已完成(世界模型 39 篇双树)。2026-09-21 起 Paperlist/文献树按 INV37 明确为 catalog/survey 的论文类视图；剩：真实主题更多端到端实盘与知识系统 v2 Catalog 统一） |
| Phase 4 | 一致性审计 | 🚧 0.28.0 已发布显式 knowledge manifest 的只读审计与批次审计；周调度、单次 repair-plan/apply 和真实 Vault 审计未执行 |
| Phase 5 | 两级 AI 阅读（略读推荐 + 详细分析） | 🚧 进行中（recommend-papers 基座已落地；analyze-paper v2 的人类正文、紧凑 Canvas、profile/IR、conformance、一次修复与 canonical transaction 已随 0.28.0 发布。test Vault 的新 V-JEPA 2 v4 候选内容、Canvas 和 ZotFlow 页链已获用户验收；旧稿逐项守恒、正式迁移与其他论文的科学来源核验仍待完成。notebooklm-py 略读闭环、watchlist 半自动登记、doctor 探针 + 回落也未完成） |
| Phase 6 | 科研项目系统 v2（共同基座 + 源码/config profiles + Run/Attempt/Target + 本地成果保存） | 🚧 基座已随 0.28.0 发布并通过 fixture 测试；真实项目 pilot 与 backup backend 未执行 |
| Phase 7 | 科研知识系统 v2（核心文档 + 原子资源 + 附属产物 + 人类投影 + 批量 conformance） | 🚧 分析/批处理/只读审计基座已随 0.28.0 发布；JEPA test Vault 候选已验收，但正式 Vault 的 JEPA/世界模型迁移、全库对象迁移与周调度均未执行 |
| Phase 8 | Hub Control Plane v2 历史基线 | 历史发布/测试事实保留；产品目标退役，不继续扩建。存量接口未退场前仍需安全守护；本次未核验或改变任何监听进程 |
| Phase 9 | Hub v3 历史纠偏与兼容实现 | 2026-10-01 产品方向由 G16 取代；Hub UI/worker 专属残余验收 retired，不记 pass。知识模板、来源和真实迁移门禁独立保留；既往结果不视为本批测试 |
| Phase 10 | 项目中心资料整合与职责解耦 | Stage A 源码已实现：独立context/schema/只读CLI与首批Knowledge公共模型/文档/Field提取；原生reader、文献树catalog与Field事务仍留兼容Hub依赖。未运行独立测试，未发布/安装、停服务或迁移真实数据。详见 `project-centered-refactor.md` |

## 未来项（记录待办，暂不实现）

| ID | 事项 | 说明 |
|---|---|---|
| F1 | 给文章标题加入重要程度批注 | 在展示/索引论文标题时附一个推荐重要程度的批注，辅助人工判断优先级。待 Zotero 元数据读取链路稳定后再设计。 |
| F2 | ~~Zotero 官方本地写 API 落地后重启程序化写入~~ **已兑现** | 由 Zotero 10+ 官方 Local API 提供本地读写能力；无需第三方 MCP。新增性写入直接执行，破坏性动作须批准（见 G4/G9/INV9/NG5）。 |
| F3 | ~~challenge-insight tree（挑战-洞见树）~~ **已落地（v0.17.0）** | 与技术路线树同构、复用 `concept` 结构与同一渲染器（一个 doc 一棵树），已并入 INV22。原 `challenge_insight_tree` schema seam 退场（不再做平行异构结构）。触发源:世界模型调研实盘已手搭双树。 |
| F4 | recommend-papers 略读闭环实盘 + watchlist 登记 + doctor 回落 | A3/A4：notebooklm-py 实盘略读、watchlist 半自动登记子模式（authorId 台账 + 项目层配置按 cwd 加载）、doctor 探针 + NotebookLM/Scholar Inbox 回落。tracer(A1) + 四源聚合(A2)已落地，闭环待实盘。 |
| F5 | Scholar Inbox 反馈回流（rate / trending / collect） | feed-agent 的 recommend-papers 已吸收 scholar-agent 的「拉取 + NotebookLM 略读」主链，但缺反馈回流：`rate`/`rate-batch`（点赞驯化推荐口味）、`trending`（跨社区热点，独立于个性化 digest）、`collect`（Scholar Inbox 侧收藏）。vendored `scholar_inbox` 目前只含读取侧（api/auth/config）。补法倾向扩 vendored client + recommend-papers 加「反馈」子模式，不原样引入整个 scholar-agent skill（与 recommend-papers 大面积重复）。参考 jiahao-shao1/sjh-skills 的 scholar-agent。 |

## 维护规则

- 目标/不变量/非目标**变化时更新本文**，但**保持 ID 稳定**；新增项分配新 ID，不复用旧 ID。
- 每条目标应由 `evals/` 的用例守护。`（待补）` 标记尚未有守护 eval 的缺口。
- 目标或范围变化必须同步记入 `CHANGELOG.md`。
- 这是活文档，不归档。原始设计文档已移出仓库（`archived/scholar-workflow/project_references/`），仅作历史快照留存。
- **项目中心重构（2026-10-01）**：新增 G16、INV59–INV61、NG21–NG22 与 Phase 10；G10/G14/G15
  保留 ID 并标记产品目标退役。明确允许项目持有导航/上下文引用，继续禁止隐式同步和双真源；正文、
  模板、原文证据、安全事务及实验档案不随 Hub 退役而取消。旧 Hub 专属门禁应 retired 而非 pass；
  仍有代码的兼容路径继续遵守安全约束。当前正式重构规格为 `project-centered-refactor.md`。
- **Hub v3 架构纠偏（2026-09-23）**：新增 G15、INV47–INV51、NG17–NG19 和 Phase 9；
  cmux workspace 从全局授权降为窗口 Destination，文件/cwd 由可信 Target 授权；文档 Libraries 收敛为
  Papers + 动态 Fields，Projects/Tools 平级；论文入口改为 direct actions，Zotero 批注唯一权威且
  ZotFlow 独占 Web API 密钥；受管服务使用动态端口/discovery，不依赖源码目录。v2 G14/INV43–INV44
  继续作为 0.28.x 历史兼容基线，不能覆盖 v3。正式规格见 `hub-control-plane-v3.md`。
- **三系统联合改造（2026-09-22）**：新增 G13–G14、INV40–INV46、NG13–NG16 和 Phase 8；
  `HubDirectory` 成为唯一根，Projects/Tools 进入独立 typed Library，Knowledge/Project 改为显式独立复制，
  bounded brief/effort 取代 blank-session-only 规则，批量论文输出必须逐篇通过 conformance gate。
  正式规格见 `project-system-v2.md`、`knowledge-system-v2.md` 和 `hub-control-plane-v2.md`。
- **科研知识系统 v2 修订（2026-09-21）**：V-JEPA 2 真实运行否定了 v0.27.2 的逐字段双投影设计；
  新增 G12、INV37–INV39、NG11–NG12，并修订 INV2/INV17/INV19–INV21/INV24/INV25/INV29。人类 Markdown
  改为正文真源，Canvas 改为概览，机器 baseline 移入 sidecar，raw loopback URL 降为兼容细节。
  以下相关历史条目只记录旧决策过程，不覆盖当前不变量；完整规划见 `planning/knowledge-system-v2.md`。
- **Zotero 官方 Local API 迁移（v0.24.0）**：第三方 zotero-mcp 与 bundled MCP
  配置退场；Zotero 10+ Local API 成为统一边界。确定性 CLI 新增读、授权、精确判重、
  create、collection 与三阶段附件上传；回环限制、禁代理/重定向、上传 URL 校验与 macOS
  Keychain 守护写密钥。Local API 没有原生 semantic/vector endpoint，INV14 改为全文
  quicksearch 召回 + 当前宿主模型排序，不新建 embedding 基础设施。以下 zotero-mcp 条目
  保留为历史决策记录，不代表当前架构。
- **zotero-mcp 转向的下游同步（✅ 已完成对齐）**：全部 4 个顶层 references（security / storage / identity / source）、全部 5 个 SKILL.md、全部 5 个 agents、`evals/safety.json`（`no-zotero-write` 删除 → `no-unapproved-destructive-zotero` + `no-create-without-existence-check`；`no-existence-on-unreachable` 语义迁至 MCP；删除守护已删机制的 `no-unapproved-apply` / `plan-invalidated-on-change`）均已按 zotero-mcp 新模型重写；代码层退场项（`adapters/zotero_local.py`、`workflows/sync.py`、`dedup`、CLI 的 `sync`/`locate`/`resolve`/`catalog`）已删除。
- **审批原则变更（本轮）**：写入审批从"每次写入须批准"改为"新增性写入直接执行、仅破坏性动作须批准"（G4/G9/INV9/NG5），并同步至 `~/.claude/CLAUDE.md` 与 `references/security-policy.md`。
- **INV16 两层守护的缘由(v0.18.0/v0.19.0)**：INV16 正文已把"可达性"写成名实一致的两层(doctor 对路径 fail-fast + 端点 advisory;skill 层核验工具注册),不再靠脚注反向解释"必检退出 3"。缘由：CLI 子进程够不到 MCP 工具,只能探端点 TCP/HTTP 层;而 HTTP-MCP 只在会话启动瞬间注册、端点未起则整会话静默无工具且不自愈——若把端点暂态计入退出码会让每次 Zotero 没开都阻断整会话,故端点检查定为 advisory,真正的 fail-fast 交 skill 层(工具缺失时,见 `security-policy.md` zotero-mcp boundary)。
- **规划文档迁入 `planning/`（本轮）**：`GOALS.md`、`HANDOFF.md` 及 per-phase 规格从仓库根迁入永久、不归档的 `planning/`（区别于将被归档的 `dev-guide/`）。AGENT.md 文档边界表已加 planning 层。历史 CHANGELOG 行不追改。
- **INV17/INV18（Phase 2）**：新增本机 loopback PDF link-service（附件-key glob storage、inline 流原始 PDF、URL 只存不透明 key）与 sync-projections 的规划/执行分离（LLM↔CLI 只经 JSON、CLI 不碰 MCP）。决策记录 DR-1 见 `planning/phase2-sync-projections.md`。
- **INV20（Phase 2，曳光弹验证）**：论文相关资料文档经受管块之外的小节挂到索引表，聚合周边资料链接、不重复元数据。已用 `上汽标注/text2cad.md` + 其枢纽笔记端到端验证：块外小节在重投影后存活（INV4 保护）。**v0.21.0 命名收敛（WI-017）**：原 `<论文名>论文相关资料.md` 与 build-literature-tree 的 `paper_assets/<年>-<第一作者>-<标题>.md` 是同一"论文枢纽"的两套命名、互不连通；统一到后者。曳光弹文件已迁移 `上汽标注/Text2CAD论文相关资料.md` → `上汽标注/paper_assets/2024-khan-text2cad.md`，`text2cad.md` 反链同步更新。
- **INV17 历史修订（Notion 本地 URL 双链，已被 2026-09-21 契约取代）**：当时把 Notion PDF
  链接从「只用 Web Source、不用 loopback」改为 `Web Source + Local URL` 并用 text2cad 8 篇实盘；
  当前 INV17 已禁止把 raw loopback URL 作为新投影的规范身份，旧字段只作为显式迁移输入保留。
- **版本 bump 规则放宽（AGENT.md）**：从「每次 skill change 都 bump」改为「按连贯能力批次 bump，0.x 期批次内迭代不单独 bump」。缘由：`0.6→0.7→0.8` 同日三连跳暴露了按 commit bump 的过细粒度。本轮 Notion 双库实盘定为 `0.8.1`（Phase 2 改进，非发布级 minor）。
- **INV19 改写 + INV21 新增（Notion 双库）**：INV19 原「笔记正文渲染为 Notion 原生 page blocks（全文投影）」改为「只投影一段话摘要 + Vault 回跳，正文留 Obsidian」——Notion 定位为简化跨设备前端，不重复本地内容。INV21 确立双库模型（Papers 键 `Resource ID` + Related Docs 键 `Doc ID`，relation 连接，先论文后文档）。代码层：`adapters/notion.py` 的 `upsert_page` 增 `key_property` 参（默认 `Resource ID` 不变）、`config.py` 加 `related_docs_{database,data_source}_id`、契约测试 3→5、`notion-schema.md` 单库→双库。Notion 仍未接线上（无 CLI 命令、config 无 notion 块），属库层就绪，接线上/建真实库/换新 token 为后续 ticket。
- **INV22 新增 + citation-graph 退场（Phase 3, v0.10.0）**：文献树模型由 Phase-0 随手搭的 citation-graph（论文↔论文有向图 + 6 种关系边 + evidence/confidence/review_status）替换为彭思达 literature-tree 法的 **novelty tree**（`task → pipeline → 论文` 三级、概念为内部节点、论文为叶、每概念记 novelty 锚点 + flat paper-list）。缘由：调研彭思达 GAMES003 Notion「literature tree」一手定义确认其树按 novelty 分层归类、非按引用连边；原 citation-graph 从未被 INV 背书、`workflows/lineage.py` 是空 stub，无沉没成本。代码层：`literature-graph.schema.json`→`literature-tree.schema.json`、新 `workflows/novelty_tree.py`（复用 `render_table`/`ObsidianAdapter`）、`project-literature-tree` CLI、删 `edge-evidence.md` + 死 stub、SKILL/agent/README 改写。NG7 澄清：novelty 锚点是可核实先后事实、不受反浮夸约束。challenge-insight tree 留 schema seam、押后作 F 系列 future 项。渲染限 Obsidian 受管块 + 内联 Mermaid（本轮不投 PNG/draw.io/HTML/Notion）。
- **INV23/INV24 新增 + 两级 AI 阅读（Phase 5, feature-ai-reading, v0.11.0）**：新增两个 skill——`recommend-papers`@intake（略读级）+ `analyze-paper`@knowledge（详细分析级）。略读级(INV23)四源聚合(S2 Recommendations / Scholar Inbox / S2 author watchlist / HF Daily)按 arXiv id 合并去重、仅 shortlist 走 NotebookLM 略读、产物临时不落 vault；详细分析级(INV24)经 zotero-mcp `get_content` 读正文落 Obsidian 附属笔记、与批注笔记分立 `related` 互链、局部分析块外多小节追加、挂 INV20 枢纽。代码层：新 `adapters/recommend_sources.py`（HF Daily + S2 recommendations/author + Scholar Inbox 规范化，四源 emit 统一候选、按 arxiv_id 合并）、`config.py` 加 `RecommendConfig` + `load_recommend_config`（两层 recommend.yml，interests/watchlist 追加）、`bin/recommend-papers.py`（唯一网络出口，CLI 零外部网络承 INV18）、vendor sjh `scholar_inbox` 客户端（api/auth/config，MIT 标归属 + THIRD_PARTY_LICENSES）。设计哲学：只编码外来规定（源/落点/格式/网络路径/依赖），不编码内在能力（读/摘/比较/归类）。build-literature-tree 加「批量读料优先经 NotebookLM」编排提示（优化约束、复用略读引擎）。skill 数 7→9（find/ingest/sync/build-tree/check/export/env-setup + recommend-papers + analyze-paper）。剩：略读闭环实盘、watchlist 登记、doctor 回落（记 F4）。
- **survey-topic 编排入口（v0.14.0）**：新增 `survey-topic`@intake（skill 数 9→10），补上「宽泛调研开口无 skill 响应」的缺口——此前"调研世界模型"不触发任何 skill，因九个 skill 全按具体机械动词匹配。定位是**跨 phase 编排入口**：grill 钉死程度/范围/时间窗 → 提有序计划 → 委派给 recommend/find/ingest/build-tree/analyze，**自己不做调研、不落文件、不产物**。设计哲学落点：唯一编码的外来规定是 **depth→skill 映射表**（哪个 skill 服务哪个调研子目标，模型推导不出）；「怎么调研」是内在能力、不编码。边界：**build-literature-tree 保持独立**——"画树"直达它，survey-topic 只是其上游调用者之一，路由过去时交出 scope、让树跑自己的 gate（承 INV22）。不新增 INV：它整体是优化脚手架（模型变强会自己 scope+编排、会贬值），由 `evals/routing.json` 两用例（正向开放式调研 + 负向"画树"动词绕过）+ intake-agent 映射守护即可。借 Matt Pocock writing-great-skills 语汇成文（薄壳编排 + 委派、leading word=survey）。名字 `survey-topic` 为落地初选，无引用绑定、改名成本低。
- **文献树渲染形态重构（Phase 3, v0.15.0）**：按真实世界模型 vault 实践重塑 novelty tree 的落地形态（INV22 渲染子句扩写）。七点外来规定:①主题文件夹以主题命名、无 `-literature-tree` 外壳;②`01-Paperlist.md` 固定为独立扁平全集账本、与树分离(互链);③多棵树/视图可共存,树内论文子集叫 subpaperlist;④索引文件用图书馆编码前缀(01 固定,携带索引/表/Mermaid 的文件才编号 02/03…,skill 分配、CLI 只固定 01 槽);⑤一棵树=一个自包含笔记(内联 Mermaid + 嵌套 `##`任务/`###`pipeline + `内容简介`/`论文列表`),**无 H1**、不重复标题;⑥DOI 留 schema 字段(判重身份)但删表格列,每篇论文加 `paper_assets/<年>-<第一作者>-<标题>.md` 相关资料笔记、每个 `#` 一种资源类型、必含 `# 相关文献树` 小节反链回树的 pipeline 位置(承 INV20 枢纽);⑦Importance 三级文本 `founding`/`milestone`/`representative` + 星级徽章。代码层:schema 加 `summary`(概念内容简介,存 JSON 保幂等)+ `asset_note`(论文资料笔记路径);共享渲染器 `projection.py` 删 DOI 列、Importance 追加星级、Assets 列 opt-in(`assets=True`)——**连带 sync-projections 的 Zotero 镜像也从 10 列变 9 列**(故意共享,一致性);`novelty_tree.py` 由多文件层级重写为单文件分节(`render_tree_note` + `render_paperlist` + `plan/project_*`),`ObsidianAdapter.ensure_managed_block` 支持空 heading(无 H1);`project-literature-tree` CLI 入参加 `filename` + `paperlist_only`,`root` 默认主题名。设计哲学落点:只编码外来规定(布局/编码/形态/字段),不编码内在能力(判归属/写简介/组 Mermaid)。NG7 澄清不变(novelty 锚点是可核实先后事实、非突破徽章)。
- **survey-topic 冷启动广度侦察(v0.15.1)**:真实调研实践暴露一个缺口——冷启动时往往没法盲目界定深浅,得先跑一次快速的 web-inclusive 广度侦察(含非 arXiv 源:无论文的模型、benchmark/项目页、实验室博客)摸出领域轮廓,grill 才有对照可 scope。落地为 survey-topic 三处 prose(身份句不再声称"runs no retrieval"、Grill 段加 Cold-start orientation 小节、Constraints 加"Orientation reads; acquisition is delegated"把获取的 what/where/source 交回 source-policy + ingest-resource 而不复述 arXiv-only)。**Depth→skill 映射表不动**(每行都路由到下游 skill,而侦察不路由到任何 skill、是定向阶段的内部读取)。**并行 fan-out 的机制不编码**(内在能力,承设计哲学)。侦察产物丢弃式(类 recommend-papers 的 Reading Report,INV23),不落 vault、不进库。不新增 INV(优化脚手架、非业务约束);routing.json 不加(侦察是内部模式、非新路由目标)。获取策略经用户澄清定为"仅元数据回落"(无 arXiv 版时只登记元数据+标记,PDF 不自动从他源下),等同现状(NG1),source-policy 不改。
- **文献树模型广义扩展 + 挑战树落地 + INV25(Phase 3, v0.17.0)**:世界模型调研实盘(`0-inbox/世界模型调研经验_20260804.md`,一次真实端到端反馈)驱动的三处扩展。**① novelty 三类→四类**:概念深度轴与论文角色轴分离——1/2/3 类是**概念节点首创**(task/pipeline/**module** 各一级,用现有 `novelty_anchor` 表达,仅新增 module 这一 kind),4 类是**论文级"改进"属性**(用 module 改进已有 pipeline、语境相关),作普通成员挂被改进节点下、**零 schema 字段**(4 类是判断、不编码进数据,承设计哲学"不给无消费者的属性建字段")。**② 拓扑变深度**:加可选 module 第四层,`topic→task→pipeline→module→论文`。**③ 挑战洞见树落地**(F3 兑现):`challenge→insight→论文` 与技术树**同构**,复用同一 `concept` 结构与渲染器、一个 doc 一棵树;原 `challenge_insight_tree` schema seam 退场(不做平行异构结构)。代码层:`concept.kind` 枚举平铺扩举加 `module/challenge/insight`;`render_mermaid` 由硬编码三层(`_emit_task`/`_emit_pipeline` 不递归)重写为**单个递归 `_emit_concept`**——修了 module/insight 及其论文被 Mermaid 图**静默丢弃**的真 bug(文本分节本就递归、图没跟上);`_KIND_DEPTH`(task/challenge=2、pipeline/insight=3、module=4)、`_ANCHOR_LABEL`、classDef 配色各加表项;schema/plan/project/render_table 无结构改动。新增 **INV25 一文多树**:论文↔树多对多(同 resource_id 可跨多节点/多树/含技术树+挑战树)、`paper_assets` 语境 Hub 按主题文件夹分身、`01-Paperlist.md` 按 topic 隔离、绝不加唯一性检查——实盘双树共享全集(§2.4)直接印证。2026-09-21 的新目标契约进一步明确：topic Hub 可分身，但 canonical resource-owned 分析/Canvas 不分身。设计哲学落点:只编码外来规定(四类定义/拓扑/同构/一文多树),不编码内在能力(判归属/首提判断)。NG7 澄清扩到含 module 首创。测试 109→115(novelty_tree 加 module 递归/挑战树同构/一文多树用例,契约 seam 测试替换为 module-depth + challenge-reuse + 退场 seam 拒绝)。实盘打包缺陷(shim/venv 版本漂移/doctor 探针)属独立线,本轮不做。
- **Agent 拓扑重构:按机械动词切 → 按任务级自足单元切(v0.16.0)**:五个 `agents/*.md` 原先①无 YAML frontmatter,Claude Code 从不注册为可委派 subagent,是影子文档;②按机械动作切(发现/入库/投影/建树/审计),而真实任务跨多动作,故每个 agent 是够不着任务的碎片(典型症状:lineage 硬塞一个"只读"find-resource,因为从零建树本就内含搜索)。重切原则:**agent 按「会独立吃大量上下文的用户任务」划分,每个自足拥有完成该任务的全部 skill,skill 可跨 agent 复用、不归属单一 agent**。落地:intake(find+ingest,吸收并删除 library)/ lineage(find+ingest+build-tree,由"只建树"扩为方向级调研)/ **feed**(recommend-papers,新增,从 intake 拆出每日 push 流)/ knowledge(analyze+export+sync,不变)/ audit(check-consistency,不变);全部补 `name`+`description` frontmatter。**Agent 之间不 handoff**——跨 agent 串联由宿主 LLM 或 survey-topic(顶层编排 skill、不挂 agent)编排。连带:①删死链路 `workflows/audit.py` + `cli.py audit`(够不到 MCP 的 stub,check-consistency 实为 skill 层 LLM 执行,stub 曾误导审查报告判其"未实现");②运行期文件清除私有人名归属(彭思达/GAMES003,无路由价值、随 release ship,方法本身不动,出处留 dev 层);③`handoff.schema.json` 正名 `AgentHandoff`→`PreCompactSnapshot`(from/to_agent 硬编码 precompact、唯一生产者是 PreCompact hook,从非 agent 交接;死字段留、契约测试不动)。设计哲学落点:agent 拓扑是优化脚手架(不新增 INV);跨 agent 复用 skill 是特性非 bug。scholar-agent 的反馈回流(rate/trending/collect)记 F5 待办、本轮不做。触发源:codex-review.md 外部审查(P0 frontmatter 阻断 + 影子 agent 层)+ 用户对 lineage 边界的质疑。
- **zotero-mcp 插件 bundling + doctor 三源探针 + 入库自动批准矩阵(v0.19.0)**:世界模型入库反馈(`0-inbox/agent-use-feedback/世界模型入库反馈_20260805.md`,真实端到端)驱动。**① 修「作用域陷阱」**:zotero-mcp 原只注册在 `~/.claude.json` 的**项目作用域** `scholar-workflow` 下,别的目录开会话加载不到、且"重启会话"无效(cwd 仍在作用域外)——这坐实 v0.18.0 诊断/指引对跨目录场景是**错的**(当时归因为端点时序、指引"重启会话")。修法:`.claude-plugin/plugin.json` 声明 `mcpServers.zotero-mcp`(type http、`127.0.0.1:23120/mcp`),插件 bundled MCP 在**所有启用会话、任意 cwd** 自动注册,装插件即得,作用域不再是变量。残留**会话启动时序 caveat**仍在(端点没起则整会话跳过,启动 Zotero+重启)。**② doctor 三源探针**:bundling 后 server 在插件清单、不在 `~/.claude.json`,v0.18.0 只读 project 作用域的探针会静默;`probe_http_mcp_endpoints` 改为合并 **plugin-bundled(manifest)+ global + project** 三源(优先级 project>global>plugin)、不管 cwd 都探、advisory 带 `scope` 标签,CLI 打印 scope(仍 advisory-only 不影响退出码)。**③ 入库自动批准矩阵**(把 G4/G9/INV9 具体化到 ingest 场景):新增性写入分支点(元数据来源、create/import/加分类)端到端不逐条 re-prompt、回执注明假设;仅四类停下等人——归类方向(选哪个集合/哪棵 literature tree,人的偏好、不取默认)、同源不同版裁定(预印本 vs 库内正刊,不自动跳过/合并)、NG3 身份冲突、破坏性动作;并加"same-work different-version"存在性检查 outcome。连带全局 `CLAUDE.md` 加一条**/tmp 一次性脚手架免批准**(编写/运行/删除直接执行、用完精确路径删,受门禁动作不得借脚本绕过)——解释了为何**不**做常驻 `bin/mcp-call.py` / `bin/ingest.py`(反馈建议 2/3):那些是作用域外无 native 工具被迫手搓的症状,bundling 修好根因后 native 工具回归、ingest-resource 原生跑通,curl-直连仅留作 break-glass。设计哲学落点:bundling/doctr/矩阵三者中,只有"入库业务门禁"是业务约束(稳定维护),bundling 与 doctor 探针是优化脚手架/环境事实;不新增 INV(INV16 doctor 分层脚注已涵盖端点探针)。测试 119→123(+4 doctor:global 作用域/bundled manifest/project-over-bundle 优先级/manifest helper)。
- **QA 工具链 + 配置 UX + 工作队列(v0.20.0)**:一批开发/运维设施,均为**优化脚手架**、不动意图层(无新 G/INV/NG)。**① 两个 QA skill**——`project-review`(只读战略快照,配置优先 `.project-review.md` + 精确路径自发现,读被审项目自己的 `AGENT(S).md`/`CLAUDE.md` 判五维度)+ `code-review`(经 codex 的跨模型第二意见,关键是**调用前先建高上下文交接**,Claude 逐点按项目原则消化、接受真问题跳过误判,VERDICT 门最多 5 轮);两者**通用可发布**、不硬编码任何项目文件名。**② 配置 UX**——`config` CLI 命令组(`init`/`set`/`get`/`show [--raw]`/`path`)+ 薄 `config-setup` skill,补上"装完插件无对话内配置路径、连 `doctor` 都因 config.yml 缺失而崩"的缺口:`load_config()` 改抛 `ConfigNotFound`(`FileNotFoundError` 子类,向后兼容),业务命令翻成干净退出码 3 指向 `config init`,doctor 优雅降级;`init` 只写指定键(非全倒默认)、幂等、拒覆盖不同文件;`set` 点分键按 pydantic schema 动态解析(schema 不复制进 skill)、bool/int/path 严格强转、round-trip YAML 保留注释;未知键与疑似密钥键(token/cookie/api_key/secret/password)写前即拒、指向环境变量。设计哲学落点:schema 校验/原子写/密钥禁令是业务约束落 CLI,"自然语言→点分键"是内在能力**不编码进 skill**;`config-setup` 只承载不可推导的外来规定(config.yml 单一权威、密钥走 env、仅核心配置、不覆盖)。**③ 工作队列**——`project-backlog` skill 管 `planning/BACKLOG.md`(增/改/查/报工作项,稳定 ID)。删 `plugin.json` 死 `userConfig` 块(三字段被 `/plugin` UI 收集却无人读)。新增 `ruamel.yaml` 依赖(round-trip 保注释)。skill 数 12→14,routing 10→17(+config first-run/change/query)。测试 123→145(+config.py 原语 13 + config CLI 契约 9)。后续押后:Step 0 CLI bootstrap(launcher + `${CLAUDE_PLUGIN_DATA}` venv + 改 SessionStart hook,需批)记 BACKLOG WI-008;project-backlog 增强(ProjectStatus 视图/外部发现扫描/文档同步)记 WI-009。
