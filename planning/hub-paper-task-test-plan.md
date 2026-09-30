# Hub 论文入口与 Codex 任务：独立验收方案

## 0.30.0 hotfix 发布前回归（待批准）

- 对象/输入：仓库 `tests/unit` 与 `tests/contract` 已有合成 fixture/fake provider，
  不执行真实整库分析、迁移、Codex 任务或 Zotero 写入。
- 命令：`.venv/bin/python -m pytest tests/unit tests/contract -q`。
- 预期：既有与新增契约全部通过；失败如实记录，不通过则不提交发布。
- 影响：测试临时目录、受控本机测试服务和 mock process；不登记正式 Vault，不改真实文库。
- 产物：汇总数量、失败明细与本验收报告；不是人工产品验收。
- 另核对版本一致、runtime-only 文件边界和个人路径/密钥泄漏，不输出秘密值。
- 通过后提交 hotfix，生成正常 release 产物并经 marketplace/pipx 安装 0.30.0，
  不提前合并 main。安装更新和服务切换单独记录；旧版来源为 release 提交 e0a0b2f。
- 人工评鉴：正常安装后的 Hub 中检查 V-JEPA 2 的 ZotFlow 阅读器、指定 cmux PDF、
  相关文件与可读预览；结果须在会话中展示，用户未确认前保持待人工评鉴。

## 目录加载失败的最小回归（新增，待批准）

- 输入：临时合成 Vault，一份含未知 sw_* 字段的无效声明；snapshot 以另一个 ID
  引用该文件路径，同时包含一个正常 artifact。资源与主题均引用这两个 artifact。
- 步骤：运行 `tests/unit/test_hub_vault.py`，覆盖新增用例和原有五项相邻回归。
- 预期：无效 artifact 与资源/主题引用被清除；正常 artifact 保留；拒绝原因仍在
  diagnostics；HubCatalog 不抛 unknown artifact。原有身份、安全和重命名行为不变。
- 影响：仅 pytest 临时目录；不启动真实服务、不访问 Zotero、不写实际 Vault、不安装。
- 产物：六项测试结果和本批次验收报告。批准后执行，不等于安装态 GUI 验收通过。

人工评鉴仍独立待做：安装新候选后，从 V-JEPA 2 卡片逐项打开 ZotFlow PDF、cmux 原
PDF、Markdown、Canvas 和笔记，确认附件正确、打开位置正确、正文可读且无机器锚点。
这些效果须在会话中展示，并由用户明确确认；合成测试不能替代。

状态：用户已批准 A；合成与定向回归已执行，213 项经定向修正/复跑通过。
B 已批准并部分执行；C 仍需单独批准。独立结果见 `hub-paper-task-test-results.md`。
适用批次：WI-053；用户随后批准安装态 hotfix 验收，不正式发布、不迁移正式 Vault。

## 安装态复验（2026-09-30）

分支 `codex/hotfix-hub-paper-tasks`，保留原 main 和已安装 0.29.0。
候选 CLI/Hub 从分支构建 wheel 后安装到独立环境，不以源码 sys.path 注入冒充安装。
使用独立候选状态和已批准 test Vault 只读 Source/论文归属；不改正式 registry。
记录安装位置、包版本、分支、源码与安装后 static 文件摘要和服务身份。
用户本轮“那就进行测试吧”批准此安装态 B 复验；C 不据此启动。
先复跑已有 UI fixture 集合，仅新增尾部块锚点隐藏（仍保留 DOM id）、行内代码不受损、
Zotero 条目选择/PDF 阅读标签区别的断言；然后执行 B 表中尚未完成的实机入口。
候选停止后原安装和服务仍可使用，无需正式发布或迁移数据来回退。

## 测试对象与边界

- 合成数据：独立临时目录、fake Zotero/Obsidian/cmux/Codex、模拟 HTTP；不使用正式文库数据。
- 唯一真实论文：V-JEPA 2。只打开和读取现有附件、分析、Canvas、笔记，不新增/删除批注，不重做已接受的内容评审或批注往返。
- 唯一真实执行对象：用户的独立 `test` Vault。系统选择器确认其目录；不注册其他 Vault、不改变正式 Hub 的目标列表。
- 候选 Hub：使用 hotfix 构建的独立已安装包、独立 Scholar 状态目录和动态端口；不替换已安装 0.29.0 或终止其他服务。
- 面向用户的展示材料保存在 `test` Vault 的独立 `Hub验收/` 目录；临时目录只放可丢弃日志与合成 fixture。

## A. 定向合成测试（先执行）

| 对象和输入 | 操作 | 预期与通过标准 | 可见产物 |
|---|---|---|---|
| 同名但无关系的文档；明确归属的资料/分析/Canvas；声明但缺失的文档 | 加载相关文件、预览并调用受控动作 | 仅暴露明确归属；缺失项有原因；陈旧关系或 symlink 不可打开；无客户端绝对路径 | 分项测试结果与 API 摘要 |
| 103 个 Zotero 子条目、错误分页、异库/异父子条目 | 分页读取并构建附件/笔记清单 | 完整读两页；错误或异属内容不冒充本论文内容 | 分页与归属用例结果 |
| 已知可执行候选、fake model/list、已确认默认模型、未知 profile/effort | 预览、确认、保存偏好、构造任务 argv/stdin | 检测零写入；确认只用审议选项；拒绝未知选项；秘密不读取；选择跨重启保留 | 脱敏配置摘要、参数与 stdin 断言 |
| 一个项目、一个 Field、双重 Field、无目标；唯一/多个 recipe | 运行隔离 DOM fixture，不打开真实浏览器 | 唯一匹配才自动选；歧义留空；缺目标引导登记；对象上下文保持正确 | UI fixture 结果 |
| 系统选择的独立文件夹、过期 token、目录 inode/registry 变化、已有 Field target | 确认文件夹并注入 CAS 失败 | 无路径请求；token 一次性；陈旧拒绝；条件回滚；整个文件夹不被误缩成 Field | 文件夹安全结果 |
| 新任务及旧版 task/run，之后改变 Default | create/resume/fork 的合成状态与配置检查 | 已有实际模型/强度不变；旧记录能恢复；改变配置须新建或 fork；不使用 --last | 状态与固定配置断言 |
| 无认证、异 Origin、raw model/cwd/command/sandbox/permission/environment | 请求相关 API | 执行/配置拒绝；设置仅有界策略选择；setup 与任务保留互斥 | HTTP 安全结果 |

批准后使用的定向命令：

```bash
rtk uv run --with pytest pytest -q tests/contract/test_zotero_related_children.py tests/contract/test_hub_paper_task_api.py tests/unit/test_hub_paper_related.py tests/unit/test_hub_target_setup.py tests/unit/test_hub_codex_profiles.py tests/unit/test_hub_ui_paper_tasks.py
```

之后仅对受影响的历史链路作回归（同一批准范围，不跑全部业务）：

```bash
rtk uv run --with pytest pytest -q tests/contract/test_hub_v3.py tests/contract/test_hub_actions.py tests/contract/test_hub_task_runtime.py tests/contract/test_hub_lifecycle_cli.py tests/unit/test_hub_v3_fields_zotflow.py tests/unit/test_hub_execution_runtime.py tests/unit/test_hub_terminal_worker.py
```

定向 Ruff/编译及 diff 检查也只在批准后执行；不借“静态检查”绕过测试独立原则。
可能创建临时依赖缓存/锁文件；仅保留测试报告，新增临时锁文件不提交。
若输入或测试范围发生实质变化，更新本方案并重新说明；修复后只重跑对应失败项和受影响回归。

## B. 单篇可见阅读验收（A 通过后）

| 步骤 | 真实输入 | 必须看到的结果 | 影响 |
|---|---|---|---|
| 从候选 Hub 的 V-JEPA 2 卡片点“在 ZotFlow 标注” | 当前登记 Vault + 当前 Local API 附件身份 | Obsidian 内 ZotFlow **Library Reader** 显示正确论文；不是独立 Zotero 窗口或 Vault Local Reader | 打开应用/窗口；插件可能更新自身缓存，不写批注或迁移文档 |
| 点“在 cmux 阅读”，使用默认打开位置，再选另一个已存在 workspace | 同一原 PDF | 指定 workspace 的 browser surface 实际显示 PDF；按钮注明不含 Zotero 批注 | 仅创建阅读 surface，不创建 workspace、不生成副本 |
| 展开相关文件 | 此论文明确关联的现有文件 | 名称、来源、状态与实际关系一致；缺失项不隐藏 | 只读 |
| 逐项点击现有分析 Markdown、Canvas、资料/批注/阅读笔记 | 仅真实存在且有关联的条目 | Hub 正文无机器注释，原文链接可点击；Obsidian 打开正确原文件；Canvas 能编辑（不保存改动） | 打开文件，不重渲染论文、不保存修改 |
| 使所用 destination 不可用（只用专用临时 surface/目的地记录，不关闭用户工作区） | 失效 destination ID | 提示重新选择；Hub 正文、文件列表继续可读 | 仅测试专用目的地记录 |

OS 返回 opened=true、HTTP 200、截图出现标签或模拟测试成功，都不能代替实际 PDF 可见证明。
若图形控制不可用，提供准确的卡片/按钮位置供用户手动验收，记录未自动核实部分；不标假通过。

## C. test Vault 的 Codex 小任务（单独批准执行）

输入准备：在 `test` Vault 的 `Hub验收/` 下建立唯一子目录，放一个 `input.md`：

```text
Hub acceptance sample
alpha = 2
beta = 3
```

先显示候选 Codex 版本、批准的模型/强度、目标的精确目录、workspace 和写入范围，再确认设置。
只允许该子目录作为 ExecutionTarget。拟运行的 bounded brief：

> Read input.md in the current working directory. Create only result.md containing a
> short sentence that alpha + beta = 5. Do not access sibling directories, use network
> tools, install packages, edit other files or launch another task. Report the file created.

模型：用户在配置向导选择的已列出模型；思考强度：该模型支持的最低适用值。
策略：workspace-write，仅该独立目标；不降低沙箱、不提供任意环境变量。
风险与影响：一次真实模型调用，可能消耗账户额度；会创建 test 输入和 result.md、候选状态/任务记录、
一个 cmux terminal surface。没有进一步授权就不删除这些产物，也不修改正式 Codex/Hub 设置。

通过标准：摘要与 TaskRun 的实际模型/强度一致；cwd 是被选的子目录；终端在指定 workspace；
TaskRun succeeded 且有明确 thread ID；result.md 内容正确；输入及其他文件未改动。
有模型目录但调用被拒绝只能记“账号调用未通过”，不能归罪于界面或宣称账号可用。

## 验收表与交付

| 项目 | 当前状态 | 批准后结果 |
|---|---|---|
| 相关文件、完整子附件、缺失诊断与路径限制 | A 合成通过 | 见独立结果；真实界面待 B |
| 模型设置、思考强度、偏好与上下文建议 | A 合成通过 | 真实调用待 C |
| 旧任务兼容与实际配置固定 | A 合成通过 | 不代表真实账户调用成功 |
| V-JEPA 2 ZotFlow Library Reader | 未验收本批代码 | 待填：GUI 与附件身份 |
| V-JEPA 2 指定 workspace 原 PDF | 未验收本批代码 | 待填：GUI 与 workspace |
| V-JEPA 2 相关文件逐项打开 | 未验收本批代码 | 待填：真实清单、正文/Canvas |
| test Vault 单个 Codex 任务 | 未执行，需单独批准 | 待填：模型/cwd/surface/result |

可见交付：`test` Vault 中的一份验收结果 Markdown（含清单、通过/失败与截图）及 Codex result.md，
仓库内只记录脱敏证据与状态。不将真实文件绝对路径、密钥、token 或全文测试日志提交 Git。
所有本轮通过项只证明该能力批次和测试范围；不自动关闭旧 Field 迁移/批注同步/发布门禁。
