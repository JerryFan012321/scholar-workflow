# 内部项目入口 skill：开发评价结果

## 结论与交付边界

2026-10-09：新增独立 `organize-project` 与共享 `references/project-entry.md`。
它复用既有项目资料选择、代码与实验档案，提供内部 PROJECT 的六节结果契约；
初始化、简短 overview 清单、内部 PROJECT 与公开 README 各自保持边界。
没有新增 CLI、schema、状态库或 Hub 前置条件，不规定内部思考顺序。

独立手写预期和测试计划先于模板及候选；另一任务手写三组 raw 输入，候选生成者
不知道 EXPECTED，独立核对者则直接对照原始输入、先行预期与冻结候选。三个场景
在本次有限行为核对中未发现不符；这不是普遍鲁棒、安装态或原生阅读验收通过。
整个 G17 未完成，没有发布安装、修改版本或合并 main。

## 输入、实际操作与产物

- 预期：`tests/fixtures/project-entry/EXPECTED.md`。
- 计划：`project-entry-skill-test-plan.md`。
- raw：`tests/fixtures/project-entry/INPUTS.md` 所列 complete-inline 20、
  sparse-external-plan 15、preservation-conflict 15 个小文件，合计50。
- 记录复用已有字段形状，但不是完整初始化档案，不宣称实验 CLI 自动发现这些 JSON。
  两个小 Canvas 只作导航输入，不代替正式论文分析五分支格式验收。
- 读取50个场景文件与INPUTS；候选分别另存到独立展示目录。不执行任何源码或配方，
  不读取真实项目/Vault/Zotero，不调用外部应用或网络，不生成真实论文或实验结果。
- 保留原README、人写PROJECT/SCHEDULE、代码/config、实验记录及论文单元。

当前展示位置已于2026-10-10转存到test Vault的
`Scholar Workflow 实验/上层组合审阅-20261010/项目入口/`。
原始版本逐字节保存在同审阅目录的 `复现记录/原始展示/project-entry-skill-candidates/`；
当前三PROJECT只机械重定位入口到随附合成输入。独立转存计划见review-location-test-plan.md，
实际结果持于test审阅目录；下方2026-10-09生成事实和当时边界保持为历史记录。
内有 `GUIDE.md`、三个场景各自 `PROJECT.md`、`EXECUTION-NOTES.md`、
`INDEPENDENT-REVIEW.md` 与仅作测试字节基线的 `input-baseline.json`。

## 各项实际结果

| 检查 | 实际结果 | 不能推定的事项 |
|---|---|---|
| 新 skill 的 quick_validate | 通过 | 不是触发正确性或最终效果证明 |
| `tests/unit/test_evals_schema.py` | 10项通过 | 只查JSON结构，不代替host行为判断 |
| 独立职责及路由审阅 | 未见阻断缺陷；内部PROJECT、公开README、纯实验比较、初始化和普通code review边界明确 | 不是已安装宿主的自动触发测试 |
| complete-inline | 2Run/4Attempt/2Artifact逐项链接；详细计划仅内联候选 | 两份report字节匹配不等于有效metrics或实际执行 |
| sparse-external-plan | 缺失config/report/Canvas明确保留；GPU主张无源码支撑，不画成已证实边；PROJECT只摘要链接唯一SCHEDULE | 不填零、不改选配置、不生成缺失结果或日期 |
| preservation-conflict | 人写理由和相反计划保留；候选另存，不选计划权威；远端产物只保留声明 | 不下载远端、不覆盖原文件、不宣称现行计划已修好 |
| 独立直接入口解析 | 21/16/16共53个文件入口和每份6个节内导航均指向所选目标/对应标题 | 文件存在与标题匹配不是VSCode实际点击 |
| 原始集合/字节守恒 | 50raw＋INPUTS＋EXPECTED共52文件前后集合、size/SHA-256完全相同；无symlink | 不是文件系统原子快照或已验证备份 |
| 冻结候选守恒 | 三PROJECT与EXECUTION-NOTES四文件核对前后size/hash不变 | 不代表人工接受 |
| diff检查 | 通过；论文分析skill及analysis代码相对HEAD无改动 | 不重审已认可论文/Canvas格式 |

实际档案合计4Run、7Attempt、4Artifact：两份本地report、一个缺失report、一个
manifest-only报告。两份本地报告实际250/258字节且各自hash匹配；角色report不是
metrics，数值只并列为手写声明，不算已验证差值/排名/显著性。同Run重放不算独立实验。
未核验的Target、提交、阅读器和备份均保留其限制。

详细独立观察与冻结文件hash唯一记录在展示目录 `INDEPENDENT-REVIEW.md`，
实际读取/写入范围记录在 `EXECUTION-NOTES.md`，不以生成者自评代替核对。

## 失败与最小修正

运行前独立审阅指出一个P3：若已有唯一计划叫BACKLOG，新模板不应强制改为
PROJECT/SCHEDULE。已在共享reference小修为：新计划采用PROJECT或SCHEDULE，
其他既有唯一权威保持原名并链接，未获授权不迁移。不据此改变测试预期或输入。

还明确Mermaid需要支持它的预览器，不能假定已安装；完整组候选补齐同一依赖说明，
然后冻结所有候选再交独立核对。没有内容/链接/计划/守恒核对失败，没有为获通过
放宽格式或修改raw。收尾文档同步一次patch因旧设计稿上下文不符被整批拒绝，
检查确认未写入后修正补丁重发；不是产品测试失败。

不重复上一轮2417项完整代码回归；本轮仅文档/skill和合成输入，提交前仍须按仓库
规则说明并执行完整回归，不能称现已可提交或发布。

## 人工与安装态交接

会话明确给出候选位置及以下判据：在VSCode打开完整组PROJECT并预览Markdown，
点击源码、实验记录/报告、论文来源/分析/Canvas和计划入口，判断当前情况是否
一眼可理解、图是否紧凑且诚实、链接是否直接、状态与归属是否清楚。另两组可检查
缺失诊断和计划冲突；其中计划分歧只是合成测试，不要求用户裁决真实项目日期。

Mermaid预览依赖未核实；Canvas原生显示需支持它的阅读器，未配置或调用Obsidian。
以上阅读、渲染、点击及人工美观均待评鉴；已安装插件触发另走正常hotfix发布/安装流程。
本轮没有替换真实项目的PROJECT，也没有写test或正式Vault、Zotero、服务或worker。
