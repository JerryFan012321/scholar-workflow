# 论文分析 v5：独立验收输入与手写预期

状态：**用户已批准本文件展示的测试范围；执行结果另行记录**。

本材料独立依据 `skills/analyze-paper/references/analysis-output-template.md` 与其中引用的证据、链接和兼容边界编写；没有读取生产生成器、复制其输出或运行测试。它约束可观察的末端产物，不规定阅读、推理或写作过程。下面的 `v5` 是拟实现版本，不能据此宣称当前插件已支持。

## 对象、影响范围与用户将看到什么

- 唯一正向对象是虚构论文 **Synthetic Scalar Reader**。输入正文、命名槽位和预期都在本文件中，不使用真实论文、Zotero、PDF 或 Vault。
- 开发阶段只在隔离的合成工作目录生成一对 Markdown/Canvas 和必要 sidecar，以及单独的检查结果。既有 V-JEPA 2 内容、正式知识库、批注及旧 v4 文件均不改动。
- 自动检查批准后才执行；需安装后评鉴的 Canvas，另按正常 hotfix 版本发布/安装，再在独立 `test` Vault 新目录展示。发布、安装及真实 Vault 写入不由本方案自动批准。
- 展示产物必须包括：输入版本与摘要、结构对照表、可编辑 Canvas、完整 Markdown、每项失败的具体位置、几何与节点统计、未核验事项。不能只给“通过”或截图。
- **必须人工评鉴**：在 Obsidian 中观察五分支整体布局、英文标签、直角无箭头连线、每个命名子槽位能否独立编辑、文字及链接是否被裁切、是否约有一行点击留白，以及是否避免单轴过长。会话中须明确说明这一要求。

## 一、独立合成输入

### 1. 输入身份与范围

```yaml
fixture_id: synthetic-scalar-reader-v5-01
paper_title: Synthetic Scalar Reader
resource_id: paper:synthetic-scalar-reader
schema_version: 5
framework: reference_tree_v5
language: en
scope: whole
markdown_quotes: true
note_stem: Synthetic Scalar Reader Analysis
reader_projection: zotero_native
source_verification: synthetic_only
```

这是**语义输入清单**，不是承诺某个尚未实现的机器字段名。转录为实际 v5 fixture 时须逐项对照，不改变下面独立预期；转录后的完整输入、schema 版本和 hash 应先展示给用户，再执行。不能把字段换名解释为删去必需内容。

合成 PDF locator 固定为 `library_type=user`、`library_id=99999999`、`attachment_key=SYNTH001`、`content_hash=`64 个 `0`；这些都是占位身份，不声称附件存在。默认来源 URI 预期为 `zotero://open-pdf/library/items/SYNTH001?page=N`。不向真实 provider 请求它，也不以此证明真实来源归属。

### 2. 合成原文：唯一引用核对依据

下列短段落即合成来源全集；页号是物理页而非印刷页码。所有逐字摘录都应与这里逐字符核对，不能由生成器编造。普通句子用于分析正文，带 `Q_` 的句子专门用作逐字摘录探针，故其全文**不得出现在 Canvas**。

| 物理页 | 完整合成来源段落 |
|---|---|
| 1 | `Estimate a scalar from three measurements. Q_TASK: "Three inputs, one scalar."` |
| 2 | `The first module subtracts the arithmetic mean. Q_METHOD: "Subtract the mean <before> aggregation & preserve signs."` |
| 3 | `Without centering, the synthetic error is 9; with centering, it is 4. Q_ABLATION: "Error changes from 9 to 4 in this toy comparison."` |
| 4 | `Only three synthetic measurements are considered. Q_LIMIT: "Evidence is limited to the three-input toy setting."` |

引用均来自本材料自己的合成短文，不涉及真实论文著作权、Scientific source fidelity 或 ZotFlow 路由。Page 2 的 `<`、`>`、`&`、引号测试显示字面值；Markdown 内不得被误解释为 HTML，Canvas 也不得出现该引用。

### 3. 槽位输入：38 个独立事实/availability 记录

稳定 ID 用于逐项对应预期，不是当前生成器的节点 ID。`S` 为合成作者事实，`I` 为明确标注的合成分析推断；`A` 为 `not_applicable`，必须带理由。除下表明确提供的内容外，不能新增科学结论、例子、数字或“论文未报告”断言。

| ID | 所属命名槽位（层级完整） | 输入类型与完整可读内容 |
|---|---|---|
| A-T | Abstract / Task | S：`Estimate a scalar from three measurements.` 来源物理页 1，逐字摘录 `Q_TASK: "Three inputs, one scalar."`。 |
| A-C | Abstract / Technical challenge for previous methods | A：`No prior-method comparison is defined in this synthetic source.` |
| A-I-1 | Abstract / Key insight / motivation / One-sentence insight / motivation | A：`This synthetic source supplies no abstract-level insight.` |
| A-I-2 | Abstract / Key insight / motivation / Benefit of the insight / motivation | A：`No abstract-level benefit is specified in this synthetic source.` |
| A-K1-1 | Abstract / Technical contributions / Technical contribution 1 / One-sentence technical contribution | A：`No abstract-level summary for contribution 1 is supplied.` |
| A-K1-2 | Abstract / Technical contributions / Technical contribution 1 / Benefit of the technical contribution | A：`No abstract-level benefit for contribution 1 is supplied.` |
| A-K2-1 | Abstract / Technical contributions / Technical contribution 2 / One-sentence technical contribution | A：`No abstract-level summary for contribution 2 is supplied.` |
| A-K2-2 | Abstract / Technical contributions / Technical contribution 2 / Benefit of the technical contribution | A：`No abstract-level benefit for contribution 2 is supplied.` |
| A-E | Abstract / Experiment | A：`This synthetic source supplies no abstract-level experimental account.` |
| I-T | Introduction / Task and application | A：`No application scenario is supplied in this synthetic source.` |
| I-C1-1 | Introduction / Technical challenge for previous methods / Technical challenge 1 / Previous method | A：`No earlier method is supplied for challenge 1.` |
| I-C1-2 | Introduction / Technical challenge for previous methods / Technical challenge 1 / Failure cases (Limitation) | A：`No failure case is supplied for challenge 1.` |
| I-C1-3 | Introduction / Technical challenge for previous methods / Technical challenge 1 / Technical reason | A：`No technical cause is supplied for challenge 1.` |
| I-C2-1 | Introduction / Technical challenge for previous methods / Technical challenge 2 / Previous method | A：`No earlier method is supplied for challenge 2.` |
| I-C2-2 | Introduction / Technical challenge for previous methods / Technical challenge 2 / Failure cases (Limitation) | A：`No failure case is supplied for challenge 2.` |
| I-C2-3 | Introduction / Technical challenge for previous methods / Technical challenge 2 / Technical reason | A：`No technical cause is supplied for challenge 2.` |
| I-P | Introduction / Our pipeline / One-sentence key innovation / insight / contribution | A：`No introduction-level innovation statement is supplied.` |
| I-K1-1 | Introduction / Our pipeline / Contribution 1 / Problem addressed | A：`No introduction-level problem statement is supplied for contribution 1.` |
| I-K1-2 | Introduction / Our pipeline / Contribution 1 / How it is done | A：`No introduction-level implementation is supplied for contribution 1.` |
| I-K1-3 | Introduction / Our pipeline / Contribution 1 / Advantage / insight | A：`No introduction-level advantage is supplied for contribution 1.` |
| I-K2-1 | Introduction / Our pipeline / Contribution 2 / Problem addressed | A：`No introduction-level problem statement is supplied for contribution 2.` |
| I-K2-2 | Introduction / Our pipeline / Contribution 2 / How it is done | A：`No introduction-level implementation is supplied for contribution 2.` |
| I-K2-3 | Introduction / Our pipeline / Contribution 2 / Advantage / insight | A：`No introduction-level advantage is supplied for contribution 2.` |
| I-D | Introduction / Demos / applications | A：`No demo is defined in this synthetic source.` |
| M-O1 | Method / Overview / Task / input / output | A：`This fixture tests the task/input/output slot without adding a method summary.` |
| M-O2 | Method / Overview / Method / steps | A：`No complete ordered procedure is supplied; no steps may be invented.` |
| M-1-1 | Method / Pipeline module 1 / Motivation | A：`No motivation statement is supplied for module 1.` |
| M-1-2 | Method / Pipeline module 1 / Method | S：`The first module subtracts the arithmetic mean.` 来源物理页 2，逐字摘录 `Q_METHOD: "Subtract the mean <before> aggregation & preserve signs."`。 |
| M-1-3 | Method / Pipeline module 1 / Why it works | A：`No causal explanation is supplied for module 1.` |
| M-1-4 | Method / Pipeline module 1 / Technical advantage | A：`No technical advantage is supplied for module 1.` |
| M-2-1 | Method / Pipeline module 2 / Motivation | A：`No motivation statement is supplied for module 2.` |
| M-2-2 | Method / Pipeline module 2 / Method | A：`No implementation statement is supplied for module 2.` |
| M-2-3 | Method / Pipeline module 2 / Why it works | A：`No causal explanation is supplied for module 2.` |
| M-2-4 | Method / Pipeline module 2 / Technical advantage | A：`No technical advantage is supplied for module 2.` |
| E-C | Experiments / Comparison experiments | A：`No independent baseline comparison is defined in this synthetic source.` |
| E-A1 | Experiments / Ablation studies / Effects of core contributions / important components | S：`The toy error is 9 without centering and 4 with centering.` 来源物理页 3，逐字摘录 `Q_ABLATION: "Error changes from 9 to 4 in this toy comparison."`。 |
| E-A2 | Experiments / Ablation studies / Effects of design choices in each pipeline module | I：`The toy comparison supports a centering effect only within this synthetic setup.` 推断依据为物理页 3，逐字摘录同 E-A1；不得改称因果证明、显著性或真实 benchmark。 |
| L-R | Limitation | S：`Only three synthetic measurements are considered, so the described evidence is limited to this toy setting.` 来源物理页 4，逐字摘录 `Q_LIMIT: "Evidence is limited to the three-input toy setting."`。不得另编失败案例或数据规模。 |

独立计数：Abstract 9、Introduction 15、Method 10、Experiments 3、Limitation 1，共 **38 个可归属记录**。其中 4 个作者事实、1 个推断、33 个带理由的 availability；因两个记录共享一个支持摘录，Markdown 有 5 个相邻引用块、4 种逐字引用文本。每个记录在 Canvas 中都须有独立可编辑的事实/availability 节点；命名结构标签可以额外占节点，不能拿“文本段落数”代替节点数。

两组贡献、两组挑战和两个模块只测试“重复实例”能力，**不是要求每篇真实论文有两个实例**。Availability 用于结构探针，不证明真实论文报告与否。

## 二、手写正向预期与通过条件

### 1. Framework 与 Markdown

| 检查项 | 手写预期 |
|---|---|
| 一级分支 | 严格为 `Abstract → Introduction → Method → Experiments → Limitation`。Abstract 的 `Experiment` 与一级 `Experiments` 是两个不同位置。 |
| 命名子槽位 | 上表 38 条都在完整所属路径中可见；父级与同级关系符合模板。不得改成 Task/Input/Workflow/Output/Boundary。 |
| Markdown 解释 | 38 条输入文字及理由都保留、独立可读；不得用 Canvas 代替正文。机器信息只占薄元数据，不出现 `sw-analysis-claim` 注释或独立 Evidence 章节。 |
| 原文摘录 | 5 个相邻引用块逐字匹配合成段落，标题和说明为英文；每块与所属记录共用对应来源。特殊字符显示字面值。 |
| Scope | 明确为完整合成 whole-paper fixture，同时明确其来源仅合成；不能宣称真实论文验收成功。 |
| 块定位 | 每个事实/availability 记录都有独立 Markdown block ID；不同模块的同名 `Method`/`Motivation` 不能共用锚点。 |

### 2. Canvas 节点、连线与逐点导航

| 检查项 | 手写预期 |
|---|---|
| 可编辑性 | 原生 JSON Canvas text 节点；38 条记录逐条可编辑。不接受 SVG、图片、五块 dashboard、展开后全在一个 text 节点或每个 claim 的单一 `/details` 卡。 |
| 重复实例 | `Technical challenge 1/2`、两组 `Technical contribution 1/2`、`Contribution 1/2` 和 `Pipeline module 1/2` 分别拥有自己的子槽位和父节点；相同子槽位名称不跨实例合并。 |
| 连线 | 每个命名子槽位只有其正确父级的树边；直线、直角路由，无箭头。不能省略 required edge、串接 sibling 或指到同名其他模块。 |
| Inline evidence | 4 个作者事实节点分别标注作者事实，E-A2 标注推断；33 个 availability 节点保留状态/理由或准确正文反链，不改称作者事实。无 Evidence 独立节点/分区。 |
| 原文入口 | A-T→物理页 1，M-1-2→2，E-A1/E-A2→3，L-R→4。物理页在 URI 中为 `page=1/2/3/4`；不用页标签替代。Availability 节点不产生伪造原文入口。 |
| 精确正文反链 | 38 个记录节点各自反链到本条 Markdown block，不只是章节，也不能让 E-A2 指到 E-A1；同名模块子节点仍各自对应自己的 block。 |
| 无 Canvas 摘录 | Canvas 所有节点与连线文本均不包含 `Q_TASK`、`Q_METHOD`、`Q_ABLATION`、`Q_LIMIT` 或完整逐字摘录；不创建 quote 节点。 |
| 语言 | 一级/命名子槽位、证据状态、来源链接标签和正文反链别名全部英文。合成原文仍为英文；不从文件后缀或用户界面语言猜语言。 |
| Pipeline 边界 | Method 模块只有 Motivation / Method / Why it works / Technical advantage，不增加 corresponding challenge/contribution 轴。 |

### 3. 几何、节点预算与人工评鉴

- 对**所有实际 renderer-owned 节点**统计数量及包围盒，单独列出事实节点、结构标签节点和总节点；不得沿用 v4 的“每 claim 一个 grouped detail”计数法。
- 用户补充硬要求：同深度节点左边缘对齐；直角树边不得交叉或穿越其他节点。同父节点的共享主干允许，不算交叉。分别检查生成图及错位/交叉变体，不以没有矩形重叠代替这些检查。
- 保留契约的紧凑约束：renderer-owned 节点无重叠，单节点高度不超过 420 px，整图 `max(width/height, height/width) ≤ 2`。若最终 v5 对此另作正式批准的版本化修改，重新展示该修改及独立输入，不静默放宽。
- 文本框应根据可见正文、证据、来源入口和反链尺寸留约一行点击空白；不靠固定巨大文本框、缩小字或隐藏链接骗过几何检查。机器测量只能作为线索，Obsidian 实际显示仍待人工评鉴。
- 正向 38 条事实记录符合旧 `40` 事实/细节节点上限的量级，但**不预先认定**总节点满足旧 `96` 上限；自动检查必须统计真实展开节点。预算冲突时输出明确失败，禁止合并命名子槽位、丢记录、把必备节点转成隐藏文本或悄悄改预算。
- 人工步骤：先总览辨认五分支，再任选同一模块的两个子槽位分别进入编辑，检查文字与对应链接点击区，再观察不同模块同名子槽位和独立 Experiments。能编辑不代表自动双向同步；不把人工文字改动直接写回其他产物。
- 合成来源 URL **不实际点击外部应用**。该检查只证明投影文字和页号一致，真实 reader 成功由后续独立、已安装单对象方案验证。

## 三、独立负向输入与预期拒绝

所有负向案例均从完整合成输入/产物复制出来，仅进行下表的一项变更。输出逐项错误位置及原因；不得边修边报告首次通过。是否进行一次自动修复另依正式流程约定，不在此偷换原始验收。

| ID | 单项变更 | 手写预期 |
|---|---|---|
| N-01 | whole 输入删去整个 `Experiments`，保留 Abstract / Experiment。 | 拒绝完整 whole-paper conformance；不能把 Abstract 的 Experiment 当独立 Experiments。 |
| N-02 | M-1-3 的槽位从 `Why it works` 改为 `Failure cases (Limitation)`。 | 拒绝该路径/point 槽位，不把它自动改放 Introduction，也不保留为未知自定义必备槽位。 |
| N-03 | 把 M-1-1～M-1-4 四个独立可编辑节点删除并把四段文字放进一个 `/details` 节点，保持字数完全不变。 | 拒绝展开子槽位与独立节点约束；文字俱全不代表结构通过。 |
| N-04 | 将 M-2-2 的父边终点指向模块 1 中同名 Method 节点。 | 拒绝边的归属/endpoint 拓扑；不能仅检查 endpoint 存在。 |
| N-05 | 只把 E-A2 正文反链换为 E-A1 的 block。 | 拒绝逐点反链错位，即使来源页相同。 |
| N-06 | 只把 M-1-2 source URI 改为 `page=3`，IR 仍记录物理页 2。 | 拒绝 source-span 与投影不一致；不声称“页号可打开所以通过”。 |
| N-07 | 把完整 `Q_METHOD` 原文摘录加进 Canvas 节点，Markdown 保持正确。 | 拒绝 Markdown-only quote 边界；不能删 Markdown 摘录后当成功。 |
| N-08 | 将 E-A2 的证据状态由推断改为作者事实，内容与合成输入保持不变。 | 拒绝证据 attribution 与输入不一致；不以文字一样为由忽略状态。 |
| N-09 | 英文输入输出中只把 Experiments label 改成“实验”。 | 拒绝框架 label 的语言不一致；语义翻译不能替代显式语言契约。 |
| N-10 | 一节点移动到其他生成节点上方形成矩形重叠。 | 拒绝重叠；不能靠文字短、来源链接存在忽略几何。 |
| N-11 | 全图沿 y 轴拉伸到包围盒纵横比 3:1，内容、链接、节点数不变。 | 拒绝单轴过长；不得自动缩字、合并必备子节点或放宽 2:1。 |
| N-12 | 将某 text node 高度改成 421 px，其余不变。 | 拒绝单节点高度约束。 |
| N-13 | 保留 38 记录但给 M-1-2 添加 renderer-owned corresponding-challenge 子轴。 | 拒绝模板外 pipeline 挑战轴；该文本不能以“更完善”名义进入正式输出。该案例不是要求删除用户另建的非 owner 图项。 |
| N-14 | 将所有命名子槽位文本合并到五个 branch text 卡片，保留一级五分支。 | 拒绝 dashboard/flattened substitute；五个分支存在不是充分条件。 |
| N-15 | 在文本节点中注入 `<!-- sw-analysis-claim ... -->` 或 Canvas 中添加 private top-level identity 字段。 | 拒绝可见正文机器标记或非允许顶层身份，按 sidecar/标准 graph identity 边界处理。 |
| N-16 | 删除 A-I-2 的事实/availability 记录，保留其固定框架槽位为 unfilled，不输入空作者事实或无理由的 availability。 | **允许空槽位，不造结论**；不能把无文本本身当作论文未报告证据。其余 37 条不消失，空 label 不需要伪造来源或摘录。 |
| N-17 | 把一个 marker-containing 原文引用换为同义改写，原合成 source 不变。 | 拒绝逐字 quote 不一致；不把 paraphrase 当 original excerpt。 |
| N-18 | 渲染节点量超出版本化预算的长输入，仍含全体命名槽位。 | 明确报告 budget/geometry 冲突且不提交 canonical success；不隐藏超量节点、不删槽位。预算边界值和确切长输入先另行展示再批准。 |

## 四、v4 兼容与更新安全：旧对象必须保持原样

旧格式回归只用合成 v4 文件，**不读取或改写真实 V-JEPA 2**。

| 对象/操作 | 独立预期 |
|---|---|
| 合成 v4 四分支、grouped-details、`markdown_quotes=false` 读取和校验 | 沿既有 v4 版本接口可读；不得把它报为 v5 合格，也不自动补 Experiments/逐字摘录。 |
| 不请求转换的普通 v4 focused update | 留在 v4，未选章节、原语言及 quote setting 不变；不利用更新顺手变成五分支。 |
| v4 文档仅载入/审阅 | Markdown、Canvas、sidecar 的逐文件 hash 读取前后完全一致。 |
| 未明确批准的 v4→v5 转换 | 零写入、明确报告需要格式转换审议；不能因新默认版本 silently refresh。 |
| v5 focused 更新只选 Method | 只替换完整 Method 范围；未选 Abstract / Introduction / Experiments / Limitation 内容保持。当前字节和 paired CAS 必须绑定；不将“单点更新”当删掉同级子槽位的许可。 |
| 人工 Canvas 文本编辑后再 managed update | 产生 paired conflict / proposal，不覆盖人工改动，也不自动双向同步正文。 |
| 安全 geometry/color 与自定义节点/边 | 普通更新保留安全人工布局和非 owner 图项；这些图项不参与生成节点预算。 |
| 打开 Advanced Canvas 后产生允许 metadata | 只接受并保留受限 `version`/`frontmatter` envelope；不把其内容当对象身份，不放行任意顶层字段。 |

这些更新用例的确切 base fixture、hash 与拟操作 payload 必须在执行前作为独立附件/输入展示，不能沿用开发者当前内存中的对象。

## 五、拟执行步骤与状态报告

批准前仅准备；本文件不包含任何已执行结果。

1. 转录合成输入并发布输入快照/hash，同时附 schema 字段与本表 ID 的对应关系；如果内容或范围发生变化，重新确认。
2. 执行已批准的单对象 render/validate 和指定负向检查，在独立目录记录输入、产物、逐项预期/实际和失败原因。
3. 单独验证 source-span 到页号/正文 block 的投影与 quote 字面值。不请求真实外部来源，不将 mock provider 通过计为真实来源验证。
4. 执行已批准的合成 v4 兼容/paired 更新回归，逐文件核对读取前后的 hash；不得用旧格式通过支持新格式成功。
5. 自动结果分别报告 `passed / failed / not-run / not-implemented`，科学来源和产品安装态 reader 明确 `not-verified`；不得把有生成文件视为 conformance 成功。
6. 正常安装确定 hotfix 构建后，按另行批准的单对象 `test` Vault 展示方案人工评鉴，保留旧样张并新建目录。会话明确写出对象、打开方式、观察点和待确认事项；未获明确认可仍标为“待人工评鉴”。

### 用户批准前的审阅问题

- 是否批准上述合成对象、38 条命名槽位和 N-01～N-17 范围的开发阶段自动检查，以及合成 v4 兼容/更新回归？
- N-18 的长输入与预算边界值尚未准备，不包含在本次可执行范围中；准备后单独审阅。
- 正常 hotfix 发布/安装及 `test` Vault 人工展示仍需明确批准对应版本、位置和写入范围。本材料不等于授权正式 Vault、整库业务操作或 main 合并。

结论边界：这一方案只能证明新模板的结构、投影、可编辑性、安全兼容及有限几何条件。要达到“知识可靠”，真实论文来源核验、科学内容评鉴和真实阅读器动作还需要独立证据；不得把合成内容的结构通过冒充这些事项通过。
