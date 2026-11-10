# 内容、文风与报告落地

2026-11-10，0.53.0，codex/hotfix-content-report。沿用已定共用规范，不新增未讨论的报告模板。
引用链：recommend-papers→recommendation-intake的简介质量→content-and-style Skill→共用规范；
create-report→report规范→同一共用Skill/规范；其他既有业务通过human-presentation按需桥接。
论文/Canvas/实验原有格式保留，Reading Report仍属于推荐，不固定字数、章节或图表数量。

复用旧asset-management未发布的4个共用文件和两份规划确认记录，不合并Notion等无关WIP。
新增report薄入口及中英使用说明。报告样例使用同一test对象的合成输入，独立agent只读新Skill和输入，
未提供旧答案。样例共同条件与200/140ms结果相邻，60ms/30%可回算，质量/显存/吞吐缺口真实。
Markdown字体由阅读器控制，未据此宣称Word/PPT字体或渲染已实机通过；人工评阅待用户。

433项定向通过，13.62秒，涵盖推荐内容修订、全部推荐相关回归、eval schema、插件清单、
论文格式与发布边界；Ruff/JS/diff及两个Skill校验通过。47个运行期链接及锚点有效。
没有重跑全项目或整库业务。早期标签断言、夹具变化等失败XML均保留。

官方网页已重新核实五条，四条Blog依据正文写简介，AgiWorld项目页使用完整作者Abstract译文。
代码增加本地revise-content/content-history，以CAS保存阅读字段before/after和署名，不新增推荐记录，
内容改变清审阅和待入库选择，保留旧评分/入库事实并提示内容失配。新旧作者摘要保留优先级。
代码校验结构与状态，不冒充完整性/事实支持的语义裁决；agent按规范检查，人类评阅分别记状态。

后续真实安装与五条修正回执另附本节。来源正文、草稿、报告输入/期望/成品及XML只在原test对象
_work/content-quality中，原始来源与人工内容不改，不写Zotero，不合并main。
