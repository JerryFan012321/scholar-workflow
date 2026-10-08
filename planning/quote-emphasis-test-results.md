# 摘录直接证据强调：开发验证结果

日期：2026-10-08。分支：`codex/hotfix-canvas-images-release`；初始开发基于`fbcf382`，
后续实现提交到`ac62b19842d29e5f070ed1788d37f773c015e398`，发布准备source为
`46880dc4802faf226f74d7577bf87312ea4abe89`。下方保留历史开发结果；当前发布/安装结果如下。

## 0.41.7 真实发布、正常安装与单篇候选

用户明确批准后，在独立干净clone运行既有make-release脚本，不手写release；15项发布
版本/manifest/eval定向检查通过，行为代码不变，不重复1986完整回归。

| 身份或操作 | 实际结果 |
|---|---|
| 源码 | `46880dc4802faf226f74d7577bf87312ea4abe89`，hotfix正常推送 |
| runtime | `aeed349e8b71ae19b33635c94ac9df29f901662e`，release正常推送，main未合并 |
| pipx | 正常install --force固定runtime；实际PATH产品0.41.7，direct_url commit匹配 |
| Codex插件 | 正常marketplace upgrade jerry-plugins及add，实际0.41.7；全部244 runtime文件字节匹配 |
| CLI源码字节 | 102个实际pipx Python模块均等于runtime Git |
| 原稿核对 | 原Source/Field和Zotero Local API父/附件identity、version975、PDF hash均匹配已准备输入 |
| installed stage-update | 一次completed/validated，零修复，canonical_written=false |
| installed check-bundle | 命名副本conformant/零findings；IR5、36claims、69内容、108节点、107边 |
| 独立守恒 | 完整选中分支14claims；只有3个quote_emphasis字段变化，原quote与其他IR字段相同；Markdown只改对应题注与粗体 |
| 原件与图 | Canvas完整JSON相同；三图片字节相同；Source70文件/provider5文件/registry/PDF保持 |
| 人工评鉴 | 三处新强调仍pending；旧Canvas/图片批准保持；不认证全篇科学支持或完整G17 |

新候选位于test Vault的`Scholar Workflow 实验/摘录强调验收-0.41.7/V-JEPA 2`。
完整命令argv、stdout/stderr、输入、选择、安装身份与独立保全JSON放在该候选`.review/`。
不执行commit-bundle/provider apply，不重分析/裁图/实验/整库迁移或切换服务。
旧Canvas正文反链保留原正式分析；此非canonical副本不冒充新owner/新根复现。

独立观察器首次用下标访问可省略的空source_spans抛出KeyError，产品stage/check此前已成功。
只修正观察器为空列表读取，仅读现成文件完成独立比较，未重stage/check、未改产品或输出。
Canvas物理SHA由`6989e00a85713c84d31d58d76c40ebadfe02a5af54b9ef90aaaea343e5d9e610`
变为`39c2bb8967a41cb73374c4cba14d05fd0f420220ea1501b35ff621bbe6a2591c`，完整JSON
相等，差别仅重新序列化；不谎称字节相同，也不手改候选来消除hash差异。

Obsidian接受新文档打开及preview请求，CLI状态返回该候选。一次顶层await观察表达式被
CLI拒绝后改为普通调用；dev:screenshot实际捕获旧0.41.6文档，不作新GUI通过证据。
保留截图和观察错误；停止重复窗口操作。会话明确提供新文件、搜索“粗体：”、三处观察
效果及判断标准，用户明确确认前保持pending。

最终构建来自上述source，而非旧ac62本地包。244runtime文件/16路径字节一致，开发层
排除和已知个人路径/凭据模式扫描通过（非任意秘密的形式化保证），wheel110/sdist126成员
源码一致。最终临时build产物不进入Git：

| 文件 | SHA-256 |
|---|---|
| scholar-workflow-0.41.7-runtime.tar | 53d4232bdf1f087b057afb6504c04b015117a2ee6d2dc86a5930b51da946be5a |
| packages/scholar_workflow-0.41.7-py3-none-any.whl | cb77cccb52a335aa0a479276631dab37af721cf0bd43923f7dee7f0c3514e28c |
| packages/scholar_workflow-0.41.7.tar.gz | f3732765bd7168a49336284eae0753c1edfc32e16ab45dec3d6148cd42303bf7 |

回退为正常pipx固定Git runtime`852f98376600fb0b8286c7976476c8e008710c38`重装0.41.6；
Codex旧0.41.6安装记录/cache保留；不假定当前宿主支持任意旧版本选择，若需回退须先核实
正常宿主入口，不手改缓存或为回退擅自更改远程release。

## 0.41.7 发布安装获准（此前准备历史）

用户已明确批准正式发布/正常安装及test单篇非canonical候选。范围见HANDOFF当前节；
运行时代码及1986完整回归不变，仅补15项版本/manifest/eval检查。随后从已核原稿的
完整实验/局限分支派生一次安装态保留布局更新，只加三处强调，不关闭或加入其他profile
选项。不覆盖原稿、不登记provider、不重新分析或验证旧Canvas。源码/安装身份、
候选及独立守恒检查的真实结果观察后补记，不能把授权或本地包当完成。

## 本地0.41.7准备（历史进展，不覆盖下方原测试记录）

四处版本及uv.lock已统一0.41.7；offline lock只改变本包版本，24包及依赖pin保持。
仅版本/manifest、90强调及10 eval结构定向回归：105通过，1.45秒。行为代码未再改动，
此前1986完整回归保留，不重复业务。已本地提交上述source，并按现有16路径清单归档；
没有运行release分支切换/清空步骤，release/origin-release仍为`852f983`。
正常offline构建wheel/sdist成功，静态核对244 runtime文件逐字节等于该提交，归档清单
一致、零symlink、开发层排除、已知个人路径/凭据模式未发现；wheel110成员及sdist126
成员的源码字节一致，版本/入口/强调实现存在。扫描不是对任意秘密的形式化证明。

产物在`dist/0.41.7-local.aGBdON/`，仅忽略的本地文件：

| 文件 | SHA-256 |
|---|---|
| scholar-workflow-0.41.7-runtime.tar | 3c5c079da9ef8abe5dc0a4bf62a8d5cd707c747cce5df32101c58c7143a83edd |
| packages/scholar_workflow-0.41.7-py3-none-any.whl | 20cc8afd3a9c9553cf7f7bda58af9aaa9eeed5d84a5ad3b8b25b5a67bf7f27b3 |
| packages/scholar_workflow-0.41.7.tar.gz | 16159bef3ba659d5be29428eae9e9cd0509abad0c52ac93b2fb215ce98c8394b |

独立实际JSON在同目录`实际核对.json`，readonly核对器在同目录`verify-package.py`。
首次观察器在uv run中按PATH误选开发CLI0.41.7；改为显式pipx入口后重新核对为0.41.6，
包检查仍全部通过。没有为解决这个观察错误安装或更新产品，未隐去旧误读。
当前正式发布、正常安装和test单篇候选写入仍待用户答复；主线/业务未变。

## 已实现

- 原始`quote`逐字保持，独立`quote_emphasis`声明真正支撑当前论点的原文片段；只在
  Markdown加粗，必要语境保持正常字重。作者直接证据与推断依据使用不同题注。
- PDF/注册Markdown来源、中文/英文、claim/point及v4/v5兼容；来源链接不变，整个
  Canvas JSON不变。空/省略强调字段保持旧IR序列化和输出。
- 不存在、重复歧义、重叠、空值、非法类型、不可显示profile及不可核验证据拒绝。
  多行/Unicode/原文Markdown和HTML语法保持字面文本；相邻合法片段合并显示，不产生
  连续四个强强调分隔符。schema只检查结构，精确子串关系由model检查。
- 删除/改变/移位强调不能通过conformance。focused更新保留未选分支和完整Canvas；
  并发人类正文编辑返回成对冲突，保留当前原件，而非自动接纳后覆盖。

## 独立输入与实际执行

输入：`tests/fixtures/analysis-quote-emphasis/SOURCE.md`的三个完整合成句子。
预期：先手写`EXPECTED-EXCERPTS.md`，只第二句加粗，前后句/限定/数值/单位保持。
使用既有合成v4/v5框架验证投影及成对更新，不使用真实论文的业务输出冒充测试输入。

| 执行 | 实际结果 |
|---|---|
| 实现前3个正例 | 3失败；旧模型/schema拒绝新字段，符合RED预期 |
| 新功能用例 | 90通过；涵盖上述呈现、结构、精确片段及更新保护 |
| 新用例+既有摘录回归 | 148通过，3.34秒 |
| 完整`tests/unit tests/contract` | 1986通过，93.78秒，11个既有SWIG/fork弃用警告 |
| 最后等价lint修正及相邻片段断言后 | 同一90个定向用例再次通过；没有再次运行整套测试 |
| 受影响Python文件Ruff / `git diff --check` | 通过 |
| `skill-creator`入口校验 | `Skill is valid!`；不等于运行效果认证 |
| 当前安装版查询 | `scholar-workflow, version 0.41.6`；保持未更新 |

完整回归命令：`rtk proxy uv run --with pytest python -m pytest tests/unit tests/contract -q --tb=short`。
最终定向命令只选择`test_analysis_quote_emphasis.py`和`test_analysis_quote_emphasis_contract.py`。
完整回归后唯一代码修正是依Ruff将相邻区间的`zip`等价替换为`itertools.pairwise`；
最终90用例包含该模型路径及新增相邻片段断言。没有宣称新的安装构建已经验收。

初次新用例还暴露了schema的非显示/不可核验强调与末尾换行漏洞，已修正后复验；
v5使用既有`markdown-source-quote-placement`诊断，v4使用`markdown-source-quote-mismatch`。
人类编辑用例原先误期望ready，核对既有契约后改为严格要求conflict并守恒当前原件；
没有为追求通过而放宽生产代码的冲突保护。

## 开发阶段尚未证明（历史；当前安装态结果见顶部）

新能力仅本地提交，未发布、安装，未改既有V-JEPA 2文档包。普通合成段落的支持关系明确，
但这不认证真实论文逐句来源或全篇科学支持。新强调在Obsidian里的可读性待后续正常
hotfix安装后的单对象人工评鉴；此前有效的Canvas和图片批准保持，不重新要求同样审批。
G17的模范Vault/项目/实验及原生工具全部交付仍分别按其证据核对，本轮不能宣称整个阶段完成。
