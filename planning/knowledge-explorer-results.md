# 知识探索 0.49.0：开发结果

## 2026-10-28：测试隔离与 Vault 只读接入

显式test/personal运行环境、仅test登记、同份registry范围检查、三层检查与必要调整预览已接通。
最新156项定向检查通过；另补日常模式双Vault连接通过，相关14项全过。Ruff、JS语法和diff通过。
正式登记与11个现有论文文件字节不变。测试只在test Vault，未调用真实Zotero或资产原生打开。
新源码测试预览50984已送浏览器队列，旧63349停止；不代表正常安装或人工评鉴。
完整输入/结果/截图见test Vault的`Scholar Workflow 实验/_工作/vault-onboarding-20261028/`。


开发分支：codex/hotfix-knowledge-explorer。基于已发布0.48.0，在本聊天已有干净工作树实施。
当前是开发候选；未将源码运行、临时构建或浏览器开发检查冒称正常安装、实机或人工通过。

## 2026-10-27：真实双论文与外围编辑

test Vault 现在引用原 V-JEPA 2 和新 V-JEPA 2.1：两个整论文对象、四条条件/结果记录、
一条有依据的后续关系，分别保留13和5个声明资产入口；资产数没有成为模板配额。
原V-JEPA2正文/Canvas/图片不复制；新2.1目前只是有明确来源和两项核读评测的资料笔记，
不是深度分析交付。PDF已入Zotero，原生单附件重建索引后Local API可读37/37页。

全部12来源的非秘密元数据复制到test隔离状态，路径/inode/UUID一致才映射副本device；
未排除Source或改内容哈希，用正常安装0.48 CLI完成新test Source与论文登记。正式登记
仍保持原字节，并未据此修复旧全局绑定。网页使用未发布源码，不是0.49安装态验收。

真实界面定位、条件与关系编辑后保存/重读通过；六组同记录联合筛选、任一/全部、排序和
路径上下文检查符合预期。实际原生打开同一test Paper.md、原Canvas及新PDF第15页。
原包10文件在原生打开前后hash相同，登记analysis/Canvas/sidecar哈希吻合；12份正式
provider/fields与registry未变。新单元没有生成空白分析或Canvas冒称完成。

发现新登记缺来源网页时，仅从身份核验的live Zotero父条目补URL/DOI；错误父条目和
不安全URL仍拒绝。核心/导入/链接/只读/reader gate集合125过，实验fixture当前6过。
新增维度草稿后，原生confirm在内置浏览器阻塞；独立新反例先1红，改页面内确认后
并发/草稿6过，相关浏览器/HTTP28过（5既有warning），Ruff/JS/diff过。旧弹框需先
由用户取消，修后内置浏览器回放仍待；正常安装、cmux新实机、整体人工认可均未宣称。
test目录`Scholar Workflow 实验/_工作/knowledge-explorer-vjepa21/测试结果.md`保留详情。

## 2026-10-26：真实 test 论文包读取

已将 test Vault 的既有登记 V-JEPA 2 包接入显式只读 Source/Field 入口，保持原
resource/source身份，一单元一节点，10项全部声明资产；不把其他候选目录加入论文节点。
没有创建 exploration.yml、复制正文或修全局登记。global ownership仍incomplete，
只读投影保留诊断；仅其他Source声明不可读可与本地安全读取分开，已知冲突/本地变更/
不安全文件不豁免。引用/保存拒绝与ZotFlow本地PDF gate继续有效。

独立契约先3红（缺少能力），修复后核心/Field/CLI/HTTP集合123通过（9.59秒）。
既有12浏览器场景11通过/1失败：来源位置新增details使旧技术详情选择器歧义，
仅限定“技术详情”后该场景1通过（4.44秒），不能写成首次12全绿。
内置浏览器实际显示同一正文，3张原图均加载，尺寸1200×490、1200×440、1200×285；
15个包内文件前后hash一致。用户当前看见的是开发只读预览，不是正常安装或人工通过。
归属未闭合前不能保存外围关系，原文PDF/native动作也没有冒称本轮验收。
新增H3待用户确认真实材料类型；不自动把第三方评测替代模型本体或发明正式论文。
本片只读专属与CLI成对参数检查最终6通过（含前述4项），Ruff/JS/diff检查通过。

## 已实现

- 外围单一YAML清单，维度可增改，类型/作用域/单多值/明确排序规则可配置。
- 同一研究记录联合匹配，多值任一/全部；条件、结果、评价、来源和证据共同保存。
- 有依据的工作关系、对称竞争、邻接上下文、保存查询；直角分支图及条件结果表。
- 完整显式资产列表、本地内容预览、受限原生阅读动作；缺失/未核验状态保留。
- 现有Source/Field论文单元只读导入，qualified entity_ref保留，重复引用幂等，人工定位保留。
- CLI和浏览器共享文件核心，revision冲突拒绝；页面轮询重读外部修改，dirty不被覆盖。
- 中文三栏界面；选项逐行输入名称即可自动生成标识，高级设置按需展开，小数值可编辑。
- 可读Obsidian导航导出仅stdout；既有论文正文/Canvas/sidecar/图片无写入路径。
- explore-knowledge Skill、双语说明、G20/INV64及路由/安全/待验收outcome。

## 实际验证

首次集成43项：41通过/2失败，原因是HTTP样本使用了不合契约的空评价；修正为明确待评价。
首次浏览器15项中14通过/1失败，测试错误地按button查找role=tab；修正测试选择器后单项通过。
两次失败保留为开发记录，不改记首次全绿。

完整unit+contract：3619通过，163.63秒，11条既有warnings，包含当时的浏览器联动用例。
其后独立审查指出原生open可能运行.command/.desktop及number默认step不接受小数，均已修正。
新增危险文件/协议、引用遗漏、归属未解析及原生动作边界；最终定向76项通过，7.18秒。
浏览器实际执行了新增维度、纯名称选项、0.81数值、记录编辑、保存重载、误匹配排除及资产预览；
原论文占位文件逐字节不变，全部输入是临时合成根，没有访问正式Vault、Zotero或服务器。
Ruff与新Skill快速校验通过。JS语法检查通过；wheel包含新模块和静态页面资源。
开发预览截图在gitignored build/，只展示合成记录，不是正式研究结果或安装态验收。

## 独立审查与剩余范围

原生打开只允许已知文档/媒体及明确阅读深链；代码类只能安全文本预览或拒绝，不以shell=False
冒称系统关联程序不会执行。保存只提供CAS，不提供历史撤销。图的拓扑分层不设固定维度/层数
配额；循环关系保留并明确提示，尚不宣称任意复杂图的全局最优无交叉布局。

2026-10-26补齐显式资产：现有Field清单可选择附带同Source/resource的来源标识，旧默认响应不变；
导入读取已知Zotero父条目及分页子条目，生成确认归属的条目/PDF/笔记/附件入口。
纯网址不要求伪造本地路径；离线诊断保存于外围清单并在界面/导出呈现，不下载PDF或改写论文。
安全复核先复现8个IDNA回环/正式library身份不一致反例，再修复；该纯helper59项通过。
新增接入用例首次6失败/19通过，其中一项合成fixture调用错误；业务接入修复后25项通过。
随后128通过/1失败是reader隔离fixture未复用正确guard，修正后最终受影响183项全部通过，
8.12秒，包含既有Field清单兼容、CLI、查询、HTTP、浏览器和eval schema。
最后仅补单位显示及审阅截图：浏览器再次1项通过，2.67秒，纸面占位字节保持不变。
排序控件即时限制为单值文字/数值/日期；不强制第五维或任何固定维度数量。
新增维度表单、比较表和分支图三张截图均来自合成浏览器，不是实机业务/人工验收。
本轮新Python及变更模块Ruff/diff通过；新增链接补接后的源码尚未重打wheel，旧开发wheel
不可冒充当前完整产物。误写测试文件名的一次命令未收集或执行测试，已更正并纳入上述183项。

用户已选择先看开发成果、暂不发布安装。未提交/推送/发布/安装，正常安装仍是0.48.0。
尚待：用户后续明确授权本批正常hotfix提交/发布/安装、test单外围对象原生验收与人工评鉴。
网站正文快照、简报到正式入库桥接、定时子agent、自动更新Obsidian导航页仍属后续批次。
第一阶段新对话鲁棒复现与G17整体不因本次开发通过而标完成。

## 最小论文单元边界（2026-10-26）

取消自由新建paper标题卡片，以既有登记Source/Field的整单元选择替代；不要求固定资产数。
paper必须有qualified owner引用；多个维度/条件记录仍汇总为一个命中项和图节点，内部论点、
批注、Canvas和图片保留可寻址入口但不变成独立论文。其他完整资源保留真实类型。
核心保存拒绝偷换身份/类型/局部ID及删减/替换资产；整单元移除只删除外围引用，不删除原件。
界面候选先验证再接纳，错误保留表单、输入、旧草稿与筛选。真实provider→HTTP→importer的
合成链路覆盖整包、多record、重复选择、同名不同Source不合并、未知引用拒绝和文件字节不变。

独立审查发现两个漏洞：界面整包选择仍可被直接save夹带假paper绕过，Field子目录的合法
资产被误判跨根。先用失败用例复现，再修复：新增/变更paper资产须匹配真实引用操作确认的
完整提案；会话级确认不是第二个知识台账。普通CLI init/apply禁止新增paper和改资产，
实际provider import仍可引入完整单元及新增声明资产。Source相对路径先正确映射到探索根，
跨根无URI仍拒绝，不以resolve跟随symlink。资源补链放在共享workflow，CLI/UI共用。

核心保存初跑5失败/1通过；CLI新增引用和资产改写反例分别先红，再修正，最终本文件13通过。
路径映射先2失败/20通过，修正后22通过。HTTP新增引用/片段反例先红，修正后13项含真实provider
契约通过。浏览器早期mock整包响应不能证明服务端授权，已改为注入合成provider并真实请求HTTP，
不手写授权表；两次引用后一个节点/完整两资产保存，paper.md字节不变，1通过、5.01秒。
最终受影响集合254通过、8.54秒，含core/importer/共享资产/整包service/CLI/HTTP/既有Field接口/
eval及模块/manifest契约；本批Python Ruff通过。上述255项不是重新跑完整3619项回归。
最后只读复核发现draft query只做schema校验，未确认paper虽不能保存却能显示预览节点。
新增反例先1失败（200而非400），再让草稿查询复用整单元确认；同时确认合法提案可预览、
片段预览被拒绝。最后HTTP/provider/browser受影响15项通过、11.98秒，Ruff/diff通过。
截图build/knowledge-explorer-unit-selection.png已目视核对，只有合成Source/Field，两资产整包。
既有60099进程/用户页面未刷新，仍是旧源码预览，不宣称新选择器已在该页面运行。

本条写入时正向阅读复核及当前wheel尚待补齐；下方续行已实现并开发验证，不改记旧证据。
从未据此运行真实PDF动作、提交、发布、安装、合并main或改真实论文包；安装版仍0.48.0。

## 原生阅读正向核验续行（2026-10-26）

复用既有ZotFlow窄probe整模块，移至adapters/zotflow.py；旧Hub保留同模块alias，旧私有
helper/monkeypatch仍指向同对象。minimal_child_environment和keys移至共享adapter，函数
AST及key内容不变；ZotFlow仅import归属变化。5个新增ownership检查先红后绿，相关109项
回归通过，不借提取重写原来的阅读或同步逻辑。

新ExplorationReaderGate构造无IO。由GET/assets显式核当前已登记unit/provider、父子归属、
library、LocalAPI locator与本机真实bytes；session snapshot不写YAML/论文包。POST每次
重新核验并比较来源revision、URI/ref/PdfRef及hash；无快照、变更或缺文件拒绝，不用云端
PDF补救。ZotFlow额外核Source唯一所属Vault ID、现有审计版本/启用和live local模式；
不读data.json/SecretStorage。Source重取复用current_unit(ref)现有注册体系，不造新台账。
新gateway/helper先失败用例后修正；29gate+26reference合成用例通过。主线HTTP新增2反例
先红（仅URI被误判可打开、拒绝未接入），接入后71项通过、8.62秒。

新增一项真实HTTP→真实gate→受控opener贯通，仅registry/provider/API为合成替身，确认
完整unit提案保存后直接open403；GET核验后保留page=4启动一次；同路径bytes替换后403，
再次GET保留链接但禁用动作，论文/外围清单revision不改，launch不传入合成Zotero API env。
最终受影响集合380通过、13.18秒、5条既有SWIG warnings；另完整合成浏览器1通过、5.23秒。
浏览器mock一项未通过本地模式的入口，仅验证中文原因/折叠技术详情/无按钮/零open请求，
不冒充真实PDF可用。撤mock后原文件预览、真实HTTP整单元引用/保存继续通过。
build/knowledge-explorer-reader-diagnostic.png已目视核对；60099及实际阅读器未触碰。
Ruff/JS/diff通过；未重跑完整3619项，不将定向证据升级为完整科学支持/安装态/人工验收。

离线开发wheel：build/explorer-reader-wheel.V3B7ja/scholar_workflow-0.49.0-py3-none-any.whl。
150个包内Python/静态文件与当前src逐字节一致，无多项/漏项。它来自未提交开发树，仅用于
包边界检查；不是干净source release、插件payload或正常安装证明。未提交/发布/安装，
正式库原件和已认可论文单元仍不改，完整目标保持未完成。

## 人类编辑一致性续行（2026-10-26）

只读复核确认开表单后的poll可推进版本、旧表单upsert覆盖新summary；save旧回包也可
无条件清掉后续草稿。新增独立浏览器反例首跑open-form：1失败、2未选、5.44秒，真实第二
client CAS改R2后旧表单仍被接纳（未出现预期错误）；没有用伪造model掩盖覆盖窗口。
修正表单打开基线，应用前后读取当前revision，冲突保留输入；保存防重入，期间新表单/
重新读取明确等待；迟到的load/poll/query核基线，查询始终使用当前显示的草稿，筛选变更
立即作废旧查询。没有自动merge、历史版本库或对论文包的新写入能力。

首批三个独立浏览器契约3通过、4.94秒，覆盖旧表单、延迟保存、旧轮询，以及dirty+外部
更新的CAS409；后端R2和原论文结构/字节逐项核对，取消重读后能正常修改新版本。
截图build/knowledge-explorer-edit-conflict.png已目视核对：年份2030和旧说明保留在表单，
红色说明当前输入已保留。原完整browser与HTTP/reader/provider集合18通过、13.69秒。
显式reload与筛选debounce的迟到响应另补2项通过、3.17秒：持有真实reload R2回包后打开
R1表单，释放不替换输入/data/revision；旧查询0命中结果及真实排序冲突错误在新筛选的
debounce期间释放均不落回，之后新条件正确命中r1。两个新文件Ruff/JS/diff通过，
eval schema另10通过。五个独立场景并非重新跑完整回归。仍不访问真实库、
发布安装或刷新60099。上轮开发wheel早于本片JS修改，不能冒充当前源码产物。

当前已知的原生预览缺口仍保留：Markdown正文的native超链接尚绕过资产卡gate，且已认可
ZotFlow页级navigation.pageIndex尚未支持；不能把原生资产卡的合成绿色升级为全路径安全。
下片须保留精确引用，并以原文hash/字面链接绑定的opaque link_id接管点击，方案见
knowledge-explorer-v1.md；本片不删除正文链接或改写已认可论文单元来绕过问题。

## 精确正文引用与单元身份收尾（2026-10-26）

该原生预览缺口已在开发源码关闭，不回写上条历史状态。Markdown同次安全读取返回原文
text/hash与UTF16链接跨度，原标签在原位置显示；native动作使用session link_id，点击先
prepare，再仅ID提交open。两次核原文/声明/精确链接及目标，复用既有reader gate；浏览器
不再生成native href或提交URL/path/attachment key。网页仍普通链接，代码/图片伪链接
不活化；未登记/歧义/不支持/过期入口保留标签及中文原因。源文件与外围YAML字节不变。

实际reference_source_link的ZotFlow navigation.pageIndex先3个兼容反例失败，再修正；
reader57通过，严格拒绝异常/重复JSON键、未知导航、负数/布尔及与page并存的定位。
原始URI逐字保留，不换算成别的页码参数。preview单文件28通过，含围栏结尾错误接受的
两个反例先失败后修正，声明路径/正文块锚点和跨paper唯一身份匹配分别验证。
HTTP新接口先404失败，接入后6通过；包括来源bytes/URI/symlink变化、跨session、伪造
ID/参数与原件守恒。独立浏览器先1失败（缺同点按钮，5.23秒），接入后1通过、2.35秒，
使用实际分析生成器URL；prepare→open顺序、仅ID请求、中文/emoji位置与无native href
均由真实HTTP验证，外部reader与进程创建为替身。截图build/knowledge-explorer-preview-links.png
已目视核对，仅开发合成内容，不是本机原生/人工接受证明。

本次受影响集合399通过、28.62秒、5既有SWIG警告，含7项浏览器场景与旧reader/cmux兼容。
该轮后另完成最小单元审查修正：非paper占同qualified ref时CLI原会混入论文资产，
新增2反例确实失败，最小kind冲突检查后import单文件24通过、0.07秒；最终import/CLI/
HTTP/provider接入集合54通过、8.83秒。不是399+54个独立用例，也不冒称重新完整回归。
Ruff、JS语法、Skill基础校验与diff检查通过。

原子性是组织边界而非最细寻址粒度：论文一个对象，文件/论点/证据属于内部资产，
多维定位/条件结果/评价/关系属于外层记录。完整清单不等于固定资产配额，也不证明全部
分析已经完成。现有身份检查不等于完整包的历史版本归档，不自动跨书目标识合并研究家族。
该边界已写入运行reference，旧论文正文/Canvas/sidecar/图片没有改动。
安装版仍0.48.0；60099旧源码进程未动；本轮未提交/发布/安装/合并main，不接触真实
Vault/Zotero/阅读器。旧开发wheel早于本片，不证明当前打包。原生精确跳转、正常安装和
人工评鉴仍待，整体长期目标不标完成。

## 同一论文正文的可读预览（2026-10-26）

现有预览把折叠原文、粗体和图像语法当普通文本，不能保留已认可正文的阅读方式。
本片只改显示和受控媒体读取；原文/Markdown/Canvas/sidecar/图片/外围清单均不由预览改写。
输入为一篇合成论文单元，两个实际reference_source_quote_lines生成的原文callout，分别
代表作者直接证据与推断依据；另含两段独立解释、共同/变化条件列表、条件结果表、
已声明320×120 PNG及图注、未登记/远程/SVG图、代码伪链接和原始HTML，以及字面code.py。
没有真实文库/API/app、外网、整库扫描、业务分析或论文迁移。

实现保留同点受控原文按钮与零基navigation，折叠标题常显、展开完整上下文和精确加粗；
不以摘要或Canvas简短标签代替正文。支持安全DOM段落/标题/列表/表格、强/斜体和转义，
不执行材料HTML；机器frontmatter/块锚点不成为阅读正文，非Markdown附件原样pre显示。
图片仍是当前单元内部资产。preview.images只提供源位置/图注和session media_id或诊断，
GET /api/preview-media/{id}需本会话认证，不接受任意路径或URL。只解析当前单元精确声明、
根内no-follow文件，绑定原文hash/字面embed/身份/声明与图片hash，响应前复核；改动即拒绝。
16MiB文件界和真实像素预界先于解码，拒远程/native/SVG/HTML/跨论文借图；PNG/JPEG/GIF已
合成验证，WebP通过既有decoder校验才显示，AVIF本轮无法稳妥预界而明确拒绝。不是图数配额。
切换或关闭预览取消旧读取、作废迟到响应并回收blob，不串图、不额外创建论文对象。

红绿证据：独立图片单测先21失败/28旧通过，接口完成并补边界后58通过、0.23秒；
HTTP独立契约首跑因缺images失败，接入后6通过、3.98秒。浏览器先缺真实折叠结构1失败、
5.27秒；接入后折叠/强调/图像均过，在合成斜体图注处1失败、5.16秒。图注是额外合法
Markdown选择而非实际生成器必需格式，选择最小支持em而不删断言，最终1通过、1.98秒。
媒体观察出现Chrome/Playwright Response.body空字节，但真实GET 200/image/png/640字节且
图像完整显示；fetch(blob:)又被既有connect-src拒绝。最终只观察原生createObjectURL输入
并原样调用/返回，对产品实际显示Blob检查640字节与原SHA256；未放宽CSP、伪造响应或省略hash。
code.py检查确认唯一pre与全文逐字相同，不出现details/img/link/button。原所有文件及YAML
逐字守恒，零remote和原生调用；两张viewport截图分别对应真实滚动位置，不冒称一图全滚动。

最终受影响核心/HTTP/eval集合153通过（15.60秒），另8项真实HTTP合成浏览器场景通过
（13.46秒），各5既有SWIG弃用警告；没有把前述重叠小集重复相加，也没重跑完整业务或全集。
Ruff、JS语法、tracked/untracked whitespace检查通过。截图已目视：
build/knowledge-explorer-readable-preview.png（完整摘录/粗体/表格）、
build/knowledge-explorer-readable-preview-figure.png（真实图/图注/失败诊断）。

当前开发wheel为build/explorer-readable-wheel.gkqUhg/scholar_workflow-0.49.0-py3-none-any.whl，
151包内Python/静态文件与本片源码逐字一致，sha256为
3f978e815adb5b472b6b6c91f5666e4aa57421fe7c7bbc76b344e1d3b9737be4。
它只是未提交树的离线开发包，不是确定source release/完整插件payload/正常安装证明。
仍不发布安装、不合并main、不重启60099、不改真实论文包；原生准确显示、人工评鉴、第一阶段
新对话鲁棒复现及整体目标继续未完成，不从本片安全/排版绿色推导科学支持。

## 当前候选闭环收敛（2026-10-26）

一次完整unit/contract合成基线3887通过、182.27秒、11既有警告，明确终态后才改产品。
它覆盖本片修改前的源码，不与后来定向检查相加，也不代替正常安装或科研来源认证。
PATH --version只读返回0.48.0，工作分支codex/hotfix-knowledge-explorer、HEAD ddc1862，
0.49.0尚未提交/发布/安装，60099旧服务未动。

三条并行只读收敛审查各限两项实际问题，随后独立合成反例：

| 问题 | 反例与修正 | 有界验证 |
|---|---|---|
| 读取清单混合版本 | 原地同尺寸改写可出现旧Data+新result；同fd前后stat及实际长度不一致即code5拒绝 | 与短读、导出类型共3红/49绿，修后核心52通过、0.58秒 |
| 文字取值误换论文标题 | text值恰等于work ID时误解析；现在只reference做对象标题解析 | text保持原值、reference仍正常解析 |
| 新记录默认错单元 | 唯一命中B、selected空时曾默认A；现在显式/选中优先，只有已完成当前query唯一命中才建议；多命中/在途查询留空，关系终点人选 | 五场景先5红，修正后5通过；真实保存读回正确归属 |
| 查询旧错留在新结果 | 正常排序错误后合法收窄，旧错仍红；现在只清query拥有的notice，不清CAS/外部修改告警 | 同五场景含实际外部CAS与新query回包，不是只等命中数 |
| 比较表首次PDF打不开 | 无详情预载时直接POST缺snapshot；现在明确ID取资产准备后才open，拒绝分支无进程 | 导航先4红/1绿，修后5通过、5.85秒 |
| 移除后残留旧详情 | 外部合法CAS移除A后数据更新、详情仍旧；现在清失效selected与动作，恢复空态 | poll/reload均过；迟到A资产不污染B的原通过保留 |

没有修改论文身份、归属文件、正文/Canvas/sidecar/图片，也没有新模型/工作区控制或历史档案
框架。源码/测试均在当前工作树，真实API/Store用于浏览器，外部reader/opener均合成替身。

最后受影响347项首跑345通过/2测试助手失败、41.99秒、5既有SWIG警告。两个失败来自新
waitForFunction助手内部eval撞既有CSP，不是产品或新的权限需求。仅把测试助手改为直接
闭包读取同一个matches对象，保留“实际query替换对象”的断言、不放宽CSP；当前上下文
全5项随后通过、7.13秒。未把这次覆盖冒称单次347全绿，先前3887也不是修后全集。
首轮标签locator自身错误未记作产品默认归属反例，修正selector后才取得上述5个真实红例。
最终核心、CLI/HTTP、原浏览器、媒体/原文、并发及eval中受影响能力均有相应绿色证据；
第一阶段四类业务、新对话one-shot、正常安装、原生和人工仍未因此闭合。

前轮build/explorer-readable-wheel.gkqUhg中的开发wheel早于本片core/JS改动，不能再称与
当前源码一致；本片没有重打包或安装。两份stage1文档只澄清当前安装0.48与旧0.47.3论文
证据时点，保留旧认可/partial与四类完成标准，不重跑或迁移业务。

## 可操作的整单元合成演示（2026-10-26）

新增开发专用dev-guide/demos/knowledge_explorer.py及使用说明，不进入runtime-only发布。
脚本只接受显式已存在空目录，拒自身/祖先symlink、非空或缺失目录；生成三篇已引用及一篇
待引用的合成资源，复用真实Store/import/query/HTTP/UI。注入明确的合成清单和全拒绝
NoNativeReader，不读真实host registry、LocalAPI或Obsidian配置。dev Handler只改页头和
浏览器标题标明“合成演示”，安全头、API认证及原生校验未放宽。没有新增产品入口或依赖。

| 独立检查 | 真实观察与结果 |
|---|---|
| 边界/API17项 | 非空/symlink拒绝、3单元4record2edge、D整包proposal/save/重选幂等、未知/重复身份与碎片拒绝、同条条件筛选、正文实际字节/图640×220、只外围保存、所有native拒绝 |
| 真实Chrome1项 | 图与详情、五资产（Canvas明确未生成）、折叠完整摘录/精确粗体/图注、条件结果同行、Saved View、反跨记录拼接、整篇D加入后save、可增加自定义维度、20个native POST拒绝且零进程 |
| 原件守恒 | 四个合成单元的16个实际源文件逐项hash不变；缺失Canvas保留诊断，不制造占位图或真实分析 |
| 原生inline边界 | 独立测试在自己的临时合成正文加入已声明Paper.md链接，prepare/native拒绝；初始演示正文没有原文PDF，不能冒称实际页级点验 |

边界测试先16通过7.40秒、补inline后17通过7.99秒；browser新harness两次exact-label定位
错误修正后1通过2.86秒，不计产品缺陷。随后加常显合成标识与断言，最终两文件合跑18通过、
10.88秒、5既有SWIG警告；Ruff、node --check、git diff --check通过。与之前3887/347等集合
不相加或冒称当前修后完整回归。四张截图均已目视：

- build/knowledge-explorer-demo-relationships.png
- build/knowledge-explorer-demo-conditions-results.png
- build/knowledge-explorer-demo-body.png
- build/knowledge-explorer-demo-body-figure.png

本轮源码演示在一个新动态端口实际启动，并经内置浏览器观察到正常三命中、四record及A
完整资产详情，页标题“合成开发演示 · Scholar”。session token只用于本地浏览器，不写本记录。
演示目录位于忽略build，是可丢弃开发fixture，不是正式test Vault、安装包或知识迁移产物。
因补页头，终止过本轮未交付的首个演示进程，再启动当前候选；旧60099未刷新/停止。
用户可以在当前新标签内操作，人工评鉴尚未确认。没有提交、发布、安装、合并main、真实
Vault/Zotero/服务器读写或论文分析/Canvas改写；第一阶段完整模范复现和新对话oneshot、
正常安装/原生工具验收及整体目标继续未完成。

## 候选打包边界与隔离执行（2026-10-26）

本片只做当前候选的交付前开发验证，没有运行会切分支/commit的make-release，没有pip
安装、正常更新、发布推送或服务切换。PATH实际读取仍0.48.0；source HEAD仍ddc1862，当前
0.49候选尚未提交。当前wheel来自这一未提交树，不把HEAD当成其确定源码提交。

离线构建：build/explorer-current-wheel.A8dHfn/scholar_workflow-0.49.0-py3-none-any.whl；
sha256为ce8e65ee194c0f46cfaa9ebb1a262d5d282645cb12d6140c6abd325cad42ba8c。
包内Python/HTML/CSS/JS完整集合与当前src逐字相同，METADATA与source版本一致；无越界/
symlink/dev/演示文件。此前的wheel仍只保留各自历史证据，不能代替本次产物。

开发runtime staging：build/explorer-runtime-preview.706C86/runtime。按现有make-release
的RUNTIME_PATHS，对Git可见tracked/untracked候选做机械复制，共328文件；保留权限/时间后
checksum+权限dry-run零差异，无symlink、实际个人路径/代理或开发演示端口命中。包含新Skill
三文档、canonical reference、新模块与完整静态资源，不包含根AGENT/CLAUDE、planning、
dev-guide/demos、tests、evals或build。不是git archive的正式发布提交；未提交内容仍会被
既有release dirty gate正确阻断，后续授权提交后才能进入真正发布。

独立只读审查确认111个PLUGIN_ROOT路径存在；135本地Markdown链接中仅4个既有实验示例
的运行后report/metrics目标不存在，符合生成说明，未当作漏包或删除。整单元边界、已认可
详尽正文/简短五分支Canvas/折叠原文/证据加粗/图片/对齐无交叉均在runtime Skill/reference，
不需开发AGENT或个人模范目录。文件可达不证明新Codex宿主实际变量替换/加载，更不证明
新对话one-shot科研交付。

发现Claude marketplace还宣传旧Hub/Codex控制面：新描述一致性反例先1失败（0.05秒），
只修一行与两plugin及Codex marketplace一致，后1通过（0.04秒）。未改变hooks、安装策略、
Skill路由或新版本号。CHANGELOG同步该文案修正。

新增tests/contract/test_explorer_distribution.py包含：

- runtime范围、必需文件、开发层排除、四description/版本与新Skill必读路径一致性。
- 指定确切wheel时，校验字节/版本后解包到pytest隔离根；子进程python -I移除editable src，
  所有实际加载的scholar_workflow模块__file__都在解包目录。CLI帮助、真实Store/HTTP查询、
  三静态文件精确字节、正文预览、asset禁用/native403及源文件/状态守恒通过。配置、个人
  registry、Local API、native进程均0调用；socket只准自己的动态loopback端口。无wheel时
  本项明确skip，不冒充完整绿色。

隔离助手首轮暴露python -I仍有site editable .pth与Mac urllib读取系统代理的环境行为：
来源路径检查/连接拒绝器均先拒绝，未触及实际外网。只修测试路径过滤和显式空ProxyHandler，
没有为通过测试改产品、削弱socket guard或重设HOME/CODEX_HOME。最终两项2通过0.89秒；
主代理带精确wheel与既有版本契约独立合跑3通过0.96秒，Ruff/diff通过。不是新的完整回归、
安装态或科学支持证据，不与之前18/3887等集累加。

原有论文包、正式Vault/Zotero/服务器及main未动；62454实际合成演示进程仍存活，内置标签
已保留，旧60099未刷新/停止。演示人工评鉴、正常发布安装、新宿主加载/one-shot与整体目标
继续未完成，不从打包绿色推导完成。

## 当前修后完整源码回归（2026-10-26）

输入为tests/unit与tests/contract各自合成fixture，显式设置已安装Chrome/Node和当前确切
wheel，不进行真实论文分析、Vault/Zotero/服务器业务。只启动一次pytest并持续观察同一
session到明确exit0；未因观察等待而重启/叠加运行。原有待人工与未实现outcomes不改状态。

最终：**3920 passed，11 warnings，209.35秒**。当前新增的整单元/过滤/浏览器/并发编辑/
精确原文/图片/打包检查与历史项目/实验/批次/安全兼容均包含在本次通过集合内，没有skip
或新的产品失败。不把早先3887基线和其他定向数字相加，也不把当前完整源码绿色变成正常
安装、科学支持或任意新对话one-shot证据。警告仍为既有PyMuPDF/SWIG及多线程fork弃用，
原始诊断保留；不以扩展退役Hub产品范围来处理历史兼容。

没有修改论文正文/Canvas/sidecar/图片、真实库、安装、服务或main；runtime代码未再变化，
上一片wheel/staging的字节检查仍对应当前候选。本次只有开发结果与handoff记录更新。

并行只读核对第一阶段：

| 对象 | 尚欠的真实范围 |
|---|---|
| 模范Vault/论文 | 既有正文与Canvas认可保留；独立新宿主一次生成仍partial，完整源支持与所选归属/原生/人工分别证明 |
| 项目/实验 | 保留已有典范及有限安装证据；统一可编辑参数入口、选择性导出/传输、及时自动回传仍未实现；不在本批顺手扩展 |
| 外部交互 | 有限ZotFlow/cmux/VS Code证据不能证明全部当前新入口，准确动作/便利性仍需对应原生和人工验收 |
| 当前探索 | 合成可操作演示与源码回归已交付；下一项是用户评鉴单元边界、编辑操作和阅读便利性，正式发布安装/test单对象另需授权 |

本轮已发出自包含的合成演示评鉴问题：A资料同单元、维度不复制论文、条件结果同行、D整包
加入只增一节点。其答案不自动授权发布安装或真实资料写入。当前批次不继续堆叠开发检查/
加功能来替代反馈；网站存档/入库桥接/调度等后续能力未冒称完成。长期目标保持未完成。
