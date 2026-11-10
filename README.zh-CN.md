# scholar-workflow

面向 Claude Code 与 Codex 的科研项目资料管理插件。它关联一个项目的代码、相关论文、知识笔记、
实验与成果，让人和 agent 能理解、查找和调用资料，而不把所有内容搬到同一个系统。
论文分析、文献树、入库与实验档案由插件维护；阅读、编辑和执行继续利用 Zotero、Obsidian、
Notion、cmux 和外部 Codex 的原生能力，不另建工具控制面。

当前0.51.0发布范围：保留科研Skill、已认可格式和原生工具薄适配，退役旧Hub网站，停止扩建独立探索网页。
知识按完整论文／Blog／文档资产单元及明确上下文管理，区分管理、分析、查看与编辑。
见[资产单元](references/asset-units.md)与[项目Skill分层](references/project-skills.md)。
多维查看／编辑方式继续讨论，已有记录保留。0.51.0新增第一期推荐页和多agent统一提交入口。

本次后续修复将原目录设备号恢复与Canvas编辑器保存确认分开：不改文件，明确显示尚待确认，
导出仍需完成单独的元数据确认。

[English](./README.md)

## 后台推荐与普通本地地址

外部推荐agent和管家agent通过共享CLI读写同一数据池，无需打开网页或HTTP服务。
执行/定时归外部宿主。人类运行 `scholar-research recommendations start` 后，
用它输出的普通本地URL打开即可；`status`查询地址，`open --no-browser`只输出URL。
支持多个浏览器/cmux窗口，无需URL凭据或已登录窗口。关闭窗口不停止服务，
`stop`关闭HTTP也不影响agent的CLI操作。刷新查看外部agent的新结果。

## 推荐页面——第一期（0.51.0）

多个agent通过同一JSON/CLI入口提交论文、项目主页和Blog。首页紧凑显示领域/任务/类型筛选、
原文及项目链接，以及带来源和采集时间的原始平台数据；展开条目后阅读完整摘要译文和相关链接。热度只列数据，
不生成综合分数或评价。定时调度继续由各agent的宿主持有。

```bash
scholar-research recommendations schema
scholar-research recommendations submit --input recommendations.json
scholar-research recommendations open
scholar-research recommendations status
scholar-research recommendations stop
```

个人候选池初始为空。让agent使用`recommend-papers` Skill即可发现统一提交入口。
使用`recommendations --profile test`访问独立测试池。审阅后选择并导出清单，再交给
`ingest-resource`；导出不等于入库。0.52.0开发候选另提供预览后明确确认的Zotero书目入库，
范围见下文。具体格式见[统一入口契约](references/recommendation-intake.md)。
知识单元、原生阅读器和agent执行仍由各自工具持有。

## 架构

宿主 LLM 负责理解、分类、排序与推荐;确定性 CLI(`src/scholar_workflow/`)负责可测试的文件和
Zotero 操作。Zotero 适配器只连接 Zotero 10+ 的回环 Local API;其他对外访问均受限且显式声明——
`apply` 从 arXiv 下载 PDF,独立的 `bin/notion-project.py` / `bin/recommend-papers.py` 各自访问其
声明的服务。**Zotero 是权威主库** —— 元数据、存在性核验、索引全文与新增性写入使用官方
Local API。主题召回由 Local API 全字段/全文 quicksearch 加宿主模型排序完成,不需要 MCP server
或本地向量库。破坏性动作仍需批准。**Obsidian** 保存知识笔记与派生索引;**Notion** 保存可选投影。

非论文研究动态由独立的 `scholar-research` 获取；本地 `scholar-workflow research` 命令不抓取网站。
可用 [track-research](skills/track-research/README.zh-CN.md) 管理所选研究者博客、机构网页、
代码发布及模型列表：`research sources list/register` 查询或登记，`scholar-research check` 检查一次，
`research updates/mark` 阅读并标记动态。首次建立基线，失败保留诊断，选中不等于入库；
不要求 Hub、源码目录或定时服务，不下载模型权重。动态跟踪已随0.48.0发布安装，并完成单个RSS来源的安装态功能检查；其他渠道、人工评鉴和入库交接仍分别待验。

### 内容与项目归属

多维研究定位的数据由[explore-knowledge](skills/explore-knowledge/README.zh-CN.md)保留，
查看与编辑方式继续讨论，不默认启动旧网页。现有`.scholar-workflow/exploration.yml`、
可扩展维度、条件记录、证据和保存查询不改；显式CLI查询／导出仍可使用。
导出只向stdout输出可读导航，不修改论文单元。精确数据接口见[运行契约](references/knowledge-exploration.md)。

0.50.0源码候选补齐论文、Blog和技术文档的完整单元引用。只读查看可用
`knowledge list --asset-units --source-id SOURCE --field-id FIELD --language zh`；
`--paper-units`仍只列论文。新引用经实际登记导入，旧未登记记录保留只读并明确标为未核实。
当前0.49.0安装版尚无该选项；这不增加网页、复制正文或自动采用旧资料。

- **Knowledge System** 以人类可读 Markdown 为正文。论文、重要技术文档和 Blog 是原子资源；
  分析、Canvas 和附件是显式归属的附属产物。新生成的全文分析采用原图的 Abstract、
  Introduction、Method、Experiments、Limitation 完整框架；旧任务／输入／分步流程／输出／边界格式仅供
  历史内容兼容读取。证据与对应论点或逐点陈述放在一起。
- **Project System** 保存稳定 `project_id`、宿主中立的源码/config profile，以及彼此分离的
  Run、Attempt、Target、成果 promotion 和备份记录。没有独立校验过的第二份副本就不能称为备份完成。
- **项目资料上下文** 用独立、可选的 `project-context.json` 明确关联代码、论文、笔记、实验和成果，
  并说明每份资料为什么与项目相关。它不复制正文、不启动工具，不要求 Hub 或 workspace 登记。

项目引用不改变资料原有归属。显式复制是另一种操作：副本获得目标身份并独立演化；两者均不建立
隐藏同步、跨域覆盖或级联删除。

对于明确选定的官方网页，0.47.5补齐真实Zotero书目与带段落锚点的 `Source.md` 归档：
`knowledge document-plan` 预览、`knowledge register-document` 登记单个新归属，不要求PDF；
沿用同目录内完整正文与五分支分析树。未公开技术细节不从另一篇论文补写，详见
[网页原文登记与分析](references/document-registration.md)。

0.43.0 起，schema 2 的领域清单可以保留指向既有知识对象的引用及用途。
`knowledge list --resolve-references` 可选显示声明归属和文件诊断，不打开阅读器或创建副本。
schema 1 保持原样；`knowledge reference-plan/reference` 提供单条增删预览与确认，
只改引用方清单，不改目标内容。人工导航评鉴与命令契约验证分开，详见
[知识目录登记契约](references/knowledge-registration.md)。

0.43.0 另可用 `knowledge list --paper-units --source-id SOURCE_UUID --field-id FIELD_UUID`
组合单个领域已有论文包的资料、分析、Canvas 和笔记入口，提供安全的 Obsidian 链接及
缺失诊断。不替换旧论文表、不复制正文、不写文件，详见
[论文单元导航](skills/build-literature-tree/references/field-paper-units.md)。

0.44.0 起，可请 `build-literature-tree` 将选定主题整理为01完整论文列表、02时间线文献树、
03放射技术路线树和04放射挑战洞见树。安装skill自带纯布局工具与两份限定作用域的CSS；
原生样式需Advanced Canvas及启用两份snippet，具体见
[设置与输出格式](skills/build-literature-tree/references/field-library-format.md)。
0.44.2起明确复现模范库的紧凑呈现：02标题只放短名年份，03/04论文叶端一句做法加导航；
详细条件与证据留正文，不逐卡重复诊断，开发材料不混入领域阅读目录。
已有论文归属和单篇分析格式不变；新主题原生显示、人工评鉴仍独立验收。

0.44.3起领域库规范以用户指定的“模范知识库”为唯一蓝本：该有的必须有，没有的默认不加；
后续目录、正文和图形格式必须一致。新论文包使用 `resources/<目录段>/`，已有归属原位保留。
一致指呈现格式，不照抄内容配额；分析深度、图表和证据数量依实际论文决定，不凑图或删必要材料。
正常安装、原生显示和各主题人工评鉴与源码验证分开记录；详细要求仍由上面的格式文档唯一持有。

0.43.0 的 `literature-preview --input evolution.json --format md|json` 可零写入预览逐贡献
novelty、位置归属及带证据入口的技术取舍，不读原资料；
最终可编辑演进图、真实科学内容和外观人工评鉴分别待验，见
[演进预览契约](skills/build-literature-tree/references/evolution-preview.md)。

0.43.0 新增 `review-experiments` skill，把选定 Run/Attempt/Artifact 整理为可读、
带来源链接的比较，不运行实验、不新增结果数据库。明确要比较的 Run、结果 Attempt
和指标即可；失败、重放和缺失证据仍保留。详见[实验复核](skills/review-experiments/README.zh-CN.md)。

0.43.0 新增 `organize-project` skill，用内部 PROJECT.md 展示最新情况、带源码依据的
模块图、代码/实验/论文直接入口，以及 PROJECT 或 SCHEDULE 中唯一维护的详细计划。
README 仍负责对外展示；此能力独立于初始化和简短资料清单，
详见[内部项目入口](skills/organize-project/README.zh-CN.md)。

### 项目资料与已收集实验总览

源码候选新增可编辑的`--selection-file`（YAML/JSON）：选择指标、配置、报告和图表，模型载荷
留在源端；原始Run/Attempt/产物记录保持不变。接收、读取、更新和恢复沿用同一清单，必需成果
若明确延后则显示尚未收齐。现用0.49.0尚无此入口，实际使用先核对安装版帮助；这不等于已实现
远端自动导出或SSH拉取。详见[结果选择与交付](references/experiment-result-selection.md)。

已收集的子项目实验，用正常安装且 `scholar-workflow experiment --help` 中有 `collected` 的版本：

```bash
scholar-workflow experiment collected --project-root /path/to/parent --language zh
scholar-workflow experiment collected --project-root /path/to/parent --child-project-id CHILD_UUID --json
```

它只读本地档案，不连接子项目服务器。配置／条件与记录结果同处一行，缺失或损坏记录保留。
需要保存时，显式存到总项目根目录以保持相对链接可用；它不解释指标意义或排名。
预览、登记、首次接收、四摘要更新及显式提交／回滚见[项目管理契约](references/project-management.md)。
使用前确认正常安装版本的帮助确实列出相应命令；源码开发和测试通过不代表已经安装。

远端子项目代码可用新增的`execution-code`引用，只保留子项目身份与相对代码位置，不留日常开发副本。
`project remote-code-plan`按明确选择的已有Target和服务器登记预览位置；它不连接、不核验远端Git、
不启动编辑器。使用前检查安装版本的命令帮助，细则见[资料清单契约](references/project-context.md)。

最简源码留存先用`project code-recovery-plan`检查明确提供的本地自包含Git bundle，
再用返回的计划摘要显式执行`project retain-code`。它覆盖所选子项目已收集Run的源码提交，
同内容只保存一份bundle和小型核验记录，不生成开发副本、不从服务器下载、不收集未提交内容，
也不认证真正备份。具体命令、缺口和中断处理见[恢复材料说明](references/project-management.md#selected-local-git-recovery-material)；
使用前确认正常安装版本确实提供这些命令。

对于已经初始化的项目，先输出空清单模板，选择实际相关资料后，显式保存为项目根的
`project-context.json`。模板命令本身不写文件、不猜论文、不创建强制首页：

```bash
scholar-workflow project context-template --project-root /path/to/project --language zh
scholar-workflow project validate-context --project-root /path/to/project
scholar-workflow project overview --project-root /path/to/project
scholar-workflow project overview --project-root /path/to/project --json
scholar-workflow project overview --project-root /path/to/project --context-file project-context-candidate.json
```

默认总览以人类 Markdown 输出到终端；需要时显式保存为项目根下的文档，相对链接以项目根为基准。
本地缺失和不安全引用会报告，不跟随符号链接；外部对象未联网核验时明确标为“未核验”。
不需要插件配置、网页服务或模型配置页。字段、来源归属和阅读器入口见
[项目资料契约](references/project-context.md)。
可选候选文件参数只预览项目根一个 JSON 声明，明确标为未应用；不会替换生效清单或批准覆盖。

0.42.0 起，`project overview --resolve-knowledge` 按已登记声明核验所选知识对象，分别说明正式归属、
文件可用性和仍未核验的阅读入口。不搬动内容、不建立同步，默认输出保持。
正常安装后先核对 `scholar-workflow --version` 和 `project overview --help` 再使用新选项。
合成验证已完成；安装态与人工导航评鉴仍分别判断，不能用源码测试替代。

### 不依赖 Hub 的知识文件夹预览（0.34.0）

运行 `scholar-workflow knowledge preview /所选文件夹绝对路径 --language zh`。
它列出候选/已有领域、完整导航、未映射正文、外部 writer 和冲突；`--format json` 输出独立机器记录。
预览零写入，不登记、不创建首页、不启动服务，也不代表内容或 Canvas 通过验收。
Source/Field 的正式登记与分析成对提交仍是另行审议的操作。

### 直接在 Obsidian 打开登记目录内的笔记与 Canvas（0.37.0）

用 `scholar-workflow knowledge list --format json` 查看 `source_id`，然后运行：

```bash
scholar-workflow knowledge reader SOURCE_ID --language zh
scholar-workflow knowledge open SOURCE_ID '相对目录/笔记.md' --language zh
scholar-workflow knowledge open SOURCE_ID '相对目录/解析树.canvas' --language zh
```

所选目录可以只是 Vault 的子目录；父 Vault 只决定 Obsidian 打开位置，不扩大文件权限。
不需要 Hub、workspace 或 Obsidian CLI。系统接受打开请求不代表画面/人工评鉴通过，
也不是论文正式归档。ZotFlow 本机 PDF 能力另行检查。

### 不依赖 Hub，登记单个知识领域（0.36.0）

0.39.0 起支持便携归属复现：`knowledge reproduction-plan` 导出明确归属；
复制并显式附着 Source 后用 `knowledge restore-plan/restore` 恢复缺失 provider。
输入、拒绝覆盖及阅读器/来源/人工待验收边界见[复现契约](references/knowledge-reproduction.md)。

0.41.4 起，原登记路径与 inode 相同、仅设备号变化时，可先运行
`knowledge rebind-plan --source-id SOURCE_ID --format json`，审阅后再用
`knowledge rebind --source-id SOURCE_ID --approved-digest 确认摘要 --language zh`。
它只恢复主机绑定和派生 snapshot revision，不改正文或归属；不同目录和过期输入拒绝。
中断续行与明确限制仍以同一复现契约为准。

预览后选择一个候选相对目录（单个子目录为 `.`），运行：

```bash
scholar-workflow knowledge registration-plan /所选目录绝对路径 --field-root . --language zh
scholar-workflow knowledge register /所选目录绝对路径 --field-root . --approved-digest 确认摘要 --language zh
scholar-workflow knowledge list --language zh
```

先审阅导航与摘要，再确认；文件或登记状态变化后旧摘要失效。只登记所选 Field，不创建首页或
改论文。含旧分析、旧端口链接的目录仍需联合迁移审议。已有便携清单改用 `--existing-source`，
只登记到本机，保留全部身份和清单原字节。详见[登记契约](references/knowledge-registration.md)。

### 直接检查已有论文资料包（0.35.0）

0.38.0 起的单篇归属入口见[论文登记契约](references/paper-registration.md)：
`knowledge paper-plan/register-paper` 使用已登记 Source/Field，先核 Zotero 身份，再按
摘要创建新的资料笔记、归属和导航；中断只能条件续行。它不接管旧包，也不代表科学验收。
目前使用前必须确认安装版本已提供这些命令。
0.43.0 按规范 Zotero 身份核对所有显式登记 Source 的论文主归属，清单缺失时拒绝猜空。
新 Source 经明确登记初始化空清单，挂接旧 Source 不自动补造；恢复方式见上述契约。

```bash
scholar-workflow analysis check-bundle /论文目录绝对路径 \
  --markdown '论文分析.md' --canvas '论文解析树.canvas' \
  --sidecar 'analysis.baseline.json' --require-ir 5 --language zh
```

使用实际三个文件名。入口只读取当前正文、Canvas和sidecar，检查格式、几何、反链及基线一致性，
不重新生成、不登记。`--format json`给出hash和诊断；退出0/7/2分别表示自动通过/不通过/输入无效。
科学来源、阅读器点击和人工评鉴仍是独立事项。

### 可复现项目／实验样例（0.33.0）

在已安装插件根目录运行 `python3 skills/init-project/scripts/example_project.py plan /chosen/new-project`，
再运行同一入口的 `apply /chosen/new-project`，只会准备一个新独立项目。生成的双语 README
说明如何另行提交明确源码、显式本地执行，并从新克隆目录重建。无需 Hub、源码仓库变量或
额外安装系统 Python 依赖，也不打包外部论文。详见[复现契约](skills/init-project/references/reproducibility.md)。
确定性示例不证明科学论文结论，也不替代人类评鉴。

### 保留兼容服务，退役旧网站

当前源码已移除旧Hub网站的HTML/JS/CSS，`/hub/`和`/hub/assets/*`返回HTTP 410。
`open-hub`在启动服务、路由终端或打开浏览器前明确拒绝，不自动跳往尚未决定的多维界面。
已安装0.49.0在新版本正常安装前仍保留旧行为。

目录、health、PDF及受控原生打开的兼容API保留，已有状态和服务管理边界保持：

```bash
scholar-workflow hub status
scholar-workflow hub doctor
scholar-workflow hub stop
```

停止／重启只影响经身份核实的自有服务。本次源码删除不自动停止已安装服务、不删除状态。
论文原生打开见[资料定位契约](skills/find-resource/references/resource-location.md)，
笔记可使用独立`knowledge open`命令；均无需网站。

显式生成独立的Zotero批注PDF副本仍可使用
`scholar-workflow zotero snapshot-annotations ATTACHMENT_KEY --output /path/to/copy.pdf`，
不覆盖原附件、不将副本编辑同步回正式批注。

### 本地Field事务

Field内容事务改为本地调用，无需HTTP服务、浏览器token或cmux。新增Field时先输出完整JSON计划，
把计划保存在所选Source之外：

```bash
scholar-workflow knowledge field-transaction plan --root /path/to/selected-folder --field-root . > REVIEWED.json
scholar-workflow knowledge field-transaction apply REVIEWED.json --approved-digest sha256:PLAN_DIGEST --external-writers-paused
```

已有Source内的未登记Field可改用`--source-id SOURCE_ID --field-root RELATIVE_ROOT`。
计划绑定明确选择、候选改动与原文件字节；apply可跨进程重建并核对完整摘要，摘要过期即拒绝。
仍须交互确认，并先安排外部编辑器／同步程序停写。恢复快照不是真正经过验证的备份。
原有中断journal可通过`knowledge field-transaction recover SOURCE_ID FIELD_ID
--confirm-recovery --external-writers-paused`条件恢复。

受信任的旧分析候选包可做本地只读守恒检查：

```bash
scholar-workflow knowledge field-transaction legacy-preview --root /path/to/selected-folder --field-root . --package-file PROPOSAL.json
```

这不等于stage旧分析；Provider与Field联合legacy-stage仍以依赖错误3拒绝。新增登记不能绕过
受管内容冲突。旧`hub field-transaction`命令提供迁移提示，已有浏览器候选须重新生成明确本地计划。

旧的链接专用命令只用于**已经登记**且不需要重排分析或 manifest 的 Field：

```bash
scholar-workflow knowledge field-migration plan SOURCE_ID FIELD_ID
scholar-workflow knowledge field-migration apply SOURCE_ID FIELD_ID --approved-digest sha256:PLAN_DIGEST --external-writers-paused
scholar-workflow knowledge field-migration recover SOURCE_ID FIELD_ID
```

这个 `plan` 完全只读；每个不同的附件 key 都须通过 Zotero Local API 核实为个人库中可读取的 PDF，
才能批准稳定 URI。条目不存在、组库、非 PDF、不支持的附件形式或 Local API 不可用，都会成为
明确的计划冲突；`apply` 在创建恢复快照或写入前再次核验。`apply` 重新扫描并要求摘要与已验收
计划完全一致，只改 Field manifest 明列的 Markdown/Canvas。未映射文件若仍有旧链接会阻断。
此命令不重排论文分析，也不自动规范化 JEPA 模板。`apply` 还要求交互确认，并由操作员明确声明
Obsidian 等外部写入者已实际暂停；CLI 无法自行证明。多文件替换中断会留下私有 journal；新的
`plan`/`apply` 会先拒绝，须显式运行 `recover`。恢复会校验 journal、snapshot 和当前文件 hash，
仅条件回滚仍符合原/目标状态的本 Field 文件；若有外部修改或快照损坏，则停止并要求人工审查，
不会覆盖外部内容。recovery snapshot 不是已验证备份。不能用这条兼容路径初始化「世界模型」Field。

完整运行期契约见 [`references/hub-contract.md`](references/hub-contract.md)。Field 迁移产生的 recovery
snapshot 不是 verified backup；真正备份仍需要独立介质和恢复演练。
旧 v1 HTTP 的写入、上传和执行动作返回 `410 Gone`；应使用 v3 的 Field、target 和 action 流程，
不能把兼容查询响应当成写入授权。

## Skills

| Skill | 用途 |
|---|---|
| survey-topic | 界定开放式"调研 X"请求的范围,再路由到其他 skill |
| find-resource | 搜索论文、核验身份、定位已有资源 |
| ingest-resource | 导入论文 / 归档技术文档 |
| sync-projections | 重建 Obsidian 索引表 + 同步 Notion 投影 |
| build-literature-tree | 完整论文列表 + 时间线文献树 + 放射技术路线树和挑战洞见树 |
| check-consistency | 跨系统一致性审计(只读) |
| export-annotations | 把某篇论文的 Zotero 批注整理成结构化 vault 笔记 |
| recommend-papers | 多类型研究推荐、统一agent提交与人工审阅选择 |
| track-research | 所选博客、机构网页、代码发布及模型列表 → 增量动态 |
| explore-knowledge | 可扩展多维定位、条件比较、证据关系及完整资产导航 |
| analyze-paper | 把论文详细分析投影为 Markdown + 可编辑 Canvas 文档对 |
| manage-assets | 先查已有记录，再登记和复用自有服务器与知识库 |
| env-setup | 搭建并查阅个人 API-key / SSH 服务器 env-records 台账 |
| agent-collaboration | 在 Claude Code、Codex 或其他可用 agent 之间双向协调边界清楚的任务 |
| init-project | 初始化宿主中立、由 Git 管理且不带自定义 agent/hook 的研究项目骨架 |
| organize-project | 内部 PROJECT、模块图、资料入口与唯一计划（0.43.0起） |
| review-experiments | 只读整理与比较选定实验档案（0.43.0起） |
| config-setup | 初始化、查询和更新插件配置 |

## 本地科研资产

让 agent 查询已有服务器/知识库，或登记你明确提供的自有服务器；它应先读已有记录，
而不是反复让你提供名称和路径。也可直接使用：

```sh
scholar-workflow assets list --language zh
scholar-workflow assets server show gpu-example --language zh
scholar-workflow assets server register --spec server.json --language zh
scholar-workflow assets server check --language zh
```

登记JSON只填写别名、主机、用户、端口等非秘密信息；新密码/token值被拒绝。已有记录复用，
同别名差异更新须带当前版本，查询不初始化、不连接服务器。知识库仍先预览范围再确认登记；
Obsidian已知Vault、已登记Source和论文归属分别报告。详见[资产管理契约](references/asset-management.md)。
学者关注名单和论文来源继续使用推荐系统原配置，本轮尚未纳入资产CLI聚合。

## 环境要求

- **Claude Code 或 Codex**(Codex CLI / Codex app;IDE extension 不加载插件)。
- **Python ≥ 3.11** —— 确定性 CLI 是一个 Python 包。
- **Git** —— `init-project` 创建或核验项目骨架时需要。
- **cmux** —— 只在需要把 Web/terminal/Codex/CLI 窗口路由到指定 workspace 时使用；它不授予
  文件权限，也不是阅读、Vault 保存或已登记项目文档操作的前置条件。
- **Zotero 10+ 且启用 Local API** —— 权威主库。在 Zotero 的
  **设置 → 高级**中启用;不再需要 Zotero 插件或 MCP server。Codex 在沙箱中运行时可能还需
  放行 localhost/网络权限才能访问 23119;在把 exit 3 判断为 Zotero 离线前,应带该权限重试。
- **按功能可选:**
  - **Obsidian + ZotFlow** —— 用于在 Obsidian 中标注 PDF。Hub 会检查 app/plugin 版本与 ZotFlow
    `minAppVersion`，并通过只返回非秘密字段的实时探针确认本机 storage 模式；不兼容时只报告，
    不自动升级 Obsidian。可选 Obsidian CLI 仅用于 ZotFlow 的此项证明，不是 Zotero 主动作的
    前置条件。Zotero Web API 密钥只留在 Obsidian SecretStorage。
  - Notion 集成 token —— 仅启用 Notion 投影时需要。
  - `notebooklm-py` + Google 登录 —— 仅显式选择的文献树 NotebookLM
    批读需要。
  - Scholar Inbox 账号 —— 仅该推荐源需要。
  - 目标 agent 的 CLI 与既有登录态 —— 仅 `agent-collaboration` 跨宿主运行时调用时需要;
    使用宿主原生 agent 工具时不需要。

## 安装

1. **在宿主中安装插件。**

   release 同时提供 Codex 原生 marketplace 元数据与 Claude 兼容 marketplace 入口；
   两者安装的是同一个插件根目录与同一版本。

   Claude Code:
   ```text
   /plugin marketplace add JerryFan012321/scholar-workflow@release
   /plugin install scholar-workflow@jerry-plugins
   ```

   Codex CLI:
   ```bash
   codex plugin marketplace add JerryFan012321/scholar-workflow --ref release
   codex plugin add scholar-workflow@jerry-plugins
   ```
   安装后新开 Claude Code 或 Codex 会话,让 bundled skills 与 hooks 生效。

2. **安装 Python 包**（提供两个 CLI 命令，无需源码目录）：
   ```bash
   pipx install "git+https://github.com/JerryFan012321/scholar-workflow.git@release"
   ```
   包与宿主插件必须来自同一个已发布的运行版本。需要可复现验收时，将 `release`
   替换为发布回执中的已批准 runtime commit。只安装 marketplace 插件不会安装或更新这个包。
   在宿主实际使用的环境中核对：
   ```bash
   command -v scholar-workflow
   command -v scholar-research
   scholar-workflow --version
   scholar-research --version
   scholar-workflow research --help
   scholar-research check --help
   ```
   两个版本都应与已加载插件的 manifest 一致。命令缺失或版本不符时应修正安装，
   不改用源码或缓存中的脚本绕过。版本号一致也不能证明构建相同；验收仍需保留
   runtime commit、命令及解释器路径。开发者可以在 checkout 中使用 `pip install -e .`，
   但这不属于正式安装态验收。

3. **建配置。** 直接在对话中说「配置 scholar-workflow」,`config-setup`
   skill 会替你执行;或手动跑:
   ```bash
   scholar-workflow config init
   # 额外设置可内联 KEY=VALUE,如:
   #   scholar-workflow config init notion.enabled=true
   scholar-workflow config set paper_inbox ~/path/to/download/inbox   # 后续改单项
   scholar-workflow config show                                       # 查看生效值
   ```
   这会写 `~/.config/scholar-workflow/config.yml`(只写你指定的键,非全倒默认值)、校验、
   后续编辑时保留注释。需要时用 `SCHOLAR_WORKFLOW_HOME` 覆盖位置。所选Vault/目录的
   登记使用独立knowledge命令；普通原生阅读无需先登记整个Vault。旧`research_vault_root`仅为迁移候选。

4. **授权 Zotero 写入。** 启动 Zotero 后运行:
   ```bash
   scholar-workflow zotero probe
   scholar-workflow zotero authorize
   ```
   多阶段 PDF 导入请选择 Zotero 弹窗中的 **Always Allow**。密钥存入 macOS Keychain,
   不会打印或写进 config/git;读命令不需要密钥。

5. **按需提供其他凭证**(见[环境要求](#环境要求))。token / cookie 存环境变量或各工具自己的
   登录态,**绝不进配置或 git**。如 Notion:`export SCHOLAR_WORKFLOW_NOTION_TOKEN=...`。

## 更新

两个宿主 manifest（`.claude-plugin/plugin.json` 与 `.codex-plugin/plugin.json`）共用同一版本
（改动见 [CHANGELOG.md](./CHANGELOG.md)）。更新宿主插件后，从同一个已发布的运行版本重装包：

```bash
pipx install --force "git+https://github.com/JerryFan012321/scholar-workflow.git@release"
```

固定版本验收时用已批准 runtime commit 替换 `release`，新开宿主会话后，重复上面的
命令、路径和版本核对。Marketplace 更新和 Python 包更新是两件事，不能相互代替。
你的 `config.yml` 与凭证留在仓库之外。

## 使用

直接用自然语言跟 Claude Code 或 Codex 说,每个 skill 按意图触发;Codex 也可用
`$skill-name` 显式调用,例如:

- *"帮我调研一下世界模型这个方向"* → survey-topic →(推荐 / 查找 / 文献树…)
- *"找 DreamerV3 这篇论文并导入"* → find-resource → ingest-resource
- *"推荐今天世界模型方向的论文"* → recommend-papers
- *"分析这篇论文的方法部分"* → analyze-paper
- *"画一棵从 NeRF 到 3DGS 的文献树"* → build-literature-tree
- *"导出我对这篇论文的批注"* → export-annotations
- *"同步 Obsidian 索引和 Notion"* → sync-projections
- *"让 Claude Code 和 Codex 分工完成这次迁移并整合"* → agent-collaboration
- *"用标准骨架初始化这个项目"* → init-project
- *"根据这些选定资料，整理一份内部 PROJECT 预览"* → organize-project

各 skill 自己的 `README`(在 `skills/<名>/` 下)详述其选项与配置。推荐清单是临时的;你
留下的论文走常规 find/ingest 管线,不经判重不入库。

## 状态与已知限制

插件仍处于 `0.x` 活跃开发期。哪些已稳、哪些仍在打磨:

- **Zotero 10.0.2 实机已跑通:** Local API 已完成 probe、search、collections、持久写授权、
  条目创建、imported PDF 上传、精确 DOI 复用与附件复用。同一 ingest payload 重跑会返回原
  item/attachment，不重复上传。
- **多维交互待讨论:** 保留文件型研究记录与已认可论文包，旧探索网页不再是推荐工作流；
  源码检查、正常安装、原生打开与人工便利性仍分别取证。
- **旧网站已退役，兼容API保留:** 动态服务身份、PDF及原生路由继续受安全边界保护。
  原生工具自行持有配置与生命周期；cmux 只选择打开位置，不授予文件权限。
- **真实数据继续逐 Field 门禁:** 明确选择已登记 Source/Field，在迁移改写前审议当前 preview；
  其他 Vault/项目保持不动，单个样本验收不批准其他 Field 或整库迁移。
- **ZotFlow 可用性只诊断、不自动修复:** 版本不兼容、本机 storage 模式关闭、CLI 无法证明或本机
  PDF 不存在时，Hub 只禁用 ZotFlow 动作并说明原因；不会自动升级 Obsidian、卸载插件或通过
  Zotero Web API/WebDAV 下载 PDF 来补齐本机文件。
- **已实现但尚未真实端到端跑通:** 旧 `build-literature-tree` Mermaid CLI投影（尤其第四层
  `module`）、`check-consistency`。
  当前领域库格式的安装态、原生显示和人工评鉴独立记录。
- **不支持跨运行续跑:** 重跑 `apply` 是全新任务、会把每一项从头下载,不会接着上次的进度。
- **身份安全双层执行:** skill 先预览候选,`zotero ingest` 在创建前再次执行 DOI 或规范化
  title+creators 精确核验。当前 CLI 不暴露破坏性 Zotero 命令;未来若增加仍需审批。

## 开发

发布后的 `release` 分支仅包含运行时文件、Codex 原生及 Claude 兼容 marketplace 元数据与两个宿主
manifest。开发规范、规划文档、测试与评估在 `main` 分支；贡献指南见其 `AGENT.md`，测试在该分支运行
`pytest tests/unit tests/contract`。

### 来源目录与直接书目入库（0.52.0）

不同外部agent先查询同一个本地来源目录，再使用各自harness中的MCP、API或工具。
alphaXiv是其中的重要来源；插件为支持的宿主声明其官方MCP端点。原生连接、OAuth和API凭据
由宿主持有，推荐页不再提供原生工具表单控制台，也不管理alphaXiv API key。

```bash
scholar-research recommendations sources list
scholar-research recommendations sources show alphaxiv
scholar-research recommendations sources context alphaxiv
scholar-research recommendations sources history --source-id alphaxiv
```

本批候选增加[推荐要求](references/recommendation-requirements.md)：在对应推荐源条目中展开查看和编辑，
不再单列“推荐要求”页面。agent用 `scholar-research recommendations requirements list --source-id ID`
查询该源要求，再通过同一`show/save`入口读取或修改。正常新记录填写已登记的来源；旧无归属记录
仍可查询和查看历史，不自动猜源或迁移。
内容由实际任务决定，不预填筛选标准；不同任务明确选用要求及版本，详情保留当时文本。
保存不自动启动推荐，既有记录不会被新要求改写。该增量已随0.52.0发布。


新增来源、管理备注、研究者建议和外部操作回执均见[来源目录契约](references/recommendation-sources.md)。
回执明确标为`agent_reported`，用于跨会话交接，不冒充独立核验、实时连接或云端账户真值。
各agent保留自己的producer身份，按统一入口提交已核元数据、完整摘要译文或有来源的总结。

首页保持紧凑；展开条目即可阅读完整内容、原文、灵活附件及推荐来源。推荐页不启动agent或模型，
论文单元的正文、Canvas、证据与图片保留原格式。

在卡片审阅并选择后，点击“加入Zotero”，选择分类、预览并确认。
完成以实际条目及分类读回为准；当前直接执行范围为Zotero书目，PDF和Vault完整单元均标明
`not_requested`，继续按既有Skill单独完成。运行细则见[alphaXiv](references/alphaxiv-source.md)
与[推荐入库](references/recommendation-intake.md)。

## 内容、文风和报告交付

`content-and-style`统一维护内容解释、中文文风、字体和交付要求；`create-report`负责报告用途、
对话指定载体和人工评阅，按需逐层引用共用规范。论文正文/Canvas、领域知识库和实验格式仍归原业务。
推荐有完整作者摘要时全文翻译；缺摘要时基于正文写完整简介，并引用共用文风。主标题简洁，出处折叠。
`recommendations revise-content --input FILE`按精确revision修正文案；`content-history`读回署名历史，
不因此增加推荐次数，也不代人评分或入库。


## 推荐源插件（开发中）

设置→推荐源增加版本化来源包的新建、导入、编辑、导出和启停；agent用
`scholar-research recommendations sources guide SOURCE_ID`读取操作说明、推荐要求及续接上下文。
插件不接管宿主MCP授权和执行；新增源无需修改核心或页面枚举。
格式和CLI见[来源插件契约](references/recommendation-source-plugins.md)。当前尚未发布安装，
日常0.53.0页面保持原状。
