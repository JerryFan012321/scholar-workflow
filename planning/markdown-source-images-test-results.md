# 正文来源图片：实际开发验证结果

## 0.41.6 实际发布、安装与单篇暂存

收尾只改实际状态文档/eval描述：10项eval schema通过（0.02秒），diff检查通过；行为代码
没有变化，未重复1896完整回归。Obsidian只读确认新展示稿存在，当前人阅读页保持原登记稿。

用户明确批准后，source26a2284/runtime852f983推送至release，正常pipx固定runtime、
Codex市场add得到0.41.6。CLI版本/direct_url/关键模块和cache全部244文件一致；main未合并。
独立输入/预期先于执行：现有V-JEPA2 IR仅启用正文图开关，PATH公开stage一次validated，
零修复/零canonical写入。命名展示副本check conformant、零findings、69内容108节点107边；
独立比较完整Canvas JSON、IR其他字段与全部原文不变。Markdown只增图2/表2题注源页两行，
三图各一次且byte/hash相同，15Source+7外部保护共22未变。成果及原始输入/回执/核对
保存在test“Scholar Workflow 实验/正文图片验收-0.41.6”，不重跑分析、裁图或实验。

实际失败与纠正：pipx upgrade拒绝URL（无该次变更），正常install固定SHA成功；
marketplace upgrade网络clone超时，正常add成功并全字节核验；观察器误用论文名读取stage
通用文件，修正观察路径；直接以通用analysis.md显示名check按门禁拒绝，命名副本保持
暂存三文件字节后通过。未改变生成输出、代码、缓存或再次stage。

展示仅供新增正文阅读评鉴，Canvas反链仍指待原位采用的原正文；未commit/provider apply，
不冒称新根复现。旧Canvas批准保持，新增图片位置/题注可读性独立待人。完整G17、科学
全项认证和其他工具便利性不由本单项完成。以下开发与未安装表述为历史。

2026-10-08，`codex/hotfix-canvas-images-release`；基于已提交父版本`10f501b`的开发增量。
计划与输入先于代码和测试，见[独立测试计划](markdown-source-images-test-plan.md)。
不是新发布或安装态验收。

## 实际执行

| 检查 | 实际结果 |
|---|---|
| 新中英文生成用例，旧实现RED | 2 failed，旧profile拒绝未知`markdown_source_images`，符合预期 |
| 首次全图片用例 | 57 passed / 3 failed；新测试误按未转义`Q_METHOD`/`Q_ABLATION`查找原文。既有quote renderer正确转义；修正测试预期，没有改变生产摘录 |
| 修正后图片定向 | 65 passed，1.41秒 |
| 受影响分析与eval结构回归 | 622 passed / 1272 deselected，15.79秒，5既有弃用警告 |
| 补充HTML隐藏样例、baseline schema、合法加长closing fence后图片+eval | 79 passed，1.44秒，其中图片69、eval结构10 |
| 最终完整unit/contract | 1896 passed，89.04秒，11既有弃用警告 |
| skill quick_validate | Skill is valid |
| 修改的Python与测试Ruff、diff空白检查 | 通过；初次Ruff提示已有import排序，已在触及文件中最小修正 |

主要命令：

```bash
rtk uv run --with pytest pytest -q tests/contract/test_analysis_canvas_images.py -k selected_images_render_beside_markdown_records --tb=short
rtk uv run --with pytest pytest -q tests/unit tests/contract -k 'analysis or evals_schema' --tb=short
rtk uv run --with pytest pytest -q tests/contract/test_analysis_canvas_images.py tests/unit/test_evals_schema.py --tb=short
rtk uv run --with pytest pytest -q tests/unit tests/contract --tb=short
```

## 证明的边界

- 新v5明确启用时，选定流程图/实验表在其Markdown record旁生成，摘录、caption和原文页链接保持。
  conformance拒绝漏图、改图、错record/文末图库、caption或源页修改。
- 只复用对应point或其所属claim的实际embed；文件名、普通链接、code/转义/HTML隐藏样例、
  其他point不满足该record的显示要求。已有同点Markdown/Obsidian embed不重复添加图，保留题注/源页。
- 完整Canvas JSON不因该开关变化；旧省略/false的序列化和输出保持，baseline符合公开schema。
  focused保留开关，whole可明确采用，已启用不能普通更新关闭。
- 只修改生成、校验、schema、既有更新边界与对应运行期文档。不新增源图生成器、依赖、
  图片类型、Evidence/图库分区、内部推理步骤、事实或文件权限。

## 未做与待完成

实时只读检查：当前CLI为0.41.5，安装环境的`AnalysisProfile.model_fields`没有新字段。
本次没有发布、安装、修改cache、合并main、切换服务、调用Zotero/Obsidian或写Vault。
已有test V-JEPA2正文实查在方法处有图2、实验处有表2、局限处有EK100段落图；不重复
其旧业务操作或已通过Canvas图片评鉴。原checkout的既有未提交修改保持。

新开关的安装态单对象验证仍待后续正式hotfix安装；新增正文图片的人类阅读体验待明确确认。
开发全绿不代表外部阅读器、科学来源或G17整阶段完成。新源码规则由skill的v5 reference持有，
不是把开发测试步骤塞进执行skill。

## 0.41.6 本地版本与打包准备

仅元数据增量，正文图片实现、依赖和此前1896完整回归所覆盖的行为不变。四处版本与
uv.lock本包版本统一0.41.6，`rtk uv lock --check`通过（24 packages，3ms）。
独立范围先写入上述测试计划的本地打包节，再执行既有manifest/runtime版本、69图片
契约和10 eval结构用例：84 passed，1.45秒；diff空白检查通过。未重复完整回归或业务。

本地归档与sdist/wheel将从此次干净已提交源码按既有release manifest构建；新建的
`dist/0.41.6-local.*/`仅存忽略的构建产物与独立实际结果，不进入Git或runtime归档。
这些静态构建结果不能替代正常安装，正式发布与安装仍待许可；PATH产品保持0.41.5。
