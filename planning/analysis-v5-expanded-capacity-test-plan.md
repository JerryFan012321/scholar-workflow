# v5 显式扩展容量：独立测试方案

状态：用户已明确批准并执行；定向 63 passed/2 failed，完整 1418 passed/2 failed。实际结果见 `analysis-v5-expanded-capacity-test-results.md`；本次未通过，改变实现/输入后须重新批准复测。本轮不是重新分析整库或生成真实样张。

最新覆盖状态：修正后普通自动复测已执行，定向 65 passed、完整 1420 passed/11 warnings；详情见 `analysis-v5-expanded-capacity-retest-results.md`。测试执行规则以最新通用 AGENT.md 为准，旧段落中的全面审批描述仅为当时记录。

## 修正后复测（尚未执行）

用户已要求修正两项失败。v4 反例改为合法四分支 roles，唯一非法条件仍为 expanded。原 70 条输入不删减；诊断实际为 98 节点、3056×8250，仅报 aspect。expanded 的过高树采用均匀层间距补足必要宽度，层间距上限 336 px；保留原文本框大小、字体、独立节点、垂直 band 与固定端点，不改默认档，超过上限仍由原门禁拒绝。首轮修正后复测 64 passed/1 failed：原 320 px 上限低于该输入所需 332 px，已在会话说明并改为 336；不是提高 2:1 门禁或文本框上限。

新增手写几何预期：同一 70 条输入仍为 8250 px 高，宽 4125–4131 px，98 个节点；不能因改字/删节点/缩字体得到通过。须完整 conformance 无对齐、交叉、穿框或比例 finding，baseline 成功；该尺寸仅是自动几何期望，不是人工审美结论。

复测步骤与范围不扩张：先新容量+现有 v5/v5 safety 三文件，之后完整 unit/contract，指定六文件 Ruff 和 diff 空白。所有输入为仓库内合成对象；不操作 Vault、应用、服务、安装或发布，产物为独立复测报告。执行条件遵守当前根规则：普通测试无需额外批准，高推理强度测试仍须批准；本记录不推断或宣称当前宿主配置。

## 实现范围

文档级 `capacity: expanded` 只适用于 v5，将独立记录与受管节点上限从 40/96 改为 96/192；省略时保留原行为。普通成对更新拒绝改变容量档。模型、JSON schema、渲染、conformance 与 baseline 共用相应版本化上限；420 px 高度、2:1 比例和对齐/无交叉等规则不变。

## 输入与预期

测试文件 `tests/unit/test_analysis_v5_capacity.py` 使用既有 synthetic scalar fixture 和明确生成的边界输入；没有真实论文事实、真实附件或 Vault。

| 输入 | 手写预期 |
|---|---|
| 默认档 40 条、41 条 | 前者模型/schema 接受；后者模型拒绝 |
| expanded 68 条、96 条、97 条 | 前两者模型/schema 接受；97 条模型拒绝；仅证明容量，不证明几何或科学来源 |
| v4 提交 expanded、v5 提交 unlimited | 模型与 schema 拒绝 |
| 未指定 capacity | 序列化不新增该字段，默认预算不变 |
| 既有 38 条合成样本选择 expanded | 正文/Canvas 字节内容不因容量改变；通过已有 conformance，不删除独立节点 |
| 默认 baseline 通过普通更新变为 expanded | 明确拒绝，不能静默改容量 |
| expanded baseline 执行不改变内容的局部 Limitation 更新 | 保留 capacity、原配对内容和新 baseline 的容量档，不退回默认限制 |
| 自动定向修复仅切换 capacity | 拒绝；不能靠切换约束把失败伪装成修复成功 |
| expanded 合成产物某节点高度改为 421 | conformance 拒绝，容量不能绕过可读性规则 |
| expanded baseline 192/193 个独立 ID | 模型前者接受、后者拒绝；人工补 ID 仅用于模型边界，不代表合法成果或正式提交 |
| 38 条既有合成记录 + 8 个模块各 4 条独立内容，共 70 条 | 默认档拒绝；expanded 的公开成对渲染/baseline/conformance 全链路接受，每条内容在 Markdown 与独立 Canvas 节点中保留；超过 96 个实际节点但不超过 192。若几何失败如实失败，不放宽几何规则 |

baseline 的 192/193 边界同时由模型与手写 JSON schema 检查。70 条用例负责证明扩展档实际成对生成能力；仅检查 68 条 IR 能被解析不能代替这个证据。

## 执行计划

批准后先运行新增容量单测及现有 v5/v5 safety 单测，再执行完整 `pytest tests/unit tests/contract`；检查改动 Python 文件 Ruff 和 diff 空白。实际命令使用当前开发环境的既有测试运行器，记录版本和完整结果，不预填 passed。

影响仅限本仓库合成测试与临时测试目录；不写正式/test Vault、不调用 Zotero/Obsidian/cmux、不安装、不切换服务、不发布。输出为单独测试结果报告。

本方案通过后仍需正常版本化 hotfix 发布安装，冻结 V-JEPA 2 的完整 v5 IR，并另行批准单篇实机方案。届时需要人工评鉴：在 Obsidian 打开真实 Canvas，检查完整五分支、同层对齐、无交叉、文字留白、可编辑与 ZotFlow 原文跳转；容量单测不能替代这些结果。
