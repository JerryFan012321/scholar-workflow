# v5 扩展容量测试结果 — 2026-10-04

结论：未通过；不提交为已验证、不发布安装、不生成正式 Vault 成果。用户明确批准当前测试方案后执行，测试期间未修改实现或输入。

## 环境和范围

- 本仓库 `.venv/bin/python`：Python 3.14.5；pytest 8.3.4；Ruff 0.16.10（uvx）。
- 对象为合成 IR、已有 scalar fixture、模型/schema、成对投影和更新/修复边界。
- 未操作 Zotero、Obsidian、cmux、正式或 test Vault；未安装、切换服务或发布。

## 实测

| 检查 | 结果 |
|---|---|
| `.venv/bin/python -m pytest -q tests/unit/test_analysis_v5_capacity.py tests/unit/test_analysis_v5.py tests/unit/test_analysis_v5_safety.py` | 63 passed / 2 failed，1.33 秒 |
| `.venv/bin/python -m pytest -q tests/unit tests/contract` | 1418 passed / 2 failed / 11 warnings，75.27 秒 |
| `uvx ruff check`：models、complete_reference、complete_conformance、updates、batch、新 capacity 测试文件 | All checks passed |
| `git diff --check` | 退出码 0，无输出 |

以上 shell 命令实际均通过 `rtk proxy` 调用。11 条警告来自 Swig 类型及多线程进程 fork 的弃用提示，不隐藏为无警告通过。

## 两个失败及证据

1. `test_unknown_capacity_and_old_version_are_rejected`：把 schema_version/framework 改为 v4 后，仍提交五个 v5 roles，触发 `whole profile must declare all framework roles or omit roles`，所以未到容量校验。拒绝行为发生了，但测试并没有证明预定的容量边界。下一轮应使 v4 反例的其余字段合法，再单独引入 expanded；不能只删除错误信息断言来凑通过。
2. `test_seventy_independent_records_reach_the_paired_projection`：70 条独立记录通过模型并产生候选，但 `create_baseline` 返回 `cannot baseline a nonconformant analysis pair: canvas-aspect-limit`。实际成对正式流程不接受该布局；不能用模型接受、文件生成或其他 1418 项通过冒充可用。容量档没有绕过原几何门禁，这一安全行为正确；长树的布局能力仍不足。

## 下一最小修正

- 只修正 v4 反例中的 roles，使其对应 v4 四分支；保留 expanded 必须拒绝的预期。
- 保留 70 条内容及每条独立节点、同层对齐、方角无交叉、可读字体和留白。修改布局以真正满足 2:1；不得隐藏分支、删内容、合并节点、缩小字号或放宽比例。
- 修改后更新独立几何预期和影响说明，重新取得测试批准；不得沿用本次批准自动复测。当前代码和输入保持本轮失败状态供审议。
- 实现与合成测试通过后，仍需正常 hotfix 发布安装及单篇 V-JEPA 2 的来源核验和人工 Canvas 评鉴；本轮不证明模范 Vault、项目或实验阶段完成。
