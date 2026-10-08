# 正文来源图片：实际开发验证结果

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
