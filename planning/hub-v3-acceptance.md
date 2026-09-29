# Hub v3 发布前验收单（更新至 2026-09-29）

状态：**0.29.0 已发布并安装；功能与真实迁移验收未通过**。本单记录隔离候选、fixture、只读实盘检查和 test Vault 独立 PDF 样本。2026-09-30 用户明确改为先提交、发布并安装 `0.29.0`，随后才运行本轮产品验收；开发树 `dd161f5`、runtime-only release `e0a0b2f` 均已推送，Codex 插件与 pipx CLI 均已更新为 0.29.0。此决定不把任何 pending 门禁标成通过，也不授权真实 Vault 迁移。
本节以下涉及 `0.28.1` 安装态的记录为 2026-09-29 历史快照。旧 `0.18.0` LaunchAgent 已停止，固定端口 `23128` 当时无监听。未知进程不得因端口或名称相似被终止。

**最新用户决策（2026-09-29）：第一项新 v4 候选验收通过。**用户已认可内容与 Canvas
版式，并确认最新版候选的 ZotFlow 链接可用且页码正确；不再把其 GUI 点击列为阻断。
用户进一步确认世界模型旧稿及同等级文件集没有人工撰写痕迹，原则批准调整和处置经只读核实
为机器生成的旧稿内容；不需要逐字段/节点再次人工签字。其他同等级文件集也须先识别边界、
核实机器生成来源并生成精确预览，不能一概自动改动或迁移。该批准不是旧稿已无损迁入的证明，
也不是正式 Vault 写入批准。旧稿原件必须完整保留；当前字节 digest、科学来源核验和精确 Field
diff 仍属第二项技术门禁。当前 test Vault Canvas 字节 SHA-256 `0f7f240d…` 与旧审议索引所记 `522011b4…`
不同；后者不可当作当前候选的批准摘要，第二项须重建字节绑定。第二、第三项现在并行
进行验收检查，仍不得 apply、发布或更新已安装插件。

开发树已加入 Vault ID 路由；最新完整 unit/contract/eval/integration 回归为 **1089 passed**。
真实注册 Source 的服务端动作和系统打开 canary 已到达正式科研 Vault Reader，但开发版 Hub 页面
真人连续点击仍未验证。World Models 的 provider+Field 联合 CAS journal、条件恢复和停写窗口
仍未完成，不能据此写入正式 Vault 或通过发布门禁。

2026-09-29 第二项只读复查：世界模型仍以 `01-Paperlist.md` 为入口，导航 43 项，旧端口
链接 122 处（Paperlist 43、挑战树 44、技术树 35）。当前 Field 事务预览只拟改三份
导航 Markdown 与新 manifest，报告两项 JEPA 成对 cutover 冲突；没有纳入分析三件套、
39 份平铺 `paper_assets` 或单篇目录搬迁，故不是完整可批准计划。全 Vault 的新预览为
6 个候选 Field、291 篇外部 ZotFlow 笔记、8 篇普通未映射 Markdown、168 条旧链接；
旧 5/305 快照已漂移，原因未判定。最新 V-JEPA 2 候选 bundle/sidecar 与 Advanced Canvas
metadata 共存时仍通过 conformance；只有旧 cutover 索引的原始 Canvas 字节绑定过期。
Zotero Local API 的过滤批注查询现查到 V-JEPA 2 附件下 2 条正式第 1 页高亮
`EHTAYL2L` 和 `SSL5GQA5`。用户确认前一条最初在 ZotFlow Library Reader 创建，
并已手动完成 Zotero 原生阅读器编辑→ZotFlow 的反向同步验证；前一条 key 和备注在
Local API 与 ZotFlow 来源笔记一致。本次**手工双向往返**通过，不推断自动持续同步。
从本机附件生成 test Vault 独立快照（48 页、2 条高亮），原附件 SHA-256 未变；macOS
Preview 实际打开该副本，显示高亮，侧栏“高亮标记和备注”列出两条备注。此样本的独立
PDF GUI 阅读验收通过；ink/image 等其他类型及旧 Collections 错误现况仍待核。
旧 0 条/404 记录仅为历史快照。

隔离临时状态的真实 Source/Hub 卡片 canary 又证明：注册 Source 指向 Vault
`02-科研技术文档`，实际 Zotero Local API 附件、Obsidian CLI 本机模式探针和 PDF 字节复验通过，
V-JEPA 2 卡片以 ZotFlow 为首选，HTTP 动作返回 200，系统打开返回 `opened=true`。
Obsidian CLI 确认正式科研 Vault 的活动视图为 `zotflow-zotero-reader-view`，标题为
`2506.09985.pdf`，视图身份精确为 `libraryID=17685951`、`itemKey=QR4ZU2S9`；
Obsidian GUI 目视确认该 Zotero Reader 渲染论文第 1 页、共 48 页。注册 Source 的
服务端动作和系统打开到正式 Vault Reader 已通过隔离 canary。真人从开发版 Hub 页面连续
点击到 Reader 的 GUI 验收仍未证明。旧配置 `documents` 与 CLI `Documents` 的
大小写差异曾使字符串路径比较误拒；开发树改用严格解析后 `samefile` 目录身份验证，
并已用旧小写路径重新跑通相同的隔离真实卡片 canary，其他目录继续拒绝。
临时服务/状态已清理，正式配置、Vault 和原附件未写入。

第二项又完成两项开发版安全收敛：普通 Scholar-owned Markdown/Canvas 可以在本地审议
源→目标搬迁并条件恢复，受管分析三件套和 ZotFlow Source Note 则继续拒绝；v4
`commit-bundle` 现在检查 Vault inode、完整 provider snapshot CAS、三类目标路径归属
和 Zotero key。该轮完整 unit/contract/eval/integration 回归为 **1041 passed**；最新总数见上方，已增至 1089。上述检查
不能代替用户侧指定 Source registry bootstrap/bind 命令或 provider+Field 的单一提交 journal，因此正式
World Models Field 仍未放行。39 份现有论文资料笔记、4 篇缺笔记及目标目录规则已写在
`test` Vault 的 `Scholar Workflow 实验/世界模型-Field-零写入映射审议.md`；这不是实际
Field 事务摘要，也没有修改真实 Vault。

## 已取得的证据（下表保留各日期的历史快照；当前门禁以上方决策及下方清单为准）

| 验收项 | 当前证据 | 边界 |
|---|---|---|
| 受管 HTTP 与身份 | 最新隔离 0.29.0 wheel 在临时状态目录、动态端口完成 `start/status/doctor`、`/api/v3/identity`、v3 Directory、`/hub/` 和 `stop`；停止后 status 为 stopped。临时环境已清理 | 不改变用户安装；这不是正式 release 或安装 |
| cmux 关闭与重连 | 同一最终 wheel 的 `open-hub` 自动选择临时 workspace，Papers/Fields/Projects/Tools 显示 305/0/0/0；论文卡片一跳打开 Zotero attachment PDF。关闭 workspace 后 HTTP PID/端口不变，`/hub/` 与 Directory 仍 200，只有 `cmux_launches` 失效；先前 restart/new-generation canary 亦通过 | 测试 workspace、隔离服务已关闭；未验证真实 Field/ZotFlow 写入 |
| Codex 受控执行路径 | 隔离 wheel + 临时 Git target + fake Codex 完成 Hub UI → 指定 cmux workspace terminal → worker → `TaskRun=succeeded`；虚拟环境 Python symlink 故障已修并有回归测试 | 未运行真实 Codex、未消耗额度；真实 worker 门禁仍开 |
| Papers 与 Field 预览（旧快照） | Zotero Papers 305 项；此前世界模型零写入预览有 5 个候选 Field、43 个导航文档、305 篇外部 ZotFlow Source Note 和 1 个 JEPA 冲突；43 个不同旧 PDF key 当时经 Local API 确认为个人库附件 | 2026-09-29 最新只读复查见上方：6 个候选 Field、291 篇外部笔记、2 个 JEPA 冲突；不能用此旧快照批准 Field 迁移。用户已撤回新首页，Paperlist 保留为目录入口 |
| 旧链接安全 | 世界模型 122 处、全 Vault 168 处固定 23128 链接已只读定位；缺失/组库/非 PDF/未下载附件会被迁移校验拒绝 | 真实链接逐字节未变；迁移仍需单独 digest 批准 |
| PDF 批注副本（旧 fixture） | highlight/note/underline 样本独立导出，原 PDF 哈希不变；pypdf、Poppler、PDFKit/Quick Look 可解析/渲染；image 批注明确拒绝且无假完整输出 | 此行是此前的 fixture 记录；最新 V-JEPA 2 Preview 和手工往返验收见上方，ink 真实样本仍缺 |
| JEPA 无损审计 | 旧 Markdown/Canvas 194/194 path/marker 对齐、无悬空边；25 个独立 Evidence 节点及 5 个多余 challenge/contribution 节点已定位；IR v2 支持逐点证据与准确反链。新隔离审议包逐 ID/哈希对 194 个旧字段、1 段未标记内容、194 节点和 193 条边给出拟议处置；15 条多目标拆分、25 条 Evidence 去向及 11 个混合目标/30 条推断路径均有逐项提案。本机 PDF 已目视复核 Figure 2/3/5/6/7/16、Eq. 1–5 及 Table 1–8/20 的指定页；三种不同的“16 秒”口径已分开。草案 IR v2 为 15 claims/49 points，生成 Markdown 与 21 节点/20 边 Canvas，正式 `validate_bundle` 返回 `ok=true`、0 findings，sidecar 与该草案基线一致 | 用户已原则批准调整/处置经核实为机器生成的旧稿，不需逐条人工语义签字；这不表示内容已迁移或来源已核实。旧/新 digest 须重绑，科学来源与剩余图表/声明仍待核，草案 sidecar 不是旧内容迁移 receipt。这些私有材料不是可提交的真实 Vault cutover，原文件未改 |
| JEPA v4 审议候选（2026-09-28 旧快照） | 当时完整候选放在 `test/Scholar Workflow 实验/V-JEPA 2/v4-审议候选/`，含人类 Markdown、可编辑 Canvas、IR、sidecar 和旧稿逐项索引；22 claims/46 points、58 text 节点/57 边。此行的旧尺寸、链接、字节和 985 项测试数只代表当日快照 | 最新候选的内容、Canvas、ZotFlow 页链已由用户验收；旧稿逐项去向及当前字节摘要转入第二项 Field 迁移安全门禁，真实 Vault 未改 |
| 论文解析树 v4 版式 | 生成器直接输出的 `test` Vault 完整样张含 45 个可编辑 text 节点、44 条有效连线；Advanced Canvas 7.1.0 前台显示、claim 文本编辑和正式 bundle conformance 已验证。用户认可当前功能与美观，已将参考图四分支树固定为 `analyze-paper` 新分析的版式基线 | 样张文本并非论文事实验收；普通 Canvas 无 Advanced Canvas 时的具体视觉回退、真实 V-JEPA 2 的新分析正文及来源核验仍未通过；不因此放行 Field 迁移或发布 |
| 原文深链与 cmux 阅读边界（旧快照） | 用户撤回新世界模型综述首页，保留既有 Paperlist 作为目录入口；IR 结构/渲染测试覆盖 PDF 物理页、可选批注 key、Vault 块链接及 Canvas→正文反链；2026-09-28 用户已逐一确认五条 ZotFlow 实验链接打开物理页 4、5、6、15、44 | 最新 v4 受管候选链接也已获用户逐一验收；页级定位不等于每条论据的科学归属或逐句定位。cmux PDF 只读预览不能冒称批注写回 |
| Field 中断恢复 | 单 Field 统一事务已有私有 journal、快照回读、显式条件 `recover`、外部冲突拒绝及故障注入；旧 link-only 命令另外要求停写断言与交互确认 | 外部非协作 writer 的最后 CAS→rename 窗口不具跨程序硬原子性，操作者必须实际安排停写 |
| 继续实现（fixture-only） | 本地操作员 `field-transaction plan/legacy-preview/legacy-stage/apply/recover` 已接入 HTTP/CLI：cutover 与完整 Field 各有摘要，受管 Markdown/Canvas/sidecar、home/navigation、manifest、host registry、旧链接同组 journal/条件恢复；30 分钟审议窗口，过期与重启 fail-closed。旧网页确认阻断任何未经审议的受管分析；未修改的现有 v2 分析三件套也须通过 bundle/sidecar conformance。Field 首页和导航只接受 Markdown，v1 写入/上传/执行入口返回 410；旧 link-only apply 需停写断言和交互确认。新增纯合成规模回归覆盖 194 个旧 Markdown 字段、194 个 Canvas 节点/193 条边及遗漏/错误映射拒绝。外部 owner 修复后的完整 unit/contract/eval 回归 **933 passed、11 条第三方/运行时弃用警告**；本轮改动路径的 Ruff、Hub JS 语法与 diff check 通过 | 这只证明 fixture 路径和机械守恒，不能代替真实 JEPA 语义或独立真人审批。同系统用户 operator credential + CLI 确认不构成独立真人审批证明。真实 Vault 未写入，JEPA 完整语义候选仍缺；全库 Ruff 的 81 项与 HEAD 完全相同、无本轮新增，但不能声称全库 lint 通过 |
| 运行包边界（旧构建快照） | 较早的 0.29.0 wheel/sdist 隔离边界检查为 81/96 项，均不含 planning/tests/根 agent 规则；wheel 未发现个人路径或密钥赋值字面量。彼时从开发树重新构建的临时 wheel 完成 schema-3 Directory、临时 Field 首页/导航、服务进程 fake Obsidian CLI PATH 和 Hub 卡片动作 canary。外部 owner 修复后再次新构建的 wheel（SHA-256 `a67fa43281612f787ade83ddd8c29b517e46fc7b8eab92a6ccaa5fbebe082e2d`）又以合成 Vault 黑盒验证 Source Note 不入 Field 且 manifest/读取/写入均拒绝接管；隔离 Hub start/status/doctor/stop 正常。临时服务、页面和目录已清理 | 该 wheel 与仓库现存 `dist/` **均已过期**，不含此后 v4 提交安全修复与普通 Field 搬迁。最新真实 Source/Hub HTTP canary、手工双向同步和 GUI 证据见上方；仍未构建最终 release artifact，工作树未提交，未安装新版本 |
| ZotFlow 诊断（2026-09-27 旧快照） | Obsidian CLI 已启用；科研 Vault 的 ZotFlow 1.6.6 本机 storage 模式与 V-JEPA 2 的 48 页本机阅读已验证。当时 Local API 尚未返回测试批注 | 最新过滤查询已有两条高亮，用户确认手工双向往返。`Pull Collections failed: net::ERR_CONNECTION_CLOSED` 是否仍发生尚未复查；Web API Key 未交给 Scholar Workflow/agent |
| 无云端 PDF 阅读门禁 | 开发树已增加 Zotero 主动作、ZotFlow 1.6.6 白名单与非秘密本机模式/附件探针，以及两类动作点击时 Local API 身份、本机存在性和实际字节摘要复验；真实注册 Source Hub HTTP 动作及 OS open 已返回成功，正式科研 Vault Reader GUI 显示 48 页；V-JEPA 2 的独立 Preview PDF 样本也通过 | 从开发版 Hub 页面真人连续点击的 UI canary 仍未完成；本机开关打开不等于批注往返成功，更不能改变 Zotero 独立的后台 File Syncing 设置 |

## 发布前门禁

1. **已通过：**用户完成新版 JEPA v4 候选的内容、Canvas 与 ZotFlow 链接验收，并原则批准处置经核实为机器生成的世界模型旧稿；不要求逐字段/节点人工签字。其他同等级文件集只有在只读识别边界、核实机器来源并展示精确预览后，才可按同原则调整。此项不宣称旧稿已无损迁入，也不授权真实 Vault 写入。
2. **未通过：**世界模型单 Field 迁移仍须完整保留旧稿原件，并核实当前字节 digest、每项科学来源和机器生成边界。原则批准意味着无需再逐字段请求人工语义签字，不免除机械守恒报告、精确 diff 与来源核验。已有 39 篇资产笔记／4 篇空缺的零写入映射提案，但尚无 Knowledge provider 与 Field 文件的统一 CAS journal、可信条件恢复或外部 writer 停写窗口；受管分析三件套和指定 Source provider 绑定也未进入可提交事务。须重建与当前旧/新字节一致的索引及精确 Field 预览，核对 home/navigation、JEPA 全文/Canvas、122 处旧链接、每篇文件夹归属和 manifest/host registry 变更，并实现联合事务后才可登记或修改真实 Vault。recovery snapshot 不是 verified backup，旧的 registration-only preview 或过期索引不能代替最终计划。
3. **V-JEPA 2 样本通过，产品集成仍部分通过：**用户确认 ZotFlow→Zotero 创建和 Zotero→ZotFlow 编辑的手工双向往返；过滤 Local API 与 ZotFlow 来源笔记保有同一 `EHTAYL2L` key/备注。新建的独立副本在 Preview 中显示两条高亮，侧栏列出两条备注，原附件哈希未变。注册 Source `02-科研技术文档` 的隔离 Hub HTTP 卡片动作返回 200，系统打开返回 `opened=true`；Obsidian GUI 在正式科研 Vault 确认 ZotFlow Reader 打开 `2506.09985.pdf`（`libraryID=17685951`、`itemKey=QR4ZU2S9`）第 1 页/48 页。服务端 Source 路由及系统打开 canary 通过，但真人从开发版 Hub 页面连续点击的 GUI 验收仍未完成。旧 `Pull Collections failed: net::ERR_CONNECTION_CLOSED` 在当前有限 Obsidian console/错误缓冲中未见近期复现，但不能推定永久解决；另有不同条目的 Source Note 打开错误，其 key `29EGKLK2` 在 Zotero Local API 当前返回 404，应与 V-JEPA PDF 路径分开诊断。ink/image 等未取得真实样本的类型边界亦保留。Web API Key 只能留在 ZotFlow/Obsidian SecretStorage，不得交给 Scholar Workflow/agent。快照不是 Zotero 实时共编或可导回的第二事实源。
4. 最新 wheel 的生命周期 canary 已过，但 Field/任务完整真实使用仍须按明确门禁验收。真实 Codex 会消耗账户额度并留下线程记录，需单独选择是否执行。已有同用户 operator credential 只是一种本机信任边界，不证明独立人工审批来源。
5. 所有证据、剩余限制和候选结果交用户批准后，才把当前未提交的验收修复落到 main、生成正式 release 分支、推送和更新本机插件。不得提前切换服务或停止未知进程。

## 不变边界

- 不自动升级 Obsidian、安装/卸载外部插件、迁移其他 Vault/项目或执行真实训练任务。
- Knowledge 与 Project 只显式复制，不建立隐藏同步；cmux workspace 只路由窗口，文件权限来自注册根和目标。
- 本验收单会随最终候选测试结果更新；`planning/HANDOFF.md` 和 `planning/BACKLOG.md` 保留阶段状态。
