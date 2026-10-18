# 总项目／子项目身份基础：开发验证

## 当前交付预检：wheel与独立脚本环境

本轮未改变产品代码、版本或安装；上一轮修复的3072项完整结果保持其原范围。
以当前未提交源码离线构建wheel，仅作开发预检，不生成release分支或推送，不把它
当正式0.46.0或安装态验收。wheel元数据仍为尚未升级的0.45.1，不能安装冒充新版。

| 检查 | 实际结果 |
|---|---|
| 离线构建 | uv build --offline --wheel成功，产物在本轮临时构建目录 |
| 分发边界 | 125个包代码/静态文件与当前src逐字节全等；无多余根、重复/越界成员或历史build残留；wheel不含planning/tests等开发资料 |
| 模块与命令 | 10个新增project模块确实从wheel路径导入，非源码回退；project/experiment两组12个新命令各自--help成功，不调用业务API |
| 版本和入口 | pyproject、两份plugin manifest与wheel metadata均为当前0.45.1；console entry为scholar_workflow.cli:main |
| 定向隐私扫描 | 包内容无当前用户名绝对路径、临时系统路径或个人代理端口；不是通用秘密审计或固定release全边界认证 |
| 独立解释器 | 系统Python缺pydantic，但初始化脚本profiles仍成功；它只依赖stdlib，不应为怀疑添加runtime runner或自动装依赖 |
| 无site-packages预览 | /usr/bin/python3 -I -S下profiles和research-parent plan成功；目标目录始终不存在，未git init/写入项目 |
| 路径安全 | 首次以macOS的/tmp别名为plan输入，按既有symlink规则拒绝2且未写；读取实际物理目录后使用/private/tmp显式路径成功，未放宽规则 |
| 现用环境 | PATH CLI实查仍0.45.1，无正常安装、缓存修改、Vault/Zotero/服务器/服务或main变更 |

临时wheel SHA-256为`c323b7bcc94456006bdc8c65c329bd9d4b8de3017652e4f88cfcce59a67edf05`。
构建后只生成常规ignored build/egg-info；tracked/untracked状态没有新增产品文件。
没有为重复同一全仓结果再跑一轮；本次证据只证明分发文件与无依赖脚本启动，不证明
新版正常安装、原生工具连接、完整业务流程或人工可用性。发布授权仍待确认。

## 当前交付审查：重复留存的同步失败

在同一合成对象已留存后，仅注入coverage目录fsync失败。独立新增断言要求partial6、
全目录字节不变、解除故障后相同重试成功。初次**1 failed**：实际错误被root context
包装成冲突5，证实旧3071项未覆盖此处。最小修正只把该同步异常转为CodeRecoveryError6，
不放宽未知内容/过期/身份冲突保护。修正后24项code recovery及相关共**118 passed，12.45秒**，
新模块/测试Ruff通过。修正后完整`pytest tests/unit tests/contract`实际为**3072 passed，
11个既有弃用警告，138.79秒**，不是沿用旧3071。diff检查通过；没有放宽产品断言。
发布/安装仍未获本批确认，PATH仍0.45.1；安装单对象输入与可见评鉴方式见
0.46.0-installed-acceptance-plan.md（待执行，不是结果）。没有真实资料或服务器变更。
未发布Changelog已合并为当前五类能力说明，去掉同一候选内“已实现/未实现”相互冲突的
开发时点表述；已发布历史不改，原过程仍保留于本文与HANDOFF。

## 当前增量：最简代码恢复材料

对象为同一个合成总项目/子项目及五状态Run；独立创建两个真实本地Git提交与完整、
增量、损坏bundle。先准备输入/预期，再检查预览、明确留存、重复执行与失败边界。
不从真实服务器采集、不运行代码或实验，不修改真实项目、Vault、Zotero或安装。

| 操作／情形 | 实际结果 |
|---|---|
| 提交覆盖 | 所选child所有已收集Run的源码commit与明确附加commit均存在且完整；不读取parent Git HEAD |
| Git隔离 | 空bare repo内verify/unbundle/full strict fsck，无checkout/执行/网络；继承Git配置、对象库和凭据不可用 |
| 缺口 | 所选提交标准LFS pointer/gitlink明确列出缺失payload；未提交/未跟踪/外部依赖/secret audit均not_checked |
| 拒绝预览 | 缺提交、增量依赖、损坏bundle、symlink、未知child、pending档案均拒绝，不生成backups目录 |
| 实际留存 | 只存child/hash下原bundle、material.json和coverage记录；mode600，原source字节不变，无开发checkout |
| 幂等与补查 | 同内容重试unchanged并再同步目录；补查第二提交只增加coverage，不重复bundle或改变其inode |
| 冲突保护 | 已有未知材料、被修改coverage、symlink目标与过期计划均拒绝，不覆盖人工文件 |
| 中断 | publish后注入故障返回partial6；相同内容重试读回并确认同步，不把可见文件当已完成 |
| 超时 | 合成Popen超时只清理所建process group并wait；未对真实进程发信号 |
| 机器契约／CLI | 实际保存的两类JSON通过严格schema；拒绝verified/多余路径/空覆盖；缺Git正确exit3，显式留存CLI通过 |

新增**23项**与transaction/package/remote-code/management/eval相关共**117 passed，12.36秒**。
Ruff新模块/测试通过。此前21项/115项也是同一切片较早快照，不重复累计。
最终完整`pytest tests/unit tests/contract`：**3071 passed，11个既有弃用警告，139.99秒**，
包含本次远端引用及23项代码恢复检查，不沿用旧3021项。eval新增后另10项结构检查通过。
init-project、organize-project、review-experiments三skill基础校验及diff检查通过。
已知CLI既有TRY004仍保留，不能称整CLI lint全绿；运行reference与schema同步的是实际接口。

这是本地明确提供bundle的覆盖核验和留存，不核验真实远端child来源、不自动创建/传输
bundle、不恢复LFS/子仓库/未提交内容，不是verified backup。SHA-1格式、256MiB输入、
8MiB Git stdout、30秒每命令、1MiB coverage边界均明示；不是完整资源沙箱。
新源码仍未提交/发布/安装；正常安装仍0.45.1。原生远端/安装单对象/人工与G17仍未完成。

## 当前增量：执行子项目代码引用与声明定位

先准备一个合成总项目/子声明/SSH Target/私有ledger，再实现schema1增量引用与CLI。
execution-code只存child UUID、安全相对路径及可选commit；只允许code项，不把主项目
当子项目。不改旧清单、不创建host registry、不保存密码/密钥/任意URI。

| 检查 | 实际结果 |
|---|---|
| 便携引用 | schema与运行校验接受子root `.`、安全中文及普通路径；绝对路径、..、空段、反斜线及控制字符拒绝 |
| 可读总览 | 只呈现用途/子代码相对位置/真实未核验状态，不显示UUID/commit hash、主机根、伪本地或SSH链接；未登记child保留missing行 |
| 明确定位 | 仅取选定现有SSH Target及其server_alias对应的既有ledger记录，正确组合带空格的POSIX根和相对代码位置 |
| 真实性边界 | 状态为declared_not_remote_verified；child身份、远端路径、commit、访问及SSH配置五项均not_checked，不把地址声明当远端验证 |
| 路径与来源 | 未登记server、未知/不匹配/local Target、越界根及symlink目标拒绝，不推断/发现/初始化 |
| 秘密与变更 | JSON不含旧密码、key路径或环境绑定；CLI非法凭据/URI错误不回显输入；读中Target/context/management/ledger变化分别拒绝 |
| 副作用 | 全父目录/ledger文件集及字节守恒；CLI禁用subprocess及未选择配置入口后仍成功，不连接、不调用原生工具 |
| 旧接口 | 旧project-file/reader、候选预览、管理身份及服务器CLI相关检查均通过，无schema2或layout变化 |

新增27项，连同context/schema/CLI/candidate/unit、management、assets CLI和eval schema，
最终**191 passed，2.40秒**。首轮97项通过；扩展后191项及最后公开schema路径复验均通过，
不将重复运行累计为不同测试。Ruff初次两处import排序问题机械修正；新增/变更的context、
remote_code及新测试Ruff通过，diff通过。补查整份CLI发现一处既有TRY004（服务器spec非
对象时抛ValueError），HEAD已确认相同实现，未顺手修改；不能冒称整个CLI静态检查全绿。
新增eval记录后10项结构复验通过。
本轮没有全仓运行；上一节3021完整回归属于更新恢复快照，不涵盖本次新代码。

这是声明引用与定位预览，不是可点击的原生远端打开或自动SSH连接。Target与child的
远端实际归属仍未核验，不能据此编辑/执行；代码恢复、正常安装态、原生及人工仍待。
没有真实项目、Vault、Zotero、服务器、发布安装、main变更；原论文与Canvas样式不改。
共享契约只增加真实数据/操作接口与末端状态，不规定研究/推理步骤，G17保持开放。

## 当前增量：实际Run更新与显式提交／回滚

先为同一合成Run定义更新、中断与恢复预期，再实现transactions模块及三个CLI命令。
update-run绑定四摘要，先保存并核验before/after/journal，再创建持久pending标记，只改
精确执行证据，receipt最后。recovery-plan本地只读，recover-update按新观察摘要显式
commit或rollback；不需要source child在线，也不连接服务器或执行实验。

| 操作／情形 | 结果 |
|---|---|
| 正常更新 | running记录更新为succeeded并增加日志；source不变，本地人工notes/report的字节及notes inode保持 |
| 任一写入边界中断 | 在首文件、新增日志和最后receipt之后分别注入失败；返回partial6，reader为pending_update，不能冒称完整 |
| 显式提交 | 子目录移走后，只凭本地材料完成candidate，移除pending后reader完整；不冒称真实执行成功 |
| 显式回滚 | 上述各边界均恢复旧受管字节；新增文件从Run移除但其字节仍留在恢复包，本地笔记保持 |
| 未知文件／伪造计划 | 人工改动、同字节但无归属的新文件、未知临时文件、把action改指向notes.md，即使重算marker摘要也拒绝；全父目录字节不变 |
| 再次中断／过期预览 | 恢复中再次注入失败后，可新预览再恢复；旧revision拒绝5且零写入 |
| CLI路径 | update-run实际写入预览版本；recovery-plan零写入，recover-update只访问本地，不使用host config或工具进程 |
| 落盘边界 | unchanged重试仍同步目录；注入同步失败仍partial6，不把字节匹配当作可靠落盘证明 |
| Git边界 | 新parent忽略collection-transactions包；PROJECT/docs/轻量experiments仍不忽略，不改已有ignore文件 |

初次18项检查中6项恢复失败：RUN_ID是字符串regex，误当compiled pattern调用；修正产品
代码为re.fullmatch，18项重跑通过，没有放宽校验。扩展后19项transaction、11项package
及其余登记/生命周期/eval共205项通过。最终在完整`pytest tests/unit tests/contract`下
**3021 passed，11个既有弃用警告，129.20秒**；本轮源码、运行reference与新parent忽略规则
均在此回归范围。Ruff、diff检查、init-project quick_validate通过；后者初次系统Python
缺PyYAML，改用项目uv依赖环境后通过，不安装全局依赖。

可恢复逻辑事务不是文件系统全局硬原子：锁为协作式，外部编辑器/同步器需停写；检测变化
拒绝，不能保证不合作工具在最后检查后的任意修改。包为本机inode绑定恢复材料，不是
verified backup；不自动清理孤立包/旧reception stage，rollback可留新空目录。实际Linux
平台、正常安装态、原生工具与人工评鉴未在本轮证明，PATH实查仍0.45.1。没有发布安装、
main合并、真实项目/Vault/Zotero/服务器操作。remote-code locator、最简源码恢复和旧G17
科学/人评/备份缺口保持未完成；原论文/Canvas已认可格式不重画。

## 当前增量：更新前恢复包准备

同一合成Run上先写独立预期，再实现内部stage_run_update。四份摘要必须与新预览一致；
包在父项目私有状态目录保存精确变更的旧/新字节、权限、文件身份和最后一项receipt。
旧/新payload及journal读回核验、目录同步后才返回staged_not_applied，不写当前归档或
pending标记，不把静态准备结果当作执行、worker存活、更新完成或verified backup。

| 检查 | 实际结果 |
|---|---|
| 正常准备 | 两个执行文件变化和最后receipt均逐字留存before/after；schema、摘要、权限及原inode符合预期 |
| 人工边界 | local notes及全部现有Run字节/source child字节保持；没有激活标记 |
| 过期预览 | 父/子/新证据/旧receipt任一摘要错误均exit5且不创建状态目录 |
| 准备中断 | journal写入失败、source变化保留明确包路径、exit6，当前归档不动 |
| 归属与路径 | storage symlink不跟随；相同字节但原inode被替换拒绝；准备材料被改动不能报成功 |
| 无变化 | unchanged，零文件写入、无新恢复包 |

首轮收集测试因跨模块import写法失败（未执行测试），修正为项目既有tests包路径；
产品校验未改松。69项首次复验通过；补充原inode替换和payload改动后，最终176项相关
检查通过，10.43秒，其中新增11项；Ruff通过。不是全仓/安装态/原生或人工验收。

仅新增内部准备接口，无用户CLI writer；activation/apply及显式commit/rollback恢复仍待。
失败材料不自动清理；未来使用需独立校验journal语义及当前归属，不能凭schema/状态直接
写入。保留完整阶段目标，未发布安装或操作真实对象，原有论文/Canvas认可不重做。

## 当前增量：安全更新预览与pending保护

在同一合成Run上先定义预期，再新增update-plan。可预览running→succeeded、新Attempt、
新日志/空目录，以及原manifest-only成果补齐本地副本；不写入本地归档。JSON列出父/子
摘要、旧receipt实际字节摘要、旧/新证据hash、逐文件add/replace、新目录、Attempt与Artifact
变化及拟议receipt。本地人工report/notes不在变更集，逐次文件集合/字节守恒。

| 检查 | 结果 |
|---|---|
| 精确变更 | running终结+日志新增仅列出对应两文件；新Attempt为新增执行，不冒称独立重复实验 |
| 配方/历史 | 同Run换源commit/配方、状态倒退、终态事实改写、Target快照变化及旧证据删除均拒绝 |
| 人工边界 | 新源文件撞上本地未受管文件时拒绝；本地已受管文件被改动时拒绝，不覆盖 |
| 内容相同 | unchanged且空变更集；新增空目录仍是planned_update，不错误标成unchanged |
| 成果补齐 | 仅保留原identity/role/source Attempt/remote origin/backup不变的manifest-only→local变化，backup仍not-verified |
| 事务标记 | 本地.collection-update.json使reader为pending_update、reception拒绝exit6；不靠标记判断进程存活，也不自动删标记 |
| 禁止混入 | 源Run里的.collection.json/.collection-update.json（文件或目录）拒绝作为执行证据导入 |

124项角色/旧实验/eval定向检查通过（9.58秒）；随后对最终变更说明及4项reserved-source
反例复验，70项（60预检/接收/读取/更新预览+10eval）通过。Ruff/diff通过。共享
read_collected_evidence复用既有完整性/位置检查，未减少证据或放宽旧格式。

未实现update apply或commit/rollback恢复，不用普通复制/覆盖假装实现；首次receive仍拒绝
不同版本。pending保护是失败关闭，不是活跃worker证明。下一步把选定变化接入可恢复journal，
再提供写入和显式恢复，继续同一合成对象。没有真实项目/Vault/服务器、发布安装或main变更；
原论文/Canvas规范及既有认可保持。G17完整阶段仍未完成。

## 当前增量：本地归档读取与索引

在同一合成单Run输入上先准备离线读取、损坏/缺失状态、选择范围及中英导航预期，再实现
collected模块和`experiment collected`。接收后移走源child目录，只靠本地档案读回原配置、
环境、dataset/version/split、seed、commit、五类状态/时间/退出码和成果入口；没有源child、
服务器、Git进程、宿主配置或Hub依赖。原始相对子项目路径经receipt映射解释，不改写事实。

| 检查 | 实际结果 |
|---|---|
| 本地离线读取 | source目录移走后仍有效；所有父档案文件字节不变 |
| 完整性与作用域 | receipt身份/schema/映射/清单hash、受管文件hash/size/mode、配方/Attempt/Target/成果均检查；读取前后重观察并核对目录位置 |
| 部分失败 | 坏receipt、越界映射、改过的文件、symlink保留invalid行；一个child坏档案不掩盖另一child的好档案，显式选择仍可只读所选child |
| 空库与边界 | 未接收child仍显示；未登记目录不扫描/不收编；未知child选择拒绝；暂存/未知条目不计完成Run |
| 可读总表 | 配置/环境/数据/seed与记录状态、起止时间/退出码及成果入口同处；中英结构标签各自一致，完整hash和UUID不进入正文；中文所有生成本地链接存在 |
| 指标 | 本地metrics只作未解读入口，remote-only不冒充本地成绩；未定义含义的合成0.8不打印为科研分数或排名，目的不猜而指向执行报告 |

新增指标fixture首轮1失败/127通过：现有ArtifactRecord要求promoted_at字段，远端manifest-only
输入漏填null。修正独立fixture，未放宽产品校验。最终128项相关检查通过，9.09秒；
其中42项是预检/接收/读取用例，其余登记、角色、生命周期、CLI和eval。Ruff/diff及skill基础通过。
未把重复运行累加成全仓检查。配方校验从预检提取为共享纯函数，读取和接收入口复用，
既有源记录不重新生成、不运行实验。没有原生VS Code呈现或人工评鉴证据。

输出为stdout Markdown/JSON；不是写入另一个权威index、自动更新PROJECT或正式实验比较。
`complete`仅指所选读取范围完成，不代表所有实验执行成功/全部回传/科研结论可信；范围、
child状态和records_only各自保留。旧flat父项目命令仍拒绝，新qualified只读索引已有源码。
CAS版本更新、显式崩溃恢复、远端定位和代码恢复仍待；未发布安装或合并main，G17开放。

## 当前增量：首次接收实际档案

先在原合成单Run输入上增加实际接收/失败/竞态预期，再实现`project/reception.py`、
`experiment receive-run`及`experiment-collection.schema.json`。不是把预览当接收：测试
逐个比较了落盘文件原字节和文件权限，保留空目录、五种声明状态及子Run的原commit。
没有执行实验、访问服务器或写Vault/真实项目；这些状态仍是合成记录，不是实际观测。

| 检查 | 实际结果 |
|---|---|
| 首次接收 | 新建experiments/child-segment/Run，受管文件逐字/权限读回核验，生成schema1机器receipt；source Run不改写 |
| 两child同名Run | 分别落在main-method和baseline，不合并；原始笔记内容分别保持 |
| 幂等及本地分析 | 新建本地report/notes/custom后，同内容重试unchanged，三份人工内容及全部既有文件字节保持 |
| 过期或冲突 | 父/子/证据任一摘要过期拒写；已有空目录、修改过的受管证据、伪造布尔schema版号均拒绝覆盖 |
| 发布竞态 | 在发布瞬间插入空目录，macOS原生RENAME_EXCL拒绝；不是普通rename覆盖空目录 |
| 路径边界 | experiments或child namespace为symlink时拒绝，外部目录为空；不跟随目录逃逸 |
| 暂存/源变化 | 写入中故障或源笔记变化不发布正式Run，正常清理仅限本次未改变的stage |
| 部分完成 | publish后fsync失败正确exit6；重复同步仍失败时维持partial，恢复同步后验证并unchanged |
| 清理失败 | 不假称已清理，exit6并保留stage供审阅，不删除其他位置 |
| 旧接口保护 | 父项目flat validate/index拒绝，不能漏看子档案后报告0Run；父Target登记仍可用 |

最初故障注入得到1失败/87通过：底层root context把publish后的OSError包装成layout错误，
导致接收入口未报告partial。已在接收边界处理两类异常，未修改通用root context语义；
目录同步覆盖namespace、experiments及项目根，暂存子目录也先同步。新故障分支均复验通过。

115项相关回归通过（11.85秒），包含31项当时的预检/接收用例、角色、旧生命周期、CLI、
复现及eval。补清理失败和receipt布尔/整数区分后，当前33项预检/接收加10项eval共43项
再次通过；Ruff/diff通过。不把重复用例累加成全仓回归，未运行全仓或安装态验收。

原生发布在本机macOS真实执行，SDK头和man2确认exclusive语义；Linux分支尚无实机证据，
其他平台或文件系统能力缺失时拒绝，不退回覆盖式rename。普通失败可能保留空namespace；
硬崩溃可能留hidden stage，显式清理恢复仍未实现。旧版本更新需CAS/恢复，不覆盖本地分析；
qualified reader/index、远端定位及代码恢复仍待，不能宣称整个回传系统或G17完成。

本机PATH本轮仍核为0.45.1；没有提交、发布、安装、合并main或服务切换。原有论文/Canvas
规范与认可保持，当前仍只有开发证据；test Vault原生单对象验收须在本轮获准安装之后进行。

## 当前增量：单Run接收前检查

先准备独立合成输入`test_project_collection_plan.py`：一个已互认父子、一个Run、真实
字节快照和五类声明状态（planned/running/succeeded/failed/interrupted）。没有执行实验，
记录中的commit/时间/状态都是明确的合成输入，不冒称观测结果。只测试一个Run，不整库扫描。

`experiment collection-plan`只读校验配方、快照hash、全部Attempt、Target/输出清单及本地
成果的身份/hash/size，输出按子项目限定的目标、原commit和文件映射；不读取管理Git。
远端report/notes映射为execution-report/execution-notes，本地分析的原名保持保留。
空目录和安全文件mode被记入预览/evidence摘要；源记录不重写，后续reader须按映射解析。

15项新增检查通过：完整五状态和文件集合；输入/目标/recipe损坏、越界快照、身份不符、
生命周期矛盾、actual commit不符、重复YAML键、报告命名冲突、未登记child、symlink和
检查中源变化均拒绝；未选另一Run无效也不读取；CLI不调用工具/配置，不写任何文件。
最终当前115项（15项新增及相关登记/身份/实验/eval）通过，6.88秒；Ruff与diff检查通过。

资源边界是128MiB总文件字节、1MiB单记录；超出明确失败，不静默跳过、不限制Attempt
数量。大型数据/权重须留远端并由显式manifest解释。重复读取能检测本轮观察到的源变化，
不是跨机器原子快照或永久冻结；running/planned明确标为可变状态。

该入口不检查目标覆盖/CAS权限，不复制文件，实际receiver/后续生命周期更新/恢复和
可重建本地索引仍待实现。没有用预览冒称回传成功。未提交发布安装；已发起本轮0.46.0
正常发布安装与test单对象验收的授权询问，尚未从未回复推定授权；main/服务/正式数据不动。

## 当前增量：子项目登记

先准备`test_project_child_registration.py`的独立输入，再实现registration模块及CLI。
一个总项目、主子项目及非主子项目均为合成声明，没有服务器/真实项目/Vault操作。
预览零写入；apply绑定两份实际字节摘要，只追加父children，不修改子项目或人工文件。

| 检查 | 实际结果 |
|---|---|
| 单次追加/旧记录保留/重复登记 | 仅父管理声明变化，其他记录/文件保持；相同登记unchanged |
| 冲突 | 目录变更/占用、多primary、错误parent拒绝，不覆盖 |
| 字节基线 | 父/子增加空行也令预览过期；CLI旧apply exit5 |
| 并发/忙锁 | 同一基线只有一个成功，另一个冲突；持锁时不等待、不写入 |
| staging后外部改动 | 修改父/子声明均拒绝；相同字节替换父inode也拒绝 |
| 安全路径 | 声明symlink拒绝，外部目标原字节保持；复用bounded/root-pinned读取 |
| 写入失败 | replace失败保留原件并清理本次暂存；replace后目录fsync失败报告partial6，实际新登记可读 |

最终当前字节239项相关检查通过，12.22秒，其中18项登记用例；其余覆盖身份/角色、旧
context安全读取/CLI、初始化/profile、实验生命周期、模范项目复现及eval结构。
Ruff与init-project基础校验通过。字节reader仅分离原安全读取与JSON解析；重复键、大小、
symlink及读取中变化保护不变。没有主机发现、SSH/Git/浏览器、实验收集或部署。

锁是协作式单文件替换；apply时外部声明编辑需停写，不声称跨机器/全文件系统硬事务。
最终检查后的不合作编辑不能保证完全阻止；硬崩溃可能留下无权威的暂存文件，不自动
清理其他文件。不确定落盘先读回，不盲目重放。正常失败清理与并发拒绝已做定向验证。

尚未提交、发布、安装或合并main；0.45.1安装无新入口。实验分层接收/索引、远端导航、
恢复采集仍未完成，G17开放。下方角色/身份切片保留历史，不把旧“无登记writer”当当前能力。

## 同日当前增量：双角色初始化

独立测试先写入`tests/contract/test_project_role_init.py`，随后实现helper和更新skill。
本轮使用skill-creator及本仓开发指南，未改变description、触发方式或论文/Canvas契约。
下方身份基础结果保留为先前切片；角色初始化不再属于“尚无源码实现”，但安装仍未更新。

| 对象 | 本轮真实合成结果 |
|---|---|
| 总项目 | 独立Git；PROJECT六节/唯一内嵌计划、README、空context及管理声明；docs知识/规划/报告、skills、assets、Target与恢复目录齐备，不生成源码树 |
| 子项目 | 独立Git及父身份/primary声明；world-model profile、canonical configs、env/toolkit/tests、dataset和实验目录；不生成总体文档或复制总项目知识 |
| 人类文档 | PROJECT无机器HTML注释、哈希或虚构研究成果；人工PROJECT/笔记在重复apply后字节保持。若PROJECT缺失但SCHEDULE存在，拒绝造第二份详细计划 |
| Git | 实际check-ignore确认PROJECT、项目笔记与轻量实验指标不被忽略，恢复bundle被忽略；没有remote，没有stage/commit/push |
| 身份与重复执行 | UUID和声明稳定；省略角色保留已有角色；不同role/parent拒绝；旧通用项目不隐式转换 |
| 边界 | 非空根、祖先Git、symlink根/祖先、parent带source参数、缺父UUID全部拒绝；无业务写入 |
| 实验安全 | 总项目create_run在创建锁/状态前拒绝，不能误用管理Git的HEAD；源child/legacy lifecycle回归通过 |

最终当前字节：95项角色/身份/初始化/实验检查通过，8.78秒；
另36项eval schema/context/模范项目复现通过，3.52秒。
共131个不同测试，不重复计算此前重跑。Ruff初次报告import/default-argument规则，修正后
helper、实验模块及角色测试通过；skill quick_validate通过。没有独立宿主行为或安装态评鉴。

这仍是空骨架，不是已填完项目事实的模范业务包。子项目不会反写总项目children，尚无
登记writer/回传receiver/远端代码导航/最简代码恢复采集；这些不能由生成骨架宣称完成。
没有发布、安装、main合并、真实项目/Vault/服务器变更。需要正常安装后，才安排test
中的一个项目原生呈现与人工评鉴；不以源码临时运行替代安装态产品。

## 范围与状态

2026-10-18，独立分支`codex/hotfix-project-management-identity`。
已实现schema与只读检查，不是双角色初始化、远端登记、实验接收或安装态验收。
本机PATH CLI本轮实查仍为0.45.1；未提交、发布、安装或合并main。
测试前已在会话说明对象、步骤、预期、影响与回执，不修改Vault/Zotero/服务器或真实项目。

## 独立输入与预期

输入固定在`tests/contract/test_project_management.py`，不由产品生成器制造预期。
一个research-parent声明两个独立child：main-method为primary，baseline非primary；
每根保留原schema2 layout UUID，管理声明另用schema1。父子互认必须同时匹配UUID和primary。
空children允许；不强制预先创建主子项目或规定baseline等科研分类。

| 检查 | 预期与实际 |
|---|---|
| 正常两角色、空总项目、schema结构 | 通过；模型往返保持完整声明 |
| 错误版本/UUID/类型、额外主机或cwd字段 | 拒绝，不接受个人定位信息或混合字段 |
| 自关联、重复子项目、重复目录、多primary | 拒绝；归档映射不合并身份 |
| `../escape`及保留`profiles`目录 | 拒绝，不与Target配置目录混用 |
| 父子UUID/primary不一致、两角色倒置 | 拒绝，不把单边声明称为互认 |
| 缺管理声明 | exit2，不推断角色或创建文件 |
| layout身份不匹配、重复JSON键 | 拒绝 |
| 符号链接文件/根、超过1MiB的声明 | 拒绝，复用既有安全读取器 |
| 显式两根CLI检查 | exit0；全部输入字节及文件集合保持，禁止外部进程和主机配置读取 |
| 仅提供一根 | 明确说明未检查另一方，不声称互认 |

## 实际结果

- 第一轮44项通过；补充保留目录、过大文件、symlink根及倒置角色后47项通过，2.55秒。
- 其中当前新增27项；另151项项目/context/实验生命周期与复现回归通过，11.96秒。
- Ruff初次指出两项通用ValueError类型规则；改用领域异常后，新增27项再次通过，0.12秒；
  两个新增Python文件Ruff通过。该异常继承ValueError，保留CLI输入错误边界。
- `git diff --check`通过；原主工作区仍保留原有未提交审阅文件，未在那里编辑。

共198个不同测试通过，不是全仓回归或新版本正常安装的证明。未运行真实论文分析、实验或
远端命令；无需重新评鉴旧Canvas、图片、折叠和项目典范。

## 可观察结果与使用边界

开发入口为`project validate-management --project-root <child> --parent-root <parent>`。
成功输出明确包含“Parent/child declarations agree”，同时保留“Remote placement, Git policy
and execution availability are not verified”。只传一根则输出“Counterpart declaration not checked”。
用户当前安装0.45.1尚无此入口，不应现在让用户照此运行或手工修改安装缓存。

project-management.json只持有便携归属；主机定位、凭据、文件授权仍留在各自现有系统。
它不证明Git push策略已强制实施，也不授予服务器操作权限。既有初始化器尚未读取/写入该文件，
旧new-run也未因这次检查而具有分层能力；不能把本地管理Git的HEAD用于远端实验。

下一步：在此身份边界上实现显式双角色初始化，保留总项目知识、PROJECT/唯一计划、
规则及实验分析；远端子项目保留源码/config/toolkit与执行档案。之后再实现子项目限定的
接收、索引与远端导航。每个切片独立测试，正常发布安装和单对象验收另行推进。
