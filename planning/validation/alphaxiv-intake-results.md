# 当前UX补充（2026-11-10）

推荐阅读与设置改版已完成，369项定向检查和同一四候选开发预览操作检查通过；
实际内容、边界、截图和待人工项见[UX实施结果](recommendation-ux-results.md)。
当前0.52.0仍未发布安装；个人0.51.1、真实账号/模型/Zotero未改。下文保留各轮历史结果。

---

# 每条推荐的个人评价（2026-11-10）

同一0.52.0未发布候选。每条paper/project/blog可选1–5分与4000字符备注，单独填写、修改或清除。
首页仅显示紧凑标记，详情折叠编辑。评价独立revision，不影响审阅、选择、热度和入库计划。
Agent再次提交保留人工评价，资料变化后显示旧评价提示；冲突/失败保留当前草稿。
本地profile共用存储，CLI JSON可读，不启动模型/agent或自动推荐训练。

18项独立合同先行，未实现时18失败，完成后18通过。含退出/入库后端44通过、浏览/热度UI51通过，
最终全部推荐unit/contract定向314通过（9.58秒）；变更Python F/E9/I、JS语法和diff检查通过。
未重跑全项目全量，既有全量记录仍属各自快照。

IAB原tab/同一test对象：合成项目保存4分/备注→改3分→清除→再存4分→刷新，均显示正确。
API读回评价revision=4，4候选原资源/revision/选择/审阅/推荐/旧入库历史保持。
演示备注明确“界面测试”，不冒称人对研究质量的评价；其余候选未评分。

原60154预览通过自身shutdown接口停止；重新绑定端口出现Errno48且无存活listener，
未杀任何未知进程，改用动态62789。现有tab原位更新，无新标签。日常0.51.1服务和正式资料不变。

证据在原test对象_work：evaluation-first.xml、evaluation-backend.xml、evaluation-ui.xml、
evaluation-integrated.xml、evaluation-browser-receipt.json、evaluation-feed.png、evaluation-detail.png。
新功能待人工评鉴，未发布安装，不作为安装态验证。

---

# 撤销审阅与入库范围核对（2026-11-10）

同一0.52.0未发布开发候选；日常0.51.1未切换，未安装本候选。

- 已审阅详情增加“撤销审阅”；同一事务取消待入库选择，保留稍后看/忽略、正文和入库历史。
  进行中写入拒绝撤销，CAS冲突拒绝覆盖；撤销后旧入库计划失效，重新审阅不会自动选中。
- 按钮明确“预览Zotero书目入库”，测试态显示“预览模拟书目入库”，历史显示模拟结果说明。
- 当前确定性Python链路调用Zotero Local API，仅书目/分类；没有agent或模型参与。
  本机Zotero10.0.7只读probe成功（API3/schema44），不证明写授权或本按钮真实写库通过。
  source-preview.py注入内存fakeZotero；旧合成完成记录不代表正式文库已写入。
- 独立退出合同6项；后端含入库26项，前端45项通过。最终推荐unit/contract定向整合
  290通过/8.94秒；修改Python F/E9/I与diff检查通过。旧全量快照不冒充本轮全量。
- IAB原tab以未审阅合成项目确认→显示撤销→撤销恢复。只改变该合成对象的revision/time；
  4候选正文、最终选择/审阅状态、推荐和旧入库历史均读回守恒。没有执行新入库。

证据：原test对象_work/review-exit-backend.xml、review-exit-results.xml、
review-exit-integrated.xml、review-exit-browser-receipt.json、
review-exit-confirmed.png、review-exit-reverted.png。页面交互待人工评鉴。

完整入库建议由现有带上下文agent读取选中资料、目标和状态，按共享Skill编排；
模型由宿主持有，确定性命令负责写入。此建议不代表已实现交接队列、后台agent或模型执行器。

---

# 入库历史逐行呈现增量

2026-11-09：按用户截图，将历史记录从大卡片改为逐行列表。标题超出单行时省略显示，
完整标题保存在提示和展开内容中；状态/日期同列，展开保留分类、完整时间、范围、错误与原生链接。
独立成功/需处理/长标题/空列表输入及原浏览、入库确认/热度回归37通过（1.48秒）。
IAB控制连接首次失效，重置工具会话后原标签恢复；刷新看到两条既有合成记录并实际展开/收起，
未执行入库或修改记录。原端口/服务未重启，不改个人页面或安装版。
证据：原test对象_work/history-rows.xml、ingestion-history-rows.png、ingestion-history-expanded.png。
展示仍待用户评阅；本轮只验证受影响呈现，没有重复全量/科学/真实库业务。

---

# 最新纠偏：推荐要求放在对应来源条目内

日期：2026-11-09。同一未发布0.52.0候选，未发布/正常安装或切换日常0.51.1。
移除独立“推荐要求”顶层入口，改为各推荐源卡片内默认折叠、首次展开加载的要求列表/编辑器。
人和agent仍共用保存状态；新增来源归属及按源查询，省略字段的旧客户端编辑保留已有归属。
历史无归属和旧版本不推测或重写；本轮仅对一个明确合成要求显式登记alphaXiv。

检查输入/预期见同名plan最后一节。首次独立2合同失败（字段未实现）保留；最终归属8＋要求18项、
UI56项通过。统一推荐/来源/要求/HTTP/CLI/元数据289项通过，8.19秒，XML零失败/错误。
修改代码Ruff、JS语法和diff检查通过。4325完整回归是此前版本快照，本轮只做受影响检查，
没有重跑论文/真实推荐/全库业务。

真实IAB在用户已有tab原位更新：顶部仅研究推荐/推荐源/入库记录；alpha条目内展开推荐要求，
读原记录并保存成功，CLI按source_id读回第4版，HF列表为空；旧第1版及旧推荐完整引用保持。
各来源草稿/迟响应/错误跨源ID隔离由合成UI检查，不冒称已人工评阅每种竞态。

可见证据在同一个test对象_work：source-requirements-tests.log/results.xml、
frontend/source-requirements-final.xml、source-requirements-contract-first.log/XML、
source-requirements-integrated.log/XML、source-requirements-cli-receipt.json、
source-requirements-browser-receipt.json、source-requirements-inline.png。
源目录真实认证/取源、正常安装及人对新位置的评鉴仍分别待验。无新agent调度或云端调用。

---

# 增量结果：共用推荐要求

日期：2026-11-09。仍为同一未发布0.52.0候选；本节覆盖此前快照的完成状态。
人和agent可保存多份自由文本要求，版本不可变、CAS编辑，页面与CLI共享选定pool；
推荐记录引用自己的要求版本，按不可变历史投影完整内容，不重复保存每篇长要求正文。
旧无引用提交兼容，不迁移recommend.yml、不用source_context代替跨来源要求。

- 独立合同先5项失败（入口未实现），后5通过；首次失败回执requirements-first保留。
- store/旧推荐47项、前端48项通过；完整unit/contract4325通过、22跳过、11警告，224.24秒。
- 修改的Python F/E9/I与diff检查通过；只有UI测试import排序在完整回归开始后整理，不改运行逻辑。
- Chrome页面保存第1版，自由文本原样可读；开发CLI读同一记录，按第1版提交一条合成归因，
  随后保存第2版；页面显示agent来源与第2版，推荐详情仍显示第1版全文，既有人审选择保持。
- 保存不启动agent/抓源/入库；个人0.51.1服务及正式文库未变，未提交/发布/正常安装插件。

仅使用同一个test外围对象，来源与入库provider保持合成。为了用正常CLI状态布局完成共享验证，
将该对象原preview-state中的DB/锁移入preview-state/recommendations/test，原文件hash守恒，
没有复制第二份池。pool_id由状态路径派生，因此布局调整后其值改变；旧交接不能沿用，须从当前位置重新生成。source-preview.py使用新位置；CLI验收设置SCHOLAR_WORKFLOW_HOME
为该测试preview-state。开发venv/源码预览不是安装态证明。

当前回执：requirements-first.xml、requirements-contract.xml、requirements-store-final.xml、
frontend/requirements-stable.xml、requirements-full.log/XML、requirements-cli-receipt.json、
preview-layout-receipt.json、requirements-shared-editor.png、requirements-historical-detail.png。
截图、填写体验和操作易懂性待用户评鉴；真实MCP授权/取源、正式Zotero与正常安装仍另验。

---

# 推荐源目录、紧凑信息流与直接入库：修订结果

日期：2026-11-09。0.52.0未发布开发候选，codex/hotfix-alphaxiv-intake。
用户否定上一版专属工具页；下方旧检查保留事实，不能作为本版验证或当前能力说明。
未提交、发布、安装或合并main；个人0.51.1服务和推荐池不变。
收尾实查：PATH scholar-research=0.51.1；个人health PID9866/build ca24e98313b7fa29，未切换。

## 当前交付

- 推荐源目录记录非秘密MCP/API/feed/CLI说明、能力、公开文档与授权前置条件；自定义来源不需新增平台枚举。
  builtin只持于包内source_catalog.json，本地显式注册持于所选候选池，不复制成第二份事实源。
- alphaXiv使用宿主原生MCP连接，插件只声明官方endpoint。删除本批未发布的自建协议客户端、
  Keychain/APIkey层、远端调用路由与工具表单；浏览器只读目录，不执行源工具或agent。
  定义已收录与连接未检查分开；HF描述复用既有聚合器；X/知乎本人源仍计划中且禁用。
- 各外部agent用同一Skill查询目录、读取来源上下文、调用宿主原生能力、准备并common submit。
  来源备注与操作记录跨会话延续，明确agent_reported；提议不等于已关注，记录不验证远端事实。
- 首页只显示基本信息、两行引言、原始计数和来源/处理状态；点击行、标题或查看详情打开完整抽屉。
  完整摘要、原文、全部灵活附件、生产agent与渠道、审阅、选择及入库操作均保留，不改变存储内容。
- 保留明确分类/计划/确认/Local API写入及读回的书目入库；PDF和Vault知识单元保持独立。

## 修订版验证

- 来源目录22项合成检查通过，合同4项通过；禁外部网络与agent启动，真实隔离store跨实例读取。
- 通用来源状态＋入库＋目录59项通过；前端紧凑/详情/原指标33项通过。
- 变更Python F/E9/I检查通过；JS语法、diff检查通过。未改动的lifecycle/metrics存在既有import排序告警，不顺手改写。
- 最终完整unit/contract：4287通过、22跳过、11既有警告，221.97秒；XML errors/failures均为0。
  相比历史4294减少的是已取消专属MCP客户端/控制台用例，新增目录/跨agent/紧凑详情用例；
  旧结果仍保留在下方，不能与新快照混用。
- 真实Chrome使用同一个test对象与显式模拟provider：紧凑首页、实际source schema目录、
  接入信息、详情全部摘要/链接、合成审阅选择→分类→计划→模拟书目完成回执已观察成功。
  1352×760默认窗口中，列表顶部342px，单条199–222px；完整内容只在详情展开。
  页面与所有数据明确测试标记；没有访问alpha账号或真实Zotero。

## 证据与待验收

同一个test对象：`Scholar Workflow 实验/alphaXiv推荐与入库-20261109/_work/`。
当前文件：source-catalog-verified.log/XML、source-contract-tests.log/results.xml、revised-state.xml、
frontend/compact-catalog.xml、revised-full.log/XML、compact-feed.png、recommendation-detail.png、
source-directory.png、revised-ingestion.png。源码预览用source-preview.py，同一preview-state。
旧development-preview.py及旧日志只是历史，不可混称当前客户端。

视觉密度、详情阅读体验仍待用户评鉴；真实宿主OAuth/原生alpha工具、正常安装和真实文库入库
尚未验收。仅查看来源目录不启动认证，也不证明工具在当前宿主可用。X/知乎本人采集、后台推荐
调度及简单科学分析均未由本版实现。日常服务不切换；本版尚未获发布安装授权。

---

# 历史快照：被用户否定的alphaXiv工具控制台候选

日期：2026-11-09。版本：0.52.0开发候选。分支：codex/hotfix-alphaxiv-intake，基于已发布0.51.1。
未提交、发布、安装、切换日常服务或合并main；个人推荐页仍是0.51.1。

## 交付

- 推荐系统页内切换研究推荐、alphaXiv与入库记录，蓝白明亮配色；21项公开原生MCP工具按真实schema生成操作表单。
- alphaXiv热门发现与项目/领域专项agent并存，合并对象、保留来源；翻译/总结/热度缺项核验仍由本地agent按共同契约完成。
  不新增科学简单分析、模型配置、agent worker或自动调度。
- 原生MCP固定endpoint、有界JSON/SSE、当前tool schema校验；独立Keychain/APIkey，test禁真实凭据/原生provider。
- 页面和本地CLI共用topics/notes、研究者建议、待整理条目、operation journal；远端文库/关注仍为alphaXiv权威。
  相同未决写即使换ID也拒绝重发，显式对账引用更新的原生read；原文全文不复制进管理日志。
- 卡片明确选择Zotero分类→预览→确认→Local API精确查重/写入→读回条目与collection→回执。
  范围仅zotero_bibliography；PDF/Vault not_requested，不冒称完整论文单元。
  进行中的候选快照不可被并发提交/选择变更改写；版本更新后的旧完成回执有区别标注。

## 机器与浏览器证据

| 检查 | 结果 |
|---|---|
| 独立持久状态用例先行 | 初始6项失败，缺失方法；实现后6通过，后续补凭据/不明写/对账/活跃快照用例 |
| alpha客户端＋manifest/独立release fixture | 38通过，无真实账号调用 |
| 首次整合 | 105通过 |
| 审查修正整合 | 120通过 |
| 完整unit/contract | 4294通过、22跳过、11既有警告，230.57秒 |
| 最后本地管理/中文时间/执行回执/活跃快照修正后 | 173项定向检查通过，8.81秒；包含全部变更能力、旧推荐存储/热度、schema和包装 |
| 语法/补丁 | 两JS node检查与git diff --check通过；变更Python F/E9/I检查通过 |
| 真实Chrome＋合成provider | 页内切换、21功能列表、模拟热门流、stage成功；模拟Zotero分类/预览/执行/持久历史成功；未读真实Zotero或账号 |

完整回归先于最后小修；不得将不同快照写成同一次最终全量。浏览器使用开发源码和显式模拟provider，
不能替代正常安装、真实账号验收或用户人工通过。

证据仅test Vault单个外围对象“Scholar Workflow 实验/alphaXiv推荐与入库-20261109/_work”；
部分前端定向日志保留在同Vault另一个外围目录“alphaXiv与直接入库-20261109/_work/frontend”，无论文包修改。
保留修复前失败日志与后续通过回执，不通过增删样本掩盖失败。

## 尚待实际验证

- 新候选需另行获准正式发布/正常安装，当前运行状态不冒称升级。
- 安装后用户在alphaXiv Settings > API Keys创建key，终端alphaxiv configure隐藏输入保存；tools执行确认连接。
  本轮没有请求、读取或存储真实密钥，MCP实际账号能力和额度尚未测。
- 真正Zotero Local API分类/授权及单对象书目入库尚待安装后明确选定对象；未执行真实写入。
- 用户需评阅明亮页面、导航、原生表单与管理记录，当前仅自动查看，未标人工通过。
- 无自动后台agent翻译：待整理列表由现有agent读取并经相同submit提交。X/知乎自有账号采集仍为后续工作。
- 遗留in_progress书目记录不会被自动夺取/重放；崩溃后的管理恢复仍需明确检查，不宣称全自动恢复。
