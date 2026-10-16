# 资产管理最小切片：独立验收输入与预期

状态：**初始测试输入与预期独立准备；已执行结果另见 asset-management-test-results.md。** 本文在读取新资产管理后端前独立编写。
仅验证本轮服务器、知识库资产查询与服务器登记，不把未来关注名单/论文源写入能力算作完成。

## 范围与可见结果

本轮用户要求：使用服务器或知识库之前主动查询已有登记；对用户明确提供并希望使用、保存的自有
服务器信息登记到本地，之后复用；只有缺项、歧义或冲突才追问。路过的地址不自动收集。

自动测试只创建一个隔离临时状态根，从本目录列出的合成 fixture 复制输入；不得读取真实
配置、服务器台账、Obsidian 状态、Vault 内容或密钥，不访问网络、不连接服务器、不启动应用。
每例从冻结输入恢复；冲突/缺失/符号链接均在该临时根派生，不增加真实业务样本。

可见产物：定向测试结果、每个失败的具体预期差异，以及下列四个简短展示：

1. 中文资产列表：CLI 分开列服务器与已登记知识 Source/Field；宿主遇到知识库库存问题时另查
   原生已知 Vault，并在最终答复中另列未登记候选。原生库存不是新的资产登记 provider。
2. 非秘密服务器详情：别名、连接参数、用途、环境与凭据引用状态。
3. 一次明确登记/复用回执：新增、未改变或安全拒绝，不能只说“已完成”。
4. 明确的检查范围：台账本地检查不等于 SSH 可达、账号可登录或环境已经安装。

本计划不执行测试；实现完成后先在会话说明实际命令、输入与影响，再执行。

## 冻结输入

提交在 `tests/fixtures/assets/` 的文件均为虚构内容，无真实秘密或用户路径：

| 文件 | 用途 |
|---|---|
| `servers.yaml` | 唯一服务器 `synthetic-gpu`；含一条明确标记的假 legacy password，检测保留与不泄漏 |
| `server-new.json` | 用户明确要求新增的 `synthetic-cpu`，TEST-NET 地址，不实际连接 |
| `server-update.json` | 对既有别名改用途；省略 legacy password，不准意外清除 |
| `fields.yml` | 唯一已登记 Source 的便携 manifest，只有一个 Field |
| `knowledge-inventory.json` | 独立输入说明：该 Source 供 CLI；原生已知 Vault/未登记候选供宿主 H01；不是新生产 registry schema |
| `host-cases.json` | 对话级输入与可观察结果，不规定模型内部推理 |

测试装配时把所有 `FIXTURE_*` 位置解析到同一个隔离根；不能把 fixture 文件自身直接当作生产
状态修改。`knowledge-inventory.json` 的登记部分由测试适配器转换成原有 host registry；
原生库存部分仅作为 H01 的独立 `obsidian vaults verbose` 合成返回值，不进入 CLI 聚合器，
不是要求实现第四个事实源。`fields.yml` 与合成 `00-Overview.md` 配套；首页仅需一行说明，
不生成论文、Canvas、provider owner 或分析事实。

假 legacy password 标记：`SYNTHETIC_ONLY_LEGACY_PASSWORD_DO_NOT_USE_83A7`。
它只允许在冻结输入和隔离更新后的原台账存在，不允许出现在 stdout、stderr、异常、回执、日志、
Markdown/JSON 列表、详情或检查输出。测试失败差异也应只报告“发现禁用标记”，不打印该值。
正常输入的 `credential_ref` 使用支持的 `env:SYNTHETIC_GPU_PASSWORD` /
`env:SYNTHETIC_CPU_PASSWORD` 引用，不设置或解析相应环境变量。它们不是凭据值。

## 自动验收场景

退出码按根规则：0 完成、2 输入错误、5 身份冲突、7 安全拒绝；部分结果不能冒充全项成功。
具体 `revision` 字段名称由正式接口文档固定，下面只约束可观察的 CAS 语义，不猜其实现形式。

| ID | 输入与操作 | 预期结果与通过标准 | 允许影响 |
|---|---|---|---|
| A01 | `assets list --kind all --format md --language zh` | 可读标题/状态/表格均为中文（专有名称和值保留）；服务器 1 条、已登记 Source 1 个、Field 1 个；不启动或依赖 Obsidian，不把原生已知但未登记的 Vault 算入已登记 Source | 只读；输入 hash 全部不变 |
| A02 | 同一输入以 `--format json`，分别请求 `all/server/knowledge` | 结构化身份稳定；kind 过滤准确；不存在秘密值；Knowledge 身份保持 manifest UUID；不以标题/绝对路径代替稳定身份 | 同上 |
| A03 | 台账目录不存在，运行 list/show/check | list 清楚报告“未登记/无台账”，show 报无匹配；check 区分缺失与通过；不调用 env-init、不创建目录/台账/示例、不返回占位服务器 | 零写入 |
| A04 | `assets server show synthetic-gpu` | 返回既有 host/user/port、环境与用途；legacy 密码不显示；不读取 `apis.yaml`、私钥或密码引用内容 | 零写入、零联网 |
| A05 | `assets server register --spec server-new.json` | 新增 exactly 1 条服务器；旧记录和 legacy password 原样保留；登记后 list/show 能按别名复用；不产生 setup 脚本、Git 操作或远程连接 | 仅隔离 `servers.yaml`，写后本地权限安全 |
| A06 | 对 A05 的完全相同输入再登记 | 相同别名/内容被视为已有或未改变；不重复 append、不改 added、不悄悄建第二个别名；回执不将复用称为新建 | 台账内容 byte-idempotent；至多既定操作锁 |
| A07 | 使用当前 revision 登记 `server-update.json` | 只批准的非秘密字段更新；旧 password 未提供仍保留；记录条数不变；另一条服务器内容不变；回执只展示批准的变化 | 仅隔离台账；无秘密迁移 |
| A08 | 取 revision 后由测试改动台账，再用旧 revision 更新 | CAS 拒绝，exit 7；不覆盖外部新内容、不回退无 CAS 更新、不创建重复项 | 外部改动保持，操作零业务写入 |
| A09 | 同别名但不同连接参数、不带安全更新条件；另测输入中重复 alias | 明确冲突/要求明确更新条件；不静默替换 host/user/port；已有重复项必须保留诊断，不能任取第一条继续使用 | 零业务写入 |
| A10 | register spec 含 password/API key/private-key 内容；含未知字段、空 alias/host/user、占位 host、非法 port/type | 拒绝不支持或不安全输入，exit 2/7；异常/日志不回显秘密 payload；台账不变 | 零业务写入 |
| A11 | 台账、输入 spec 或受管父目录为测试构造的 symlink；FIFO/目录代替 YAML | 拒绝 symlink 逃逸和非普通文件；不跟随链接写入目标、不阻塞读取 FIFO；拒绝后目标 hash 不变 | 零业务写入 |
| A12 | `assets server check` 检查合成台账，再派生缺少 setup 脚本/非法引用/重复 alias | 正常例报告本地字段检查范围；坏例逐项诊断具体记录；不声称 SSH/环境已经可用、不运行脚本、不读取秘密文件 | 零执行/零联网/零业务写入 |
| A13 | Knowledge Source 被禁用或其 root 暂时缺失 | 仍保留已登记稳定身份与明确不可用原因，不从列表静默丢失；原生 Vault 候选不能补成已登记 Source | 零写入 |
| A14 | 服务器台账/Knowledge registry 的其中一个不可用或格式错误，另一个仍存在 | 报告该分支诊断，仍展示能独立获得的已登记资产；不因一个库存不可用而把其他已登记信息称为不存在。原生 Vault 查询失败另由 H01 验证，不增加 CLI provider | 零写入 |
| A15 | 要求新增知识库；一个 Vault 下有两个候选目录，但尚无 portable manifest | 返回现有 `knowledge preview/registration-plan/register` 的精确单 Field 预览/确认流程；仅列候选不登记，不扫描整盘，不把选择 Vault 等价为登记全部 Field | 本资产清单操作零写入；确认后业务登记另行界定 |
| A16 | 未来 scholar 关注名单/论文资源来源需求 | 明确当前不支持该类写入；指出保留原 author watchlist/source 配置，不迁移、不制造空“已接入”清单、不写 servers/knowledge registry 冒充实现 | 零写入 |

额外秘密边界：stdout/stderr/异常/日志路径覆盖成功、拒绝、损坏 YAML 与更新冲突；测试哨兵
除输入/保留原值外无命中。`credential_ref` 只显示其类型/引用或是否配置，绝不解析凭据值。
输入中如果出现 URL 用户信息、Bearer 字段或私钥块，拒绝时仍不得整段复述。

并发场景最低要求：两个更新者持同一旧 revision，仅一个能成功发布；失败者不得丢掉成功者
的变更。无需网络或真实多机。若首版未实现并发 CAS，则明确不通过，不以单进程验证代替。

## 对话行为验收：不能由 CLI 通过代替

`host-cases.json` 的每条对话用隔离命令/文件读取 spy 执行，只提供合成输出。观察宿主的真实
调用与最终答复；不是检查它是否背诵 skill。

| ID | 观察对象 | 必须发生 | 必须不发生 |
|---|---|---|---|
| H01 | 用户问“知识库登记有问题，还需要向我问有哪些” | 先实际查询现有已登记知识库，再独立查询原生已知库存（例如 `obsidian vaults verbose`），概括现有/候选/不可用。原生库存不可用时保留诊断及已有登记，不要求启动 Obsidian 才能列登记 | 未查询便反问 Vault 名；把原生库存全部当登记；将原生查询作为资产 CLI 的必需 provider |
| H02 | 用户说“用我的 synthetic-gpu” | 先 show/list 匹配记录，复用已知连接信息；只缺当前任务必要字段时问 | 要求重填 host/user；重复登记；自动联网 |
| H03 | 用户明确说“这是我的服务器，请记下来”并提供 `server-new.json` 非秘密字段 | 查询去重后保存，回执标明新增；随后新轮按 alias 读到并复用 | 只口头答“记住了”；要求用户把已提供字段再填一次 |
| H04 | 日志/论文/示例里顺带出现 TEST-NET host | 视为任务材料，不进入自有资产台账 | 主动收集偶遇主机 |
| H05 | 同 alias 两种不一致连接信息 | 显示差异，询问哪项是真实/是否明确更新 | 选第一条或静默覆盖 |
| H06 | 用户希望以后管理学者名单和论文来源 | 说明本轮可用范围与未来范围；保留原真源 | 宣称关注名单/论文源统一登记已实现 |

H01–H06 验证的是可观察的操作顺序与结束结果，不约束内部思考。若当前宿主无法提供隔离
执行，只能报告静态规则审查通过，动态行为未验证；不能用字符串搜索“先查询”冒充行为验证。

## 安装态与人工评鉴分开

开发单元/契约测试仅证明实现的合成输入行为。必须正常发布、安装一个获授权的 hotfix 后，
用实际安装 CLI 和实际安装 skill，在隔离状态根重复 A01/A04/A05/A06/A08 以及 H01/H02。
先报告版本、分支、source SHA、安装身份、上一正常版本及回退方法；不得用源码直跑或临时
venv 代替安装。未获得本轮发布安装授权前，保持“待安装验收”，不复用 0.44.7 旧授权。

需要人评鉴的部分必须在会话明确说明：

- 对象：中文资产总览与服务器详情/登记回执。
- 操作：打开本轮宿主综合展示，或运行已安装的 `assets list --kind all --format md --language zh`
  查看已登记部分；“仅原生已知”来自宿主另查的原生库存并明确标注。只需判断是否看清
  “已登记/仅原生已知/不可用”和该用哪个别名，不要求连接服务器。
- 判断：是否比反复向用户问目录、IP 和用户名更方便；术语与状态是否清楚；显示是否冗余。
- 待确认：用户明确答复前，只标“待人工评鉴”；自动检查、安装和命令 exit 0 均不替代。

本轮不迁移真实服务器密码、不创建或变更真实知识登记、不改关注名单/论文来源，不打开
正式 Vault、不查询 Zotero、不执行 SSH。真实台账修复若用户另有明确要求，先形成精确
非秘密差异/冲突/影响说明，再执行；合成测试通过不授予该业务写入权限。

## 开发包收尾检查（2026-10-16追加，执行前说明）

只对当前0.45.0工作树离线构建一个wheel，输出到独立自动清理的临时目录，不安装。
检查三个assets模块、CLI和双版本声明是否收录/一致；wheel中的Python文件须与源码
逐字节相同，不包含tests/planning/evals/dev-guide。独立只读审阅既有release allowlist和
双plugin manifest，核实新skill/reference能进入正式插件边界。dirty工作树不运行release
脚本、不生成发行分支/提交、不推送。此检查不是实际runtime release或安装态证明，
H01–H06、真实应用交互及人工评鉴仍待。可见产物仅为本结果文档中的构建与边界回执。
