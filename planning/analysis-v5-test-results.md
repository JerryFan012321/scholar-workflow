# 五分支论文解析树：本轮测试结果

2026-10-04。用户已批准独立合成测试，并明确 Canvas 必须对齐、没有交叉。

## 结论

### 2026-10-04 人工评审前置修正及复验

用户明确“开始执行”后，最小修正4项lint：拆分同名兼容导入、删除两测试文件的多余导入空行、去除_node_id.encode的默认UTF-8参数。输入、模板、几何坐标和门禁未变。

实际结果：v5定向53 passed（0.88秒）；完整unit/contract 1408 passed、11 warnings（73.16秒）；原五文件Ruff All checks passed；skill frontmatter和git diff --check退出0。完整回归警告仍为SWIG及multiprocessing fork弃用警告。

自动前置检查现已通过；安装态公开流程、真实来源核对和Canvas人工评鉴尚未执行。本轮未提交、发布、安装或写入真实样张。

### 2026-10-04 修正后批准复测

用户明确批准修正后的方案，并询问1 px差异原因。执行期间未改源码或输入。

| 检查 | 实际结果 |
|---|---|
| 两个v5测试文件 | 53 passed，0.88秒；G-03/G-04均通过 |
| 完整unit/contract | 1408 passed，11 warnings，74.05秒 |
| 指定五文件Ruff | 4项未通过：models及两个v5测试文件的I001；safety测试_node_id的UP012 |
| skill frontmatter | Skill is valid，退出0 |
| git diff --check | 退出0 |

G-03的1 px不是渲染漂移：固定整数坐标不变，标签底部9103+66=9169，内容底部9039+129=9168。原预期只考虑内容框；修正后的测试继续要求明确拒绝超过2:1的布局，没有引入容差或放宽规则。
G-04检查精确Markdown转义摘录且Canvas不重复摘录。11条警告为5条SWIG和6条multiprocessing fork弃用警告，未因此改动业务代码。
本轮没有触碰Vault、外部应用、现存服务或安装环境，没有提交发布。自动回归通过不证明真实论文知识准确性、新版公共提交链或安装态Canvas人工评鉴；Ruff仍未通过，不宣称可发布。原失败记录保留在下节。

### 2026-10-04 用户批准后的实际补充结果

用户明确批准当前 supplemental plan 后，按原输入和原代码执行；没有修改 fixture 或放宽规则。

| 检查 | 实际结果 |
|---|---|
| v5 定向与补充 suite | 51 passed / 2 failed，0.90 秒；其中补充26项为24通过、2失败 |
| 完整 unit/contract | 1406 passed / 2 failed / 11 warnings，74.07 秒 |
| 指定五个 Python 文件 Ruff | 未通过，20项：导入/导出排序、旧兼容 re-export alias、字符串括号、pairwise、Iterator、encode与with风格 |
| skill frontmatter | 通过：Skill is valid |
| git diff --check | 通过 |

失败原样保留：

- G-03：固定整数拉伸后的实际 bbox.max_y 为9169，而输入和断言写9168。
  失败在输入 bbox 断言，尚未触及该例的 aspect finding 校验，不能记为几何拒绝通过。
- G-04：模型、baseline、conformance、三节点布局、正文/源链接断言已经执行通过，
  随后的引文原始字符串断言失败：Markdown 为 `Q\_LIMIT`，断言却查 `Q_LIMIT`。
  不能删除转义或改变引文内容来凑通过；该例整体仍记失败。

完整回归同样只有这两项失败。JUnit 保存于本地忽略目录
`acceptance/analysis-v5-synthetic/full-unit-contract.xml`，不提交生成产物。
其余 U/G/P 案例通过，仅支持各自独立合成接口结论，不能证明新增公共 v5 提交链、科学来源或GUI。
运行期间未改变源码/输入，未访问真实 Vault/应用，未提交、发布或安装。
修正输入/断言或 lint 后，须展示更改及复测范围并重新确认；当前版本仍不具备放行依据。

### 先前结果（保留历史范围）

**下表是上一轮已批准范围的结果，不代表最新修正已通过。** 后续只读审计发现额外边、
人工遮挡、浮点 N-11 和稀疏单链布局缺口；源码与整数断言已补修，新精确输入/驱动已准备，
尚未运行。随后只读复审又补人工边绕过和浮动端点漏检，追加 G-05～07，仍未运行。
再补 v5 point 标题/标记入口漏洞，准备 P-01～10（含 v4/v3 正向兼容），也未运行。
见 [本轮补充测试方案](analysis-v5-supplemental-test-plan.md)。

**上一轮定向自动检查通过；安装态人工评鉴尚未进行。** 没有覆盖 test Vault 原图，
没有重做论文分析、整库业务、正式迁移、提交、发布或安装。

| 项目 | 实际结果 |
|---|---|
| 最终定向 unit/contract 回归 | 164 passed、2 skipped，2.83 秒 |
| 五分支、完整命名子槽位、逐点可编辑 | 通过；38 条输入均保留 |
| 同深度左边缘对齐 | 通过；错位变体被拒绝 |
| 直角无箭头连线、无交叉、无穿框 | 通过；跨分支错接被拒绝 |
| 原文页号、独立正文反链、证据归属 | 合成输入投影通过 |
| 正文逐字摘录、Canvas 不放摘录 | 通过；独立合成来源核对，不宣称真实 PDF 核验 |
| 旧 v4 框架、摘录、更新与批量回归 | 指定既有 unit/contract 通过；不证明新版本真实迁移 |
| 新模块和独立测试 Ruff | 通过 |
| diff 空白检查 | 通过 |

## 实际合成图，不是截图或事实压缩

输入为虚构 **Synthetic Scalar Reader**，不是 V-JEPA 2。保留 38 条独立记录，
包括 4 条合成作者事实、1 条推断、33 条带理由的 availability；结构容器不伪造父级事实。
实际生成 **58 个节点、57 条连线**；包围盒 **3056×4538 px（约 1.485:1）**，
单框最高 **129 px**，符合性 **0 findings**。未修改 40/96/420px/2:1 限制。

产物保存于仓库内，未写入临时目录或真实 Vault：

- [完整 Markdown](acceptance/analysis-v5-synthetic/Synthetic%20Scalar%20Reader%20Analysis.md)
- [原生可编辑 Canvas](acceptance/analysis-v5-synthetic/Synthetic%20Scalar%20Reader%20Analysis.canvas)
- [sidecar](acceptance/analysis-v5-synthetic/Synthetic%20Scalar%20Reader%20Analysis.analysis.json)
- [几何与符合性结果](acceptance/analysis-v5-synthetic/geometry-and-conformance.json)

来源 ID `SYNTH001` 为合成占位，不是真实 Zotero 附件；不要点击它验证外部阅读器。
这些是开发树生成产物，不是已安装插件的运行证据。

## 首轮失败与修复记录

首轮：**25 passed、1 failed、2 skipped**，0.35 秒。独立几何测试使用了
`styleAttributes.path`，而已安装 Advanced Canvas 的 square 路由字段是
`styleAttributes.pathfindingMethod`。按插件实际源码更正测试字段后重跑；没有改变
独立事实、标签、对齐/无交叉预期或预算，也没有把首次失败改写成首次通过。

只读复审另发现并修复：非文本节点附带 `text=None/list` 导致校验崩溃的可能性；
摘录邻接及未知管理块锚点检查；合法多行正文误判；重复实例的 baseline 标签/标题层级。
这些源码审查修复不能冒充每种变体都已独立运行测试。

## 未执行与未核验

两项明确 skipped：N-18 长输入/预算边界尚未准备；v4/v5 更新安全完整矩阵的
精确 base、hash 与更新 payload 尚未作为独立输入展示。既有更新单测已跑，但不替代它们。

上述“尚未准备”是上轮执行时的状态。现在精确输入与 26 个具体补充案例已准备，原两个空
skip 占位已由具体 suite 替代；仍未执行，不能修改历史 164/2 或宣称这些新案例通过。

**仍需人来评鉴**：正常安装新 hotfix 后，在独立 test Vault 新目录观察完整图，
检查可读性、美观、编辑和点击留白。当前安装的 0.31.1 不包含本轮 v5 实现。
V-JEPA 2 新图、实际 ZotFlow 跳页、真实科学论点/引文、全量发布回归均未由本次测试放行。

## 可复现输入与命令

[独立输入和手写预期](analysis-v5-independent-acceptance.md)，
[转录 fixture](../tests/fixtures/analysis_v5_toy.json)，
[独立测试](../tests/unit/test_analysis_v5.py)。fixture SHA-256：
`89640ecef880ec49bdf4210f440b7938952b0529267f09aae55a02faafa2a5d4`。

```sh
rtk proxy uv run --locked --with pytest pytest \
  tests/unit/test_analysis_v5.py \
  tests/unit/test_analysis_reference_tree.py \
  tests/unit/test_analysis_quotations.py \
  tests/unit/test_analysis_updates.py \
  tests/unit/test_analysis_batch.py \
  tests/contract/test_analysis_contract.py \
  tests/contract/test_analysis_reference_tree_contract.py \
  tests/contract/test_analysis_quotations_contract.py -q
```
