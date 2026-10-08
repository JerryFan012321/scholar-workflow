# 摘录直接证据强调：开发验证结果

日期：2026-10-08。分支：`codex/hotfix-canvas-images-release`，基于`fbcf382`的未提交开发增量。
用户明确批准合成测试及必要回归；本轮没有Vault/Zotero写入、发布安装或真实论文重分析。

## 本地0.41.7准备（后续进展，不覆盖下方原测试记录）

四处版本及uv.lock已统一0.41.7；offline lock只改变本包版本，24包及依赖pin保持。
仅版本/manifest、90强调及10 eval结构定向回归：105通过，1.45秒。行为代码未再改动，
此前1986完整回归保留，不重复业务。下一步本地提交及runtime归档/wheel/sdist静态检查；
真实构建结果完成后记录。当前PATH仍0.41.6，未获下一正式发布安装与候选写入授权。

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

## 尚未证明

新能力未提交、发布、安装，未改既有V-JEPA 2文档包。普通合成段落的支持关系明确，
但这不认证真实论文逐句来源或全篇科学支持。新强调在Obsidian里的可读性待后续正常
hotfix安装后的单对象人工评鉴；此前有效的Canvas和图片批准保持，不重新要求同样审批。
G17的模范Vault/项目/实验及原生工具全部交付仍分别按其证据核对，本轮不能宣称整个阶段完成。
