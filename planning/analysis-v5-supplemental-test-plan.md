# Canvas 对齐与无交叉：补充测试批准方案

2026-10-04，状态：**用户已批准并执行；两项测试与Ruff未通过，见analysis-v5-test-results.md**。
下文保留批准时的精确方案；不自动授权更改输入/源码后的复测或发布安装。

## 修正后复测提案（已批准并执行）

用户本轮明确批准；实际结果为53项定向、1408项完整回归通过，Ruff剩4项，其他两项静态检查通过。详见 `analysis-v5-test-results.md`。此批准不授权随后代码修改后的再次复测或发布安装。

仅修正 G-03 独立预期的 1 px 误算、G-04 摘录的 Markdown 字面转义断言及原五个 Python 文件的 lint 写法。不改变模板、58 个坐标、论文内容、2:1 长宽比或无交叉门禁。兼容导出保留。

G-03 标签底部为 `9103+66=9169`，而内容底部为 `9039+129=9168`；正确 bbox 是 `3056×9169`，仍须拒绝。修正输入 SHA-256 为 `1fa29ce6f02dca72099a091867b1151449e8bc473ae2c088c1e628b2862287e7`。G-04 精确检查字面转义摘录，Canvas 仍不得包含摘录。

批准后沿用下文命令：两个 v5 文件预期53例通过；完整 `tests/unit tests/contract` 无失败；原五文件 Ruff、skill quick_validate 和 `git diff --check` 通过。影响仅合成临时文件、依赖缓存及忽略的本地报告。不触碰 Vault、外部应用、服务，不提交、发布或安装。修正尚未复测；原1406通过/2失败只属于前次执行。

本方案不扩大原论文模板，也不重新分析 V-JEPA 2。继续保留完整五分支、独立可编辑子槽位、
原文入口、正文反链、正文逐字摘录和单论文文件夹。它补查上轮未准备的安全/预算输入，以及
只读审计发现的几何漏检；上轮 164 passed / 2 skipped 是历史范围的结果，不能放行本轮新代码。

## 精确输入与预期

完整字节摘要、原始内容和逐项手写预期见
[更新安全与预算独立输入](analysis-v5-update-safety-inputs.md)，机器输入为
`tests/fixtures/analysis-v5-safety-inputs/`。只有一个虚构论文 base，不请求任何真实 PDF 或阅读器。

| 范围 | 输入 | 必须看到的结果 |
|---|---|---|
| U-01 | 完整 Method focused 更新，只改 module 2 一条 N/A 理由 | proposal 合格；其余四分支内容、证据、链接和身份原样 |
| U-02～04 | 结构容器改事实、point 顺序交换、point 身份重映射 | 精确原因拒绝 targeted repair；不把身份变化当修复 |
| U-05 | 人工编辑一个受管 Method 文本节点 | paired conflict；当前 Markdown/Canvas/sidecar 三文件零写入 |
| U-06 | 整图安全平移、改色、图外自定义两节点一边 | ready proposal 保留所有安全人工图项；不冒称已提交 |
| U-07～08 | 同一对象普通 v4→v5 或 v5→v4 更新 | 明确拒绝隐式版本转换；三文件不改 |
| G-01 | 保留全部必需边，另加一条跨分支受管边 | 明确 `canvas-unexpected-edge`，不能因 endpoint 存在而放行 |
| G-02 | 新人工 text 节点覆盖既有 Method 节点 | 明确 `overlapping-canvas-nodes`；不自动删除人工节点 |
| G-03 | 固定 58 个节点用整数坐标拉伸为 3:1 | 明确 `canvas-aspect-limit`；不能以浮点 schema 错误冒充几何测试 |
| G-04 | 只保留原 l-r 记录的合法 focused Limitation | 原事实/引文不变、可编辑、对齐、无交叉、长宽比≤2:1 |
| G-05 | 两个图外人工节点以 square 线穿过固定 Method 正文框 | 指明该边与该框的 `canvas-edge-through-node`；端点不是 managed 不能豁免 |
| G-06 | 两个人工节点以 x=272 竖线贯穿主干，不穿任何正文框 | 指明该人工边的 `canvas-crossing-edges`；不能靠 overlap 或穿框失败替代交叉检测 |
| G-07 | 仅把现有 root→Abstract 边的 fromFloating 设为 true | 明确 `canvas-edge-routing-unverifiable`；加载后可自动换 side，不是假定原 JSON 路线安全 |
| P-01～03、07～08、10 | v5 point text 或 Canvas summary 注入标题/机器标记，含前导空格与裸 ### | model 与 checked-in schema 按对应字段明确拒绝，不调用 renderer 修字 |
| P-04～06 | 正常 #tag 文本、旧 v4 列表中的 # 文本、旧 v3 point | 版本/文本保持；v4/v5 正向产物不增加章节，v3 仅证明输入兼容 |
| P-09 | v4 point 注入机器 claim 标记 | 提前拒绝已有格式禁止的机器标记，不扩大为 v4 ATX 文本限制 |
| N-18 | 40 个独立 Method module，逐项保留四个空命名子槽位 | 展开至少 206 个节点，明确预算失败；不删记录、不合并槽位、不提高 96 上限 |

测试驱动为 `tests/unit/test_analysis_v5_safety.py`：26 个具体案例，不使用“待准备”的空 skip
占位。其覆盖 render/conformance/baseline/zero-write update 和既有 targeted-repair 身份边界；
新增 v5 的 batch 状态/清理、canonical commit、安装态 CLI、GUI 和科学来源未由这 13 例覆盖，
不能用 baseline 拒绝替代这些层的实际证据。完整回归中的旧版本案例也不自动放行新版入口。

G-01～03、G-05～07 的审阅参考图保留本地但不提交。干净 checkout 在批准后由固定 IR 重建隔离 base，
必须先匹配已展示的全字节 hash、58/57、包围盒和旧坐标，再施加固定变体；不匹配则停止。
N-11 旧测试也改用整数坐标并断言明确的长宽比 finding。

追加 G-05～07 仅改变几何检查，不改事实、原文、模板、节点预算或生成器。
同轮只读查阅原生 Canvas 控制点函数和 Advanced Canvas 的路由/浮动端点实现；这不是 GUI
测试通过。空 style 的共线原生边使用控制点凸包作保守检查，不把端点矩形当全部轨迹；
未知走向报告不可证明，不为了通过 U-06 改写该既有安全人工图输入。

追加 P-01～10 来自同一合成 IR 与固定 v4 base，另有一个在输入清单完整列出的 legacy v3
内存对象；不运行真实论文、不写文件。负向必须同时由模型和 JSON schema 按确切字段拒绝；
正向保持版本、其他 claims/points/evidence，v4 的原列表兼容不被误加新版 ATX 门禁。

## 执行顺序与通过标准

1. 核对固定输入摘要，不替换事实、坐标、mutation 或预期。
2. 运行补充独立测试和当前五分支测试；每个案例从独立干净副本开始。
3. 运行当前完整 `tests/unit tests/contract`，而非复用旧 0.31.1 的 1,355 项结果。
4. 检查本批新代码/测试的 Ruff、skill frontmatter 及 diff 空白；发现失败原样报告，不自动放宽格式。
5. 报告逐项 expected/actual、实际通过/失败/未运行、输入身份和未验证事项。补充测试成功不意味着可直接发布。

拟执行命令：

```sh
rtk proxy uv run --locked --with pytest pytest \
  tests/unit/test_analysis_v5.py tests/unit/test_analysis_v5_safety.py -q
rtk proxy uv run --locked --with pytest pytest tests/unit tests/contract -q \
  --junitxml=planning/acceptance/analysis-v5-synthetic/full-unit-contract.xml
rtk proxy uv run --locked --with ruff ruff check \
  src/scholar_workflow/analysis/models.py \
  src/scholar_workflow/analysis/complete_reference.py \
  src/scholar_workflow/analysis/complete_conformance.py \
  tests/unit/test_analysis_v5.py tests/unit/test_analysis_v5_safety.py
rtk proxy uv run --locked --with pyyaml python \
  "<installed-skill-creator>/scripts/quick_validate.py" skills/analyze-paper
rtk proxy git diff --check
```

上面的 skill-creator 根由当轮宿主 skill catalog 解析，并在执行前展示；它只是本机开发工具，
不把用户绝对路径写入可提交文件、运行文档或发布包。测试驱动准备完成后再
请求批准；未批准不执行上述任何命令。源码或输入再次改变时依根规则重新确认。

## 影响和展示产物

- 新用例仅使用隔离的合成文件、baseline 和状态；当前三文件的实际 hash 在建立隔离 base 后记录，
  不伪造未生成产物的摘要。完整回归沿用仓库的 unit/contract 合成 fixture、mock adapter 与临时目录；
  HTTP 契约测试可启动并关闭自己的临时 loopback 测试服务，不操作现存 Hub、cmux、Codex 或应用。
- `uv` 可以准备开发测试依赖；不更新已安装 Scholar Workflow，不更改插件缓存或版本。
- 持久结果：`planning/analysis-v5-test-results.md` 追加本轮独立结果；JUnit 等生成产物仅留在已忽略的
  `planning/acceptance/analysis-v5-synthetic/`。fixture、测试代码与说明可提交，实际生成图不提交。
- 不访问正式/测试 Vault，不打开 Zotero/Obsidian，不点击合成来源 URI，不批量扫描、入库、迁移或改论文。
- 不提交、推送、发布、安装、切换服务或合并 main。本次批准只覆盖上述自动测试。

## 安装后人工评鉴仍独立

**最终 Canvas 需要人来评鉴。** 正常安装可识别的 hotfix 后，另行批准在 test Vault 的
V-JEPA 2 文档包中新建一个文件夹；旧样张不覆盖。届时在 Obsidian 打开该原生 `.canvas`，
总览检查五分支、同层左边缘对齐、直角线无交叉/穿框、没有单轴过度摊开；放大后检查框大小、
留一行点击空间，编辑一个节点并点击原文和正文反链。只有用户明确认可，才记人工评鉴通过。
这不是当前自动测试的写入授权，也不把合成图当作新 V-JEPA 2 产品效果。

待批准：**补充 U/G/P/N-18 精确用例、修正后的 N-11、当前完整 unit/contract 回归及列出的静态检查**。
