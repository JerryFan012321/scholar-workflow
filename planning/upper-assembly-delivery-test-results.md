# 上层组合交付准备：实际结果

2026-10-10。当前分支 `codex/hotfix-knowledge-ownership`，基线
`b9f2ffeeb344e2524401ebcf48f8f40301da190a` 加未提交开发改动。
预期先于执行，见 `upper-assembly-delivery-test-plan.md`。
后续实存复核澄清：下表“两个0330根、8项生效清单”中的8项只属于原根，历史
0330-replay仍6项；不得推断两根引用集一致。当前观察见stage1-current-state-audit.md。
上一轮为实际进展（论文单元清单开发、独立测试和 stdout 样张），不是等待或完成 G17。

## 检查结果

| 对象 | 观察与结果 | 不能证明的内容 |
| --- | --- | --- |
| 全部 unit/contract | 2458 passed，106.05 秒，11 条既有 PyMuPDF/fork 弃用警告 | 宿主触发、人工评鉴、正常安装或整库业务 |
| 文档修正后必要回归 | eval schema、runtime version、旧 novelty/tree schema 共 38 passed，0.29 秒；包含在既有全集，不加总为新增 | 模型路由/科学支持 |
| 16 个 runtime SKILL | 全部 quick_validate 通过 | 实际宿主自动选择或内容质量 |
| 26 个改动 Python 文件 | Ruff 通过 | 全源历史 lint 债清零；上一轮广泛检查的52项历史诊断未在本轮解决 |
| 本地开发 wheel | 构建成功；108 Python 模块和3静态文件与源码逐字节一致，入口/版本正确，无范围外文件 | 完整插件 release 或正常安装；版本仍是源码当前0.42.0 |
| 运行说明链接 | 检查28条相对 Markdown 链接及7个共享路由目标，无缺失 | 原生链接实际点击或外部网站可用性 |
| 有限发布路径扫描 | runtime allowlist 中未发现指定个人根/临时测试根或常见 token 前缀匹配 | 完整秘密审计或所有类型凭据不存在 |
| 论文格式守恒 | analysis 核心和 analysis-output-template/analysis-v5-format/analysis-format 与 HEAD 无差异 | 本次新科学/人工验收；论文 reproduction reference 的交接链接确有修正 |
| 正常安装身份 | 显式 `/Users/jerryfan/.local/bin/scholar-workflow --version` 退出0，报告0.42.0 | 新增开发能力已安装 |
| diff/版本元数据 | diff --check 通过；四处版本与uv.lock未变 | 已提交、发布或main已合并 |

开发 wheel 位于 `/private/tmp/scholar-upper-assembly-build.4mbwtZ/`，属于可丢弃构建
检查，不是给人审阅的 Vault 产物。SHA-256：
`358844501a8d26f015908101e12d1996b18650f386154b237b6958ab5afd20bc`。
没有用这个仍标0.42.0的开发包替换正常安装，也没有运行make-release的分支切换步骤。

## 独立复核发现与最小修正

1. `build-literature-tree` 的全 skill managed-block/Mermaid 限制与新的 stdout 模式冲突。
   现仅限定旧概念树/ledger writer，新模式仍服从其独立契约；旧格式/写入路径未改。
2. 中英文根 README 指向不会发布的 planning 文件，并保留私人首个 Source/Field 的安排。
   改为现存 runtime 原生打开说明、通用逐 Field 边界，明确 Hub 仅保留兼容。
3. project-context 的 undelivered 字样不适合作为后续同批新能力的长期接口定义。
   改为独立操作及实际安装版本检查，仍不是只读归属检查的副作用。
4. 阶段规格要求固定六项复现交付在公共 runtime reference 中，先前仅各专属说明零散持有。
   新增 `references/reproduction-delivery.md`，仅持六项交接内容与职责路由；两专属 reference
   引用并移除相应通用重复项，论文 IR/成对提交与项目 layout/Run/report/new-root 边界保留。
   独立只读复核确认覆盖完整，不新增 manifest/schema/状态库/执行入口或推理流程。

以上只修运行说明和交付约定，不改变已测试的产品 Python。六项规则落地本身不等于
真实对象全部通过。描述/触发策略未改，相关 routing/safety/outcomes 保留状态区分。

## 第一阶段完整范围审计

| 必须交付对象 | 已有有效真实证据 | 仍缺/不应混淆 |
| --- | --- | --- |
| 模范 Vault | test Source/Field、完整trio、3便携清单/6资产、正式登记/新根恢复/反链回执与原生截图存在；Canvas/图片和折叠体验认可保留 | 已审折叠候选尚未canonical采用；新清单导航待人；显式来源空缺保留，不认证全篇科学支持 |
| 模范项目 | 两个model-project-0330根、稳定identity、源码/输入、8项生效清单和新克隆重建记录保留 | 新PROJECT只有独立候选，尚未真实采用；新skill安装与VSCode导航待验 |
| 模范实验 | Run/3Attempts/report/acceptance/CLI receipts、失败日志和确定性指标存在，历史执行0.33.0 | review-experiments的2Run/4Attempt是合成输入，不是新增真实科研结果；使用体验待人，backup未验证 |
| 外部工具 | Local API、ZotFlow页/批注、Canvas显示/正文点击、cmux原PDF显示与操作说明/机器结果保留 | 新导航原生点击、cmux翻页/缩放便利性待验；本轮没有重新观察GUI |

固定六项现有素材大多分布在已命名的对象/回执中，不因缺统一新manifest而凭空增加门禁。
Source 历史“复现”目录不属于当前15文件export是已知边界，不当成内容丢失。
证据定位见 `knowledge-ownership-test-results.md`、`source-rebinding-results.md`、
`folded-quotes-test-results.md`、`model-project-experiment-results.md` 与
`native-tool-interaction-results.md`；本轮只读核对，不重新执行这些有效业务。

## 后续边界

已单独询问：通过检查后是否授权这一批按可正常发布安装的0.43.0 hotfix交付。
收到明确回复前，不因goal续行自动提交/推送/安装。版本尚未提升，不声称候选发布身份。
授权后仍须从确定、干净的hotfix源码经既有脚本生成runtime-only release，核对完整
manifests/contracts/references/skills/源码，再正常安装并保留0.42.0回退点；不合并main。

真实内容采用/迁移另行处理；折叠候选通过人工评鉴不等于已经commit/provider apply。
人工审阅对象、打开方式与标准必须在会话明确，不用自动测试或安装替代。
本轮未改真实Vault/Zotero/项目/实验、未启动或关闭服务、未迁移集合，G17仍未完成。
