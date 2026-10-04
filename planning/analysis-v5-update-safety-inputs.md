# 论文分析 v5：更新安全与预算边界独立输入

状态：**仅已准备；尚未获本轮执行批准，未运行测试**。

这是对 `analysis-v5-independent-acceptance.md` 中尚未执行的更新矩阵及 N-18 的补充输入。
预期来自完整输出模板、版本接口与 paired-update 保护约定；没有导入生产代码、运行生成器、
借用生产 factory 或观察运行结果来调整预期。JSON 的转录和 SHA-256 读取不属于测试执行。
本文件不替代已有 164 项结果，也不把旧范围的“测试批准”扩展到这些新输入。

## 对象与边界

- 唯一 v5 base 是 `tests/fixtures/analysis_v5_toy.json` 的固定字节：虚构 **Synthetic Scalar Reader**，
  38 条记录、五个分支、四个合成来源段落。其 PDF ID 是占位，不进行任何外部请求。
- 唯一 v4 base 是下面的新独立 JSON，五条 availability claim，其中一个 Method module 有四条
  availability point；没有真实论文、PDF 身份或作者事实。它明确使用四分支、grouped-details、
  `markdown_quotes: false`，不导入已有测试 factory。
- 所有后续生成文件只可放入隔离合成测试目录。不得访问真实 Vault、Zotero、GUI、网络或安装环境；
  不发布、不安装、不迁移、不打开占位 URL。读写范围、异常和文件 hash 由测试报告单独展示。
- **这批自动测试不需要人工审美评鉴，也不能替代审美评鉴**。它仅证明合成更新保护和预算拒绝。
  产品 Canvas 的人工评鉴必须在正常安装后，另行明确对象、打开方法和观察标准。

输入目录：`tests/fixtures/analysis-v5-safety-inputs/`。机器总表为 `manifest.json`；
总表和 mutation 清单明确 `prepared_not_approved`；直接 IR payload 保持原 schema，不注入额外
状态字段。总表统一声明 `execution_status: not_run`，没有伪造的通过状态。

## 固定输入与摘要

| 文件 | SHA-256 |
|---|---|
| `tests/fixtures/analysis_v5_toy.json` | `89640ecef880ec49bdf4210f440b7938952b0529267f09aae55a02faafa2a5d4` |
| `focused-method.json` | `c1ff6fc4bd090bb1795cd185adb47653bb78e86cd4bc25c1eea42b1bdbc98c5b` |
| `v4-base.json` | `4958a443190f8d20b3c6847b2ce710ef7dfcfb2dca0725a195043e1bc3c3db6d` |
| `budget-40-modules.json` | `a7de42e65adc8037a28f3ab16ec7215c96ddfecc7501bb151693d91e855bc573` |
| `repair-mutations.json` | `c80be0822fc5f9c450d42a1f0352a6838a79096735179f45a6d3982077c36863` |
| `canvas-mutations.json` | `309d0d2960fce11df9230f3290aad5e50e4fac44a1ab6c9312e4a34dc49dd7e9` |
| `focused-limitation.json` | `1551b7b837bb6713cfaa703187da23d8d85f0e4c51d23aa6ad0ac37999c9dbdb` |
| `geometry-mutations.json` | `1fa29ce6f02dca72099a091867b1151449e8bc473ae2c088c1e628b2862287e7` |
| `human-edge-mutations.json` | `2f6346f5b3d0bd8b82f5df4ed6a3983305b3155121c3855446f01a1292fb0913` |
| `point-prose-mutations.json` | `53d6378874a0e447aebb61277ec9d7ce089c8a1b895f3c394c29ebf68fd7ef52` |
| `manifest.json` | `8ebdbb0a15ea92bf79ad7e8f5e7e0ce360dd26a288779b8b0fac2b97e31af4b6` |
| 只读参考：`planning/acceptance/analysis-v5-synthetic/Synthetic Scalar Reader Analysis.canvas` | `6dab532f4b5bbf261716ede769eb1e135eac92ea5c8fe50531ba9fe98ff12b9d` |

摘要不允许被执行时的新 base 替换；当前字节与本表不符就停止，重新展示。机器清单不复制自己的
hash，以避免自引用摘要。确定性节点 ID 可由运行期正常接口解析，但记录身份、文本及预期不得
从运行结果反向猜测。Canvas 记录 selector 必须唯一命中规定 claim/point 的精确 block backlink；
零匹配或多匹配是输入/测试失败，禁止任取第一个。

## 精确更新与独立预期

所有案例独立从干净的 base 副本开始；一个负向变体不进入下一案例。后续 approved harness
使用正常的 render、baseline、propose/repair 接口，不绕过 baseline 或直接改受管真实文件。
预期拒绝允许调用层用不同异常形式表达，但必须说明具体原因，不靠偶然 JSON 不可解析取得绿灯。
普通 `plan_analysis_update` 的成功只表示 `ready`：返回可审阅的内存 proposal，不是 `updated`、
canonical commit 或磁盘写入。U-01/U-06 的守恒断言检查该 proposal；当前三文件仍须零写入。

| ID | 输入与唯一变化 | 手写预期 |
|---|---|---|
| U-01 | `focused-method.json` 完整包含 `m-o`、`m-1`、`m-2` 三条 Method claim。只把 `m-2/motivation` 的 text 和同条 N/A detail 从 `No motivation statement is supplied for module 2.` 改为 `Module 2 has no supplied motivation.`；scope 为 focused、roles 仅 Method。 | 普通 focused update 可提出合法的新整体五分支 pair；完整保留 Method 的十条记录和原来源。四个未选分支的 claim/point 内容、evidence、source spans、稳定 block/node/edge 身份、标签与链接均保持；对应 Markdown 分支字节不变。profile 不能变为只有 Method 的 whole。只改这一条理由，不造新科学事实。 |
| U-02 | `repair-mutations.json` 中 U-02 是精确 RFC 6902 patch：确认 `/claims/14` 为 `m-1` 且 container 为 true，再改 container=false，填入非空 body 与 N/A 理由；point 不变。 | targeted repair 拒绝 container 身份变更，即使独立 IR 本身可结构合法；不把原结构父节点变成第 39 条事实来“修复”布局。base 不变，不产生 repaired success。 |
| U-03 | 同文件 U-03：交换 `m-1` 的完整 motivation 与 why-it-works point 对象（索引 0/2），所有 ID、文字、证据成套保留。 | targeted repair 拒绝 point 身份序列变化；不能因最终 ID 集合相同就放行。此变体不靠未知 ID 或重复 ID 意外失败。 |
| U-04 | 同文件 U-04：只交换 `m-1` 前两个 point 的 `point_id`，其 text/evidence 留在原位置；ID 集合仍是四个合法、唯一的槽位 ID。 | targeted repair 拒绝已记录 point 身份重映射；不能把 Method 的作者事实重新绑定到 Motivation，或把 availability 绑定到 Method。不是重命名修复授权。 |
| U-05 | `canvas-mutations.json` 的 U-05：唯一命中 `m-1/method`（`point-3-m-1-method`），仅将其 Canvas text 改为 `Human-edited synthetic method note; do not overwrite.`，再提交 U-01 incoming。 | 返回 paired conflict/proposal。当前 Markdown、Canvas、sidecar 逐文件 hash 保持；人工文字不被自动覆盖，Canvas 也不自动同步回 Markdown。允许另存非 canonical proposal，但不得将它当成功提交。 |
| U-06 | 同文件 U-06：每个受管节点 x+120/y+80；`m-1/motivation` 的 color=3；在平移后受管 bbox.max_x+200 的位置新增两个 280×100 text node，y 为 bbox.min_y 与 min_y+200，ID 为 `user-review-note-a/b`；新增连接这两者的 `user-review-edge`。再提交 U-01 incoming。 | 所有存续受管 ID 保留精确平移后的 x/y；指定 color 及两个自定义节点/边的 JSON 值不变。自定义图项不进入受管预算。平移不会改变同层对齐、无交叉和无穿框结果。新的短 N/A 文字不构成放宽几何门禁的理由；若当前实现不能保留它，应报告失败，不改输入或删人工布局。 |
| U-07 | `v4-base.json` 产生独立旧 baseline/pair，incoming 使用固定 v5 base（两者 artifact/title/language 相同）。 | 普通 v4→v5 update 明确拒绝版本/framework 转换；旧四分支、grouped-details、quotes=false 和当前三文件 hash 原样，零 canonical 写入。身份相同不授权隐式迁移。 |
| U-08 | 固定 v5 base 产生独立新 baseline/pair，incoming 使用 `v4-base.json`。 | 普通 v5→v4 update 也明确拒绝，不因“兼容旧版”丢 Experiments、展开子槽位或 quotes=true。当前三文件 hash 原样，零 canonical 写入。 |

U-02～U-04 的 test op 先固定旧 claim/point 身份；索引只对已固定摘要的 base 有效。
U-06 是安全手工布局/样式保护，不要求保留不安全错位。若源布局本身未通过对齐/无交叉 gate，
不得绕过 gate 执行此正向例，也不能把原输入换成更容易通过的简化图。

## 追加四个精确几何输入

`geometry-mutations.json` 只读引用上述持久合成 Canvas，不运行生成器或由生产算法预测失败原因。
该文件已有 58 个节点、57 条边，bbox 为 `(0,0)` 至 `(3056,4538)`；其 base 文本、原边与来源
在前三个变体中保持。这里固定现有可审阅输入，不能临时重渲染后套用旧坐标。

持久 `planning/acceptance/` 产物会被 Git 忽略，只是当前审阅入口，不是测试的唯一输入；干净
checkout 的 harness 不得依赖它存在。G-01～G-03 批准后须在隔离目录从已固定 IR 经正常
renderer 重建 base，使用 `json.dumps(canvas, ensure_ascii=False, indent=2) + "\n"`、UTF-8、
原对象/列表顺序取得规范字节，并先比对已展示的 `6dab532f…12b9d` 全字节摘要。
再确认 58 节点/57 边、bbox、G-03 的全部 node_id/old_y 与 G-02 参考矩形完全一致，才施加变体。
任何差异都立即停止并报告 base mismatch：不得临时套新坐标、更新 hash 或自改预期。合法实现
变化若确需新 base，先准备新的可审阅输入、摘要与变体并重新批准。这是未来执行步骤，本次未执行。

| ID | 完整变更 | 手写预期 |
|---|---|---|
| G-01 | 新增唯一 edge `synthetic-cross-branch-edge`，从 Abstract 的 Task 节点 `1db98ef0f1d8b14b` 到 Method 的 module 1 / Method 节点 `491aa5820d139a26`；right→left、两端 none、square。保留原 57 条边。 | `canvas-unexpected-edge` 明确拒绝额外跨分支受管语义连接。endpoint 存在、原必需边仍齐全都不能掩盖多出的关系。不能把这条 managed→managed 语义边冒充与受管事实无关的 custom graph。 |
| G-02 | 新增 text node `synthetic-covering-text`，矩形 `x=1568,y=3201,width=456,height=108`，文字 `Synthetic covering box.`；正好覆盖节点 `491aa5820d139a26`。既有节点不移动。 | `overlapping-canvas-nodes` 明确拒绝。新节点不是 owner 也不能遮盖现有 Method 内容；原图无 owner-owner overlap 不是充分条件。矩形和预期覆盖对象固定，不改成别的更容易触发的输入。 |
| G-03 | N-11 的整数安全版本：所有节点只改 y，`new_y=floor(old_y×9039/4409+0.5)`；58 条旧/new y 在 JSON 完整列出，x/尺寸/文字/边不变。Limitation 标签旧 y=4440,height=66，新 y=9103；内容节点新 y=9039,height=129。 | 新 bbox 为 `3056×9169`：标签底部 `9103+66=9169` 比内容底部 `9039+129=9168` 多1 px。长宽比 `9169/3056` 略大于3；2:1 门禁不变，仍须由 `canvas-aspect-limit` 明确拒绝。所有坐标保持整数，其余事实、来源、链接及节点数完全不变。 |
| G-04 | `focused-limitation.json` 仅保留固定 base 的 `l-r` 完整对象，profile 为 focused、roles=[limitation]、quotes=true；该条 body/evidence/source/hash/page/quote 一字不变。 | 合法 focused Limitation 产物应通过，实际 bbox 比值≤2。不能为小范围结果制造超宽 strip，不能增补作者事实或改动引文来凑布局；也不能冒称完整五分支论文结果。 |

前三项必须报告表中的具体 finding，而不仅是任意 `ok=false`。其他同时产生的 finding 可以保留。
G-04 的正向预期独立来自 scope/几何契约；没有使用当前 renderer 的结果定义“应当通过”。

## 追加人工边和浮动端点精确输入（未运行）

`human-edge-mutations.json` 复用同一固定 base、摘要和隔离重建 preflight；不再分析论文，
三个案例各从原始副本开始。机器总表已追加这三项，其他既有 fixture 字节不变。

| ID | 完整变更 | 手写预期 |
|---|---|---|
| G-05 | 新增 text 框 `human-left-probe=(-480,3205,280,100)`、`human-right-probe=(3256,3205,280,100)`，文字分别为 `Synthetic left endpoint.` / `Synthetic right endpoint.`。新增 `human-through-method`，right→left、两端 none、square；水平轨迹 y=3255，从 x=-200 到3256。原58节点/57边不变。 | 两个框均不遮盖受管节点，但边穿过 `491aa5820d139a26` 的正文矩形 `(1568,3201,456,108)`。指定边路径的 `canvas-edge-through-node` 必须指出该节点；不允许凭人工 endpoint 身份跳过。 |
| G-06 | 新增 `human-top-probe=(222,-300,100,100)` / `human-bottom-probe=(222,4700,100,100)`，文字分别为 `Synthetic top.` / `Synthetic bottom.`；新增 `human-crosses-trunk`，bottom→top、两端 none、square。轨迹 x=272，y=-200至4700。 | 指名该边的 `canvas-crossing-edges`。竖线位于根框右边缘240与第一分支左边缘304之间，只与主干相交，不穿受管框；要求没有 `overlapping-canvas-nodes` / `canvas-edge-through-node`，避免其他失败替代交叉证明。 |
| G-07 | 节点不变，唯一修改 root→Abstract 的既有边 `403ef13b9c6dd3c2`，新增 `fromFloating: true`；其他边与固定 sides、square、none 值保持。 | 指定边的 `canvas-edge-routing-unverifiable`。Advanced Canvas 可在加载/移动时换端点侧，因此记录的 median-X 路线不能当作可靠实际路径。保留原文件，不清除人工 flag 来凑通过。 |

这三例验证时均保持原事实、源链接、正文和三文件字节，允许报告其他真实 finding。
新增 input 与预期由静态坐标和插件行为确定，未调用生产渲染器或测试。

## 要点正文与摘要格式输入（未运行）

`point-prose-mutations.json` 按固定 claim_id/point_id 唯一定位，只替换一个字段，其余记录和
证据不改。v5 使用 `m-1/motivation`，v4 使用 `v4-m/motivation`；P-06 的 v3 完整对象
直接列在该 JSON 的 `inline_legacy_v3`，不是借生产 factory 制造的 base。

| ID | 版本、字段和精确值 | 独立预期 |
|---|---|---|
| P-01 | v5 text=`# Extra section` | model/schema 同时拒绝，字段为 text；它是模板外 ATX 标题。 |
| P-02 | v5 text=`<!-- sw-analysis-claim id="synthetic-point" -->` | model/schema 同时拒绝机器 claim 标记。 |
| P-03 | v5 text=`   ## Extra section`（恰三空格） | 同样拒绝，不能漏掉合法 ATX 的前导空格形式。 |
| P-04 | v5 text=`#tag describes an unavailable synthetic choice.` | 保持字面文本、五个一级分支；# 后没有分隔空格，不是标题。 |
| P-05 | v4 text=`# Extra section` | 保持原四分支兼容；实际行以已有列表标签开始，不增加标题，不人为给 v4 加更严新版限制。 |
| P-06 | v3 text=`# Legacy point text` | model/schema 保留 legacy 输入兼容；不渲染、不冒称旧格式满足新模板。 |
| P-07 | v5 text=`###` | 拒绝空 ATX 标题形式；渲染追加证据也不能把它变成新章节。 |
| P-08 | v5 canvas_summary=`# Extra summary heading` | 拒绝额外 Canvas 标题；不能只检查完整 text 而漏过实际呈现的摘要。 |
| P-09 | v4 text=`<!-- sw-analysis-claim id="synthetic-point" -->` | model/schema 提前拒绝既有格式禁止的机器标记，不是 v4 ATX 兼容收紧。 |
| P-10 | v5 canvas_summary=`<!-- sw-analysis-claim id="synthetic-summary" -->` | model/schema 同时拒绝实际可见摘要中的机器标记。 |

拒绝例不得因未知 field、source gap、长度限制或非法 point ID 偶然失败；schema 的 not finding
必须落在被修改的确切字段，model 错误须说明 framework heading/marker。正向逐项核对其他
claims/points/evidence 原样；既有 whole IR 的 branch 数和标题由各自版本规范判定，不从生产
输出反向制定预期。这些只证明输入和呈现边界，不代替科学来源或真实 Obsidian 人工评鉴。

## N-18：实际展开节点超过预算

`budget-40-modules.json` 是完整独立输入，不是占位“待补长文”：

- 版本 5、whole、五个 roles、英文、`markdown_quotes: true`、Zotero-native 合成投影。
- 恰好 **40 条非 container 的 Method availability claim**，稳定 ID 为 `budget-01` 至 `budget-40`，
  outline 为 `method/modules/budget-01` 至 `method/modules/budget-40`。每条正文和 N/A detail
  均在 JSON 中完整列出，不含 source span 或虚构作者事实。
- 每条不提供 point。按完整模板仍须保留 **Motivation / Method / Why it works / Technical advantage**
  四个独立空标签；空槽位不是四条 availability，不可编造 point 来填充。
- 其余四个分支无事实但保留整个命名框架。所有输入仍受同一纯合成来源边界，不读取真实 PDF。

独立算术下界：40 个 module claim + 40×4 个空子槽位 + 1 个论文根 + 5 个一级分支 =
**至少 206 个实际受管节点**，尚未计入其他必需框架标签。40 条记录仍在 40 上限内，但
总节点必定超过 96；不要用“事实数 40”掩盖展开预算冲突。

通过条件是**明确拒绝 canonical success**，报告 managed-node budget/geometry 的具体冲突：
不得删 claim、隐藏空槽位、合成 `/details`、缩字体、自动提高 96 或改成四分支。允许渲染器拒绝，
或保留完整 noncanonical candidate 后 conformance 拒绝；不强求通过某个生产内部异常类。
若保留 candidate，报告须逐项核对 40 个 module、160 个子槽位和五分支完整性。
baseline 创建、batch validated/repaired success 和 canonical commit 均不能用这份失败产物放行。
本输入不是用户对真实长论文预算的重新授权；若实际论文内容与预算冲突，须另行向用户解释选择。

## 批准后拟执行及可见产物

1. 核对以上输入摘要，展示命令、临时合成输出位置和最终报告位置；正常接口先建立各案例自己的
   base/baseline，并记录其实际三文件 hash。这里只准备材料，没有预先伪造生成文件 hash。
2. U-01～U-08 和 G-01～G-04 各自使用新副本，记录期望、实际返回、逐项守恒/冲突和写入数；零写入案例对
   protected Markdown/Canvas/sidecar 分别比对 hash，不仅检查返回状态。
3. N-18 分别记录独立事实记录数、展开受管节点数/下界、失败环节与预算；拒绝本身不能省略
   完整性核对。没有执行的 API 层明确 not-run，不能由单一 render 拒绝推导所有层已实测。
4. 单独写执行报告，包括输入摘要、每项 `passed / failed / not-run`、受控输出链接及未验证事项。
   不访问占位 source URI，不把这些结果表述为真实来源可靠或 Obsidian 美观验收。

待用户明确批准：**这批精确 JSON、U-01～U-08、G-01～G-04 与 N-18 的纯合成执行范围**。
测试驱动代码尚由调用方准备/复核，本材料没有运行测试、生成器或正常产品；没有修改真实 Vault。
