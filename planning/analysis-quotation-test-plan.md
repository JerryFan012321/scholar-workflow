# 正文逐字摘录：独立测试方案（修正版 42 项已通过）

日期：2026-10-02。开发候选 0.31.1；正常安装仍为 0.31.0。
分支仍是 `codex/hotfix-project-context`，不合并 main。

适用范围：本方案记录 v4 摘录改动的历史测试，不覆盖用户随后要求的五分支/独立子节点
新输出模板。新模板由 `../skills/analyze-paper/references/analysis-output-template.md` 持有，
运行适配未完成；后续 B 必须按实际待安装格式重新准备，不沿用 A 授权生成新结构或改写旧样张。

首轮 A 已获用户批准并执行：新增 21 passed / 19 failed，相关回归 147 passed。
失败与范围记录在 `analysis-quotation-test-results.md`；首轮单 Method 输入不满足
既有 Canvas 2:1 长宽比门禁。以下修正版已获用户再次批准并执行：42 passed，0.47 秒。
实际成对预览与 Canvas 不变比较均通过；真实引文及安装态人工评鉴 B 仍未执行。

## A：合成测试与必要回归

**对象和输入**：仅 `tests/fixtures/analysis-quotations/` 的一个手写合成对象：
`SOURCE.md`（原文）、`IR.json`（四分支中的一个 Method claim、两个 point，分别含作者陈述和推断，
加三个明确 `unverifiable` 的来源缺口条目，不新增论文事实）、
`EXPECTED-EXCERPTS.md`（手写预期摘录块，不是执行结果）。附件身份、hash、页码均为合成值，
不访问实际 Zotero/Vault/PDF。负例在内存中修改这个输入，不另做真实业务操作。

**步骤与通过标准**：

1. 运行新增 unit/contract：原句须在合成原文中，英文/中文标签一致，摘录保留原语言；
   每条摘录紧随自己论述且有同一来源链接。ZotFlow 投影沿用原页级 URI；
   Markdown 来源使用原块入口。缺失/空白/过长摘录、非 boolean 设置、摘录删除/改字/追加/移位均拒绝。
2. 对同一 IR 比较启用摘录前后 Canvas 的完整 JSON：必须完全一致，不只比较节点数。
   缺口不编造引文，来源 Markdown/HTML 语法只作为字面文字显示。
3. 检查更新和 baseline：摘录纳入正文 hash；focused 保持设置，不能静默移除摘录。
   旧 profile 缺省不新增字段、不改变旧输出，不破坏历史 request fingerprint 和 sidecar。
4. 既有相关分析回归和 eval schema 已通过 147 项；本次只改合成 fixture 和测试准备，
   不重复该套回归，不运行 provider、GUI、Codex 任务或网络 probe。
5. 保留首轮的 focused 单 Method 原输入，分别开启/关闭摘录；两种情况都须被既有
   长宽比门禁明确拒绝。这是两项负例，不把旧输入改成可生成，也不以新输入通过掩盖旧限制。

修正版已执行（原新增 40 项 + 两项原输入拒绝检查，共 42 项）：

```sh
rtk proxy uv run --locked pytest tests/unit/test_analysis_quotations.py tests/contract/test_analysis_quotations_contract.py -q
```

不在本轮运行 full suite、编译、lint 或发布；后续提交前 full unit/contract 另按根规则批准。

**影响**：仓库测试环境与临时 pytest 文件；`uv --locked` 不重写 lock。
若依赖工具需要额外网络/安装权限，先报告，不静默安装其他工具。不写 Vault、Zotero、插件缓存、
正式配置或安装环境，不启停任何服务。

**可见产物**：单独结果表、用合成 IR 实际生成的正文预览；明确标为合成与来源未核验，
显示原句、链接、作者/推断归属，并记录 Canvas 完全一致比较结果。不得把手写 EXPECTED
当作已经生成成功的样张。结果保存在本 planning 下，不冒充已安装产品输出。

## B：正常安装后的单篇人工评鉴（不含在 A 授权中）

需要另行授权正常 hotfix 发布/安装，以及选择 V-JEPA 2 的少量已核原文摘录并在 test Vault
准备独立候选。保留旧样张，不覆盖正式 Vault，不重新分析整篇或扫描整库。
在会话明确请用户观察：正文原句与 PDF 对照准确、摘录和解释归属清晰、原链接仍在
Obsidian 内到对应页。Canvas 沿用已经通过的外观，不重复要求全套审美评鉴。

结构测试通过只证明生成和约束符合 IR；B 的原文真实性及人类阅读效果必须独立确认。
