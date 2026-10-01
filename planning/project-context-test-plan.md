# 项目中心重构：独立测试与人工评鉴方案

状态：A 已获批准并执行，96 项新增通过；188 项相邻回归通过、1 项修正待重新批准复测。
详见 `project-context-test-results.md`；B/C 仍待人工评鉴／单独发布安装授权，2026-10-01。
分支：`codex/hotfix-project-context`；源码候选 `0.31.0`，不等于本机已安装版本。

本批只验收一个合成项目与必要的合成回归，不做整库分析、真实 Vault/项目迁移、
Zotero 写入、外部 Codex 任务或旧服务切换。不得把旧 Hub 未完成产品验收当成本批前提，
也不得把其取消标为通过。

## 1. 输入与可见预期（测试之前已经准备）

- 唯一项目输入：`tests/fixtures/project-context/`。
- 身份与选择：该目录的 `project-layout.json`、`project-context.json`。
- 七项资料：五个可定位的本地文件、一个虚构外部论文、一个故意缺失的文件。
- 所有代码、实验和结果均为合成内容，无真实科学结果或测量值。
- 手写预期：`tests/fixtures/project-context/EXPECTED-OVERVIEW.md`。
  它是独立预期，不是实际生成效果或测试通过证据；原生阅读 URI 未加入本样本。
- 反例由测试在隔离副本内构造：错配身份、丢失声明、路径穿越、symlink、重复字段、
  非法/带命令 URI、不合法 profile、重复 entry 和未核验 commit。

正式模板没有变化：V-JEPA 2 已认可的四分支 Markdown/Canvas、证据链接、字体/留白
和单篇目录不再重新生成；相关回归只用现有合成 fixtures。

## 2. A：批准后执行源码合成测试

| 检查 | 操作与预期结果 | 可见产物 |
|---|---|---|
| 模块边界 | Project 新核心不引 Hub/HTTP/外部执行；提取的 Knowledge 核心不引 Hub/Analysis；兼容导出仍是同一对象 | 定向测试摘要和失败定位 |
| 资料清单 | schema、运行校验、身份匹配、七种 entry、路径与只读防护；不自动扫描或补写 | 结构化状态；输入前后逐字节相同 |
| CLI | template 只输出空模板；validate 仅说明声明有效；overview 实际文本与独立预期逐字比较；JSON 保留 typed ref | 实际中文 Markdown、英文覆盖输出、JSON |
| 安全反例 | 错配/非法声明退出码 2；缺失与 unsafe 项仍可见；命令 URI 不启动应用 | 错误/诊断及零副作用证据 |
| 既有行为 | initializer/profile、实验档案、已认可分析渲染与本批触及的 Hub 兼容安全不回归 | 合成回归摘要，不冒充实机验收 |

执行顺序：先新切片，失败只修本问题；再做与本批改动相邻的必要回归。
同一失败至多一次定向重跑，不以失败为理由重新分析真实论文或反复做大规模业务。

批准的执行范围建议为下列源码合成测试（命令只是方案，当前未执行）：

```text
rtk uv run --with pytest pytest tests/unit/test_project_context.py tests/unit/test_module_ownership.py tests/contract/test_project_context.py tests/contract/test_project_context_cli.py
rtk uv run --with pytest pytest tests/unit/test_init_project.py tests/contract/test_init_project_profiles.py tests/contract/test_project_system_contracts.py tests/contract/test_experiment_lifecycle.py tests/contract/test_experiment_cli.py tests/unit/test_analysis_rendering.py tests/unit/test_analysis_reference_tree.py tests/contract/test_analysis_reference_tree_contract.py tests/contract/test_hub_catalog.py tests/contract/test_hub_v3.py tests/unit/test_hub_vault.py tests/unit/test_evals_schema.py
```

测试使用仓库依赖环境，必要的环境解析只影响开发环境，不是插件安装或发布。
不访问正式 Zotero、Notion、Obsidian、cmux 或账户；旧 HTTP 契约如需 listener，
只能使用测试自行管理的隔离 loopback fixture，绝不连接正在运行的正式 Hub。
提交前的完整 unit+contract/编译/lint、打包与安装另报范围并取得批准，不默认包括在 A 内。

## 3. B：人需要评价的功能必须明确提出

**项目总览的清晰度和使用便利性需要你亲自评鉴，自动测试不能替代。**

A 完成后在会话展示实际 Markdown，与现在的手写预期并列。请判断：

1. 是否能看出该项目要做什么，以及代码、论文和结果为什么相关？
2. 能否直接找到所选材料；缺失和“未核验”是否容易理解？
3. 这种轻量索引是否值得保留，而不是又制造一个多余首页？

若认为不合适，只修改这一个样本的呈现契约，再给出新的预期；不扩展成新 Hub。
此阶段不要求操作正式文库或复验既有批注往返。

## 4. C：需要安装的功能，走正式 hotfix 安装流程

只有在后续明确授权提交、独立版本发布和安装后才进入 C：

- 本 hotfix 作为正常可发布的 `0.31.0` 候选提交、打包、发布和安装，不用临时 venv 冒充。
- main 不提前合并；回退到既有 `0.30.0` 正常安装来源。
- 将同一个合成项目放到独立验收目录，运行已安装 CLI 三个命令并保存实际输出。
- 验收不使用真实论文/正式项目，不启动 Hub，不改服务或 workspace。
- 验收通过后再单独决定 main 合并及下一切片，不在此次 A 授权中夹带发布。

## 5. 结果记录

批准后新建 `planning/project-context-test-results.md`，逐项记 input、operation、expected、
actual、evidence 和 pending/pass/fail。保留失败，不以开发树存在或预期样张代替实际结果。
当前 A 仍有一项修正待复测；B/C pending。以下方案中的“未执行”措辞保留为测试前预案，
实际执行状态以本文件顶部及独立结果单为准。
