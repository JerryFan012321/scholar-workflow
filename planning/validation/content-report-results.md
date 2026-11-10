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

## 实际发布、安装与业务修正回执

源码c4ec9e6d52b80d3d3c7b2911f7e083b1a949b902，runtime c594d0b849d1a470859c21ed600abd0d41e23a9a。
正常推送hotfix/release，pipx固定发布SHA、Codex/Claude市场正常更新0.53.0；未合并main。
37个发布文件、91次安装位置SHA256比较全部一致；两个受管服务build2224408b063ff8dc。
日常56292、test56303均通过普通URL实际打开；test保留原4个合成候选，没有新业务写入。
日常Lucy详情可见完整两段内容简介，出处默认折叠；截图为原test对象_work/content-quality/lucy-installed.png。
四条Blog与AgiWorld通过安装态revise-content逐条CAS修订至revision2，保留逐条历史；
总13候选、推荐记录/计数、评价、决定和入库事实守恒，其余8条正文/版本不变。
这五条原无审阅或选择，因而未触发需重新选择的状态变化；通用清审阅规则由合成检查覆盖。
源网页正文、source hash、草稿和实际修订字段均留在同一对象。未调用Zotero写接口。
私有修正前数据库和JSON留在用户状态目录recovery/0.53.0，不进入仓库或Vault提交。

独立agent报告样例只读取新Skill链和合成输入，自动核实计算及事实边界；没有提供EXPECTED或旧答案。
它发生于开发验证阶段，不冒称安装后新会话一次生成验收。安装后只核实真实宿主分发字节和页面。
当前人工待评阅两项：Lucy等完整简介的精要与文风；合成报告能否独立读懂条件、结果和证据边界。
Markdown字体由阅读器提供；DOCX/PPT未生成、未作原生渲染验收。此前已认可论文/Canvas不重复验收。
回退可按上一正常版本runtime01f2858098629266b801d14bdb719642aee1b4f1重装，保留数据；
真实内容修订有本机恢复快照，回退安装本身不会自动撤销业务修订。
