# 上层组合 hotfix 交付准备：独立测试计划

2026-10-10。上一轮已完成单 Field 清单开发验证；本轮不新增产品范围，检查这一批
已有能力是否可交付。先记录预期，再执行测试；不以测试通过替代人工或安装态验收。

## 对象与输入

- 当前 `codex/hotfix-knowledge-ownership` 未提交开发树与全部既有 unit/contract fixture。
- 已有 Source 初始化、单篇 owner 查重、Field 引用与论文清单、literature-preview、
  organize-project 和 review-experiments；原论文分析/Canvas/图片/折叠契约保持。
- 本地 wheel 只作打包检查，仍保留源码当前版本，不宣称正式候选、安装或发布身份。
- 真实 Vault、Zotero 文库、项目源码/实验、正常安装目录和运行服务均不是测试写入目标。

## 步骤与独立预期

1. 并行只读审查运行 skill 与 canonical references、release manifest/打包边界，
   以及第一阶段四类交付的现存证据。报告可重现的真实缺陷，不扩建控制面或新的状态源。
2. `rtk proxy uv run --offline --with pytest python -m pytest tests/unit tests/contract -q --tb=short`。
   预期全部通过；任何失败按实际原因处理，不因期望通过而删除检查或重做真实业务。
3. 逐项 quick_validate 已存在的 16 个 runtime SKILL，检查本轮改动 Python 的 Ruff、
   `git diff --check`、双 manifest/包版本与公开 CLI 身份。广泛历史 lint 债独立标明。
4. 通过 `mktemp -d` 创建专用可丢弃构建目录，用 `uv build --offline --wheel --out-dir`
   构建 wheel。只检查 archive：新 workflow/knowledge 模块、既有 analysis/project 与
   CLI、静态资源、版本/entry point 都存在且与源码字节相符；不含 tests/planning/
   dev-guide/私密配置或缓存。正常插件 release 必须另含 manifests/contracts/references/
   skills；不把 wheel 单独当成完整插件，不运行会切换 release 分支的脚本。
5. 独立记录结果、缺陷、仍缺的真实/人工/正常安装证据。保存报告于 planning，
   不把测试结果写进运行期 skill 或承诺未实现的发布状态。

只读审计定位了运行说明缺口：旧文献 writer 的约束作用域、README 的非发布层链接/
个人验收安排，以及共享六项复现交付只存在开发规格。按已存在的目标最小修正文档后，
追加检查 runtime 相对引用的目标存在性、16 skill 基础校验及 eval schema；不重复模型
执行或真实复现，也不把静态引用存在当作宿主触发/人工/安装通过。产品 Python 未变化，
完整回归覆盖的代码不因这次文档修正失效。

## 影响与完成条件

测试仅使用隔离 fixture、pytest/uv 缓存和专用构建目录；不调用真实阅读器、服务切换、
网络业务写入或整库分析，不执行真实实验。构建不是安装态验收。
发布、安装、main 合并及任何真实内容采用/迁移分别判断权限；本轮不自动实施。
只有全部实际结果与已知限制记录清楚，才能称“交付准备检查完成”；完整 G17 继续按
`reproducible-exemplars-stage1.md` 判断，不能缩成这份计划或自动测试。
