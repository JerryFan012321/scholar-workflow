# 正式归属只读解析：独立测试计划

## 0.42.0正常安装态：单对象执行前说明

2026-10-09用户明确批准发布安装及只读验收。输入固定为当前主机已登记的test Source、
其“模范知识目录-0.36.0”根Field/provider、一个既有模范项目和V-JEPA 2三项Obsidian引用；不改变清单
以凑结果，不重新登记、分析、裁图、运行实验或迁移。先正常安装固定release SHA，
检查公开版本/帮助、模块及两个manifest，逐文件与发布Git字节比较。

在项目根之外运行显式pipx CLI的`project overview --resolve-knowledge`，各一次人类文本
和JSON。手写预期：8项清单保持，4个本地项目文件available；资料笔记、分析Markdown、
Canvas三个Obsidian对象均resolved，文件与primary owner文件available，归入同一Source/
Field和论文primary ID；Zotero附件仍unverified，不能冒称已查询阅读器或科学支持。
registry当前只有一个启用Source，若实际声明冲突/变化则保留实际失败，禁止修改后假称通过。

独立观察器在执行前后对所选Source文件、该Source provider状态、registry、项目两份
声明及4个显式文件比较路径集合/hash。观察器为完整性核对可读取这些文件字节，不解释
论文正文；产品命令本身只读声明、检查文件路径。不得扫描其他Vault或重做整库业务。
原始stdout/JSON、安装身份及观察结果仅保存为开发侧忽略目录的验收产物；不写Vault/
项目/provider或Zotero。人类可读展示副本将项目相对链接明确重定位到原项目，知识入口
继续使用现有稳定Obsidian协议；没有新增关系或正文owner。

会话明确展示对象、打开方法、预期效果与判断标准，等待人类导航评鉴；旧Canvas/图片/
折叠摘录认可不重新审批。安装/自动结果通过不等于整个G17完成。

日期：2026-10-09；分支 `codex/hotfix-knowledge-ownership`，基于0.41.8源码71a9f7b。
状态：输入与预期先于实现准备；用户2026-10-09批准后执行合成范围，57专项与138必要
回归通过，规范修正后195项联合复跑通过。独立结果见knowledge-ownership-test-results.md。

## 输入和影响范围

- 仅 pytest 临时目录里的合成 Source、Field、provider、项目、普通文件及符号链接。
- 一个主论文 ID，配套分析/Canvas；第二 Source 用于正式 owner 冲突或不可核验用例。
- 项目清单继续使用版本1；只读可选检查不改变现有默认行为，不复制或改写正文。
- 不读真实 Vault、Zotero、Obsidian配置、凭证或服务；不运行实验、阅读器、Codex或cmux。
- 手写预期由 `tests/fixtures/knowledge-ownership/EXPECTED.md` 持有，测试文件为
  `tests/contract/test_knowledge_ownership.py`，不能以新生成结果回填预期。
- 当前57项参数化用例已执行通过；主owner缺失的人类提示、三个authority根的
  中间symlink、YAML alias/重复键与声明读中同字节换inode已补入独立预期。
  产品检查期间守卫禁止正文读取、文件写入/创建锁及文件系统变更；模拟并发替换仅由
  明确fixture hook执行，前后字节/目录集合保持，不能把fixture操作当产品写入。
- 只读独立审阅发现原39项遗漏根Field `.`、仅artifacts声明的sidecar、目录/FIFO，
  且后缀守卫不能阻止JSON sidecar正文。先补手写预期后补18项（根Field四对象、sidecar
  四状态、五位置x两种非普通文件），改为精确声明路径读取白名单；不是运行失败或通过。
  默认总览新增手写DEFAULT-OVERVIEW.md，不从当前renderer生成期望；既有静态golden回归保留。

## 本切片接口与预期

组合入口 `resolve_project_knowledge(overview, registry_path)` 仅解析 Obsidian 外部项。
只从所选 registry 的已登记 Sources 读取固定声明，不扫描磁盘、标题或 wikilink。
结果按项目 entry_id 分组；每项单独报告正式归属、文件状态和未核验的阅读入口。
原 Zotero 项继续走所属工具，不靠知识声明冒称当前 Local API 可用。

| 用例 | 手写预期 |
|---|---|
| 合法单 owner/分析/Canvas | `resolved`，同一 Source/Field/primary owner；文件分别定位，reader始终`unverified` |
| 根Field `.` | 资源从`resources/papers/...`起算、core为`Overview.md`；四对象保持相同显式归属，无虚构父目录 |
| artifact-only sidecar | 由显式artifact得到主owner；available/missing/unsafe分别报告，主owner重复仍conflict；不读取JSON正文 |
| 两项目复用 | 返回同一主归属；不新增副本或关系真源，所有输入字节/文件集合保持 |
| 跨Source重复primary | `conflict`；包括仅一边有该分析的情况，不择首项 |
| 其他已登记Source禁用/损坏/不可读 | `incomplete`，不谎称全局唯一；不绕过权限去读取内容 |
| 所有声明可核验但没有ID | `not_found`，不从审阅副本或同名文件推测 |
| 声明存在、文件缺失 | owner保留`resolved`；文件`missing`，不等同身份消失 |
| symlink/特殊文件/祖先替换 | 不跟随，文件`unsafe`或声明`incomplete`；不得读外部目标 |
| registry/Field/provider读中变化或binding不符 | `incomplete`，不能把混合版本当完成的解析 |
| 当前 reader URI 有效但未实际验证 | 永远不标阅读器通过，不用URI推导owner，不自动启动应用 |
| 默认project overview | 原JSON/Markdown保持，不读registry、不创建目录/锁文件 |
| 显式CLI检查 | JSON只追加`knowledge_ownership`；可读正文同条说明归属/文件/阅读器，隐藏UUID与绝对根 |

CLI开发入口为 `project overview --resolve-knowledge`；可用 `--knowledge-registry PATH`
明确选择合成或主机状态域。后者必须与前者一起使用，不能意外触发额外读取。
这些是本hotfix将提供的入口，未安装版本不得被描述成已具备。

## 执行记录与后续步骤

1. 已执行上述57项新增合成用例；全部通过，独立预期未据产品结果回填。
2. 已运行138项既有project-context、知识契约/登记及eval-schema回归；全部通过，不重跑真实论文业务。
3. Ruff首次两项规范问题已最小修正；195项联合复跑及Ruff通过，记录更新后的10项eval schema
   复查、diff和知识核心导入边界检查通过；原始结果及命令在独立报告留证。
4. 测试后再准备可正式发布的hotfix版本与正常安装；发布/安装授权独立，不以源码执行替代产品。
5. 安装态仅对当前V-JEPA2和一个模范项目做零写入总览，展示实际归属与现有资料打开方式；
   人工评鉴在会话明确说明后另行确认，不重复已经通过的Canvas/图片/折叠评鉴。

首轮实际用既有offline uv/pytest执行57新用例及project-context（模型/契约/CLI/candidate）、
knowledge-contract、knowledge-registration-CLI、eval-schema必要合成回归；不启动网络
或应用、不写真实状态，不运行完整整库业务。静态diff检查不能替代运行。
测试结果独立写入knowledge-ownership-test-results.md；发布、安装、安装态单对象和人工
步骤未执行。重读全局规则已确认测试方案不需二次审批，执行前仍说明对象、步骤、
预期和影响；发布安装及真实数据操作不因测试通过获得新授权。

## 可见产物与完成判断

交付一份能读懂的项目资料清单：哪个文件正式放在哪里、为何使用、原件是否可定位、
阅读入口是否仍待核验。JSON供机器保留稳定身份，不代替正文。
自动测试、安装态零写入和人类导航体验分别记状态；本切片不承担跨Source写入查重、
Field新增/删引用或owner迁移，它们仍是完整归属能力的后续交付。

## 0.42.0本地包准备：输入与预期（执行前）

本切片新增用户可见能力，按项目版本规则准备0.42.0；没有新的业务功能或真实数据操作。
同步pyproject、Python公开版本及两host manifests；lock只允许本包版本变化，不升级依赖。
现有独立runtime-version用例必须证明四处相等及公开CLI版本一致，原金样与57项预期不变。

1. 在当前hotfix运行现有`tests/unit tests/contract`合成全集。期望所有用例通过，已有警告
   单列，失败按最小范围修正；不以真实论文/整库业务代替回归。
2. Ruff只查本切片改动Python；diff及lock检查通过，无新增第三方依赖。
3. 仅本地提交本工作区本切片文件及版本，记录确定source SHA；不推送或合并main。
4. 在`dist/0.42.0-local.*`的独立干净clone运行既有make-release脚本，产生runtime-only
   分支、Git归档、wheel/sdist；只影响构建clone，不切换/删除用户checkout或其他worktree。
5. 逐文件检查runtime来自确定source SHA，新增归属两模块及公共reference必须进入包；
   无planning/dev-guide/tests/evals/AGENT/CLAUDE、个人根/凭证进入runtime。
6. 离线构建及公开`--version`/`project overview --help`仅检验包入口，无业务写入；
   此构建环境不算正常安装，也不据它认证实际安装用户体验。

可见产物为独立本地包、身份/hash与结果记录；执行后填写，不提前称已构建/已发布。
发布/正常安装、单V-JEPA2加一模范项目的零写入导航与人类评鉴仍是独立后续步骤。

## 正常安装解释器对齐：执行前说明

只读定位已安装pipx metadata发现其实际解释器为Python3.14；前述开发全集为3.12。
使用固定0.42.0 wheel及独立`uv --offline --no-project`环境，不修改或复用pipx site-packages。
以正常安装的Python executable选择同版本解释器，不在正常venv内安装测试依赖。
复验原57归属专项、138必要回归及1条runtime-version契约，共196条已有用例，预期全部
通过，手写预期及产品输入保持；不是新增196条或重跑真实业务。只产生合成临时数据和
隔离uv缓存。结果与正常安装/人类评鉴分开；离线依赖不可用时报告，不静默联网。
