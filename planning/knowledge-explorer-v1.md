# 知识探索第一批：实施与验证契约

## 目标和范围

在原有论文单元外建立可扩展维度、条件化研究关系、带依据的工作间关系、完整资产引用和保存查询。
同一资料保持唯一入口；不修改任何论文正文、Canvas、sidecar、图片或原有模板。
cmux 是浏览器窗口打开位置，普通浏览器也可消费相同页面。知识能力不依赖 workspace 绑定。

## 第一批公共接口

核心模块 knowledge/exploration.py：ExplorationStore(root).load() 返回
{revision, data}；save(data, expected_revision=...) 返回相同形状，初次写入预期 revision 为 null。
唯一受管可写文件 .scholar-workflow/exploration.yml。strict schema_version=1；顶层
dimensions/works/records/edges/views 为列表，不接受未知顶层字段。

- dimension: id,label,kind(enum/reference/text/number/date),multiple,scope(work/record),
  values([{id,label,parent_id?}]),sortable,unit?；可选 description。新增通常只改变定义。
- work: id,title,kind(paper/webpage/report/book/other),year?,summary?,attributes,
  assets([{id,label,kind,uri}])；uri 为 root 内相对文件或 https/http/obsidian/zotero 原生地址。
  可选entity_ref和asset_diagnostics保留明确来源身份及未核实资产说明。
  不猜测同名归属，不写入被引用的论文包。
- record: id,work_id,dimensions,conditions(任意字符串键值),result,evidence(资产id列表),
  assessment,origin(author/independent/local/analysis)。一条记录是一组实际联合条件。
- edge: id,from_id,to_id,kind,label,evidence(资产id列表),explanation；支持
  extends/borrows/competes/fuses/context，竞争为对称显示，其他关系的方向明确。
- view: id,title,query；query 为过滤/组织状态，不保存第二份匹配结果。

query(data, selection) 返回 {works,records,edges,context_work_ids}。selection 支持
filters({dimension:{mode:any/all,values:[]}})、text、sort_by(title/year/显式可排序维度)、
descending、include_context。先在同一 record 上匹配记录维度，再汇总工作；work维度同其对应
work共同限定。缺值不冒充零值。同名标签不替代稳定id。上下文节点不计作命中。
assets(root,data,work_id) 返回完整资产及可用性；本地相对路径拒绝越界/符号链接，保留缺失诊断。
render_markdown(root,data) 生成可独立阅读的定位/资产/条件与结果/关系导航，不改变原论文。

薄 adapter adapters/knowledge_explorer.py：本机动态端口、会话 token、严格 Host/Origin；
GET /api/state、POST /api/query、POST /api/save、GET /api/assets/{work_id}。
静态页面在 adapters/explorer_static，动态 DOM 用 textContent；不执行材料中的 HTML。
保存采用 revision 比较，冲突返回409；文件外部编辑后请求重读。POST 只写知识外围清单。
只读本地资产入口需要按明确asset id解析，不接受浏览器路径。CLI统一入口为
knowledge explore（启动界面）、exploration-init/query/export（无 Hub 前提）。

## 开发测试（先声明后执行）

输入仅测试进程创建的合成根：两项工作、一项网页材料、两条不同条件记录、带分支关系、
本地正文/Canvas/图片占位字节。测试不使用正式Vault、Zotero、服务器、模型或网络来源。
步骤：校验/保存/读回；添加自定义维度并筛选（不是要求必须有第五维）；验证 B1+T2 不跨记录误命中；any/all；
条件结果与证据读回；双入口资产；外部修改后重读与旧revision拒绝；路径/协议/脚本注入。
通过标准：查询语义正确、原文件字节全不变、冲突不会覆盖、完整资产不静默遗漏；
定向 CLI/HTTP 测试通过，界面可操作性待正常安装后独立人工评鉴。
产物：代码、定向回归结果和使用说明；不把开发服务当正常安装或把合成图当科研结论。

## 后续批次

来源动态到本界面的桥接、正文快照及已选条目的显式正式入库仍要复用既有research/ingest权威；
真实来源、定时调度、安装和实际业务验收分别取证，不让本批界面产生虚假完成状态。

## 人工编辑并发补充验证

输入为一个合成知识对象及原文占位文件，真实HTTP/ExplorationStore，测试第二client做
外部CAS修改。浏览器用受控时钟触发既有5秒轮询，延迟真实请求响应；不编造新版状态。
检查：开表单后的外部新版本不被旧字段覆盖；冲突保留表单输入；取消并重读后能正常
编辑新版本；save在途不重入也不丢后续状态；旧state响应不倒退已保存版本；既有dirty
草稿遇外部变化仍用旧revision保存并获得409，不自动推进基线。原论文文件字节不变。
截图build/knowledge-explorer-edit-conflict.png仅示合成冲突提示，不替代安装/人工验收。

## 正文原生链接接管：接口与独立验证

原Markdown预览直接渲染native超链接，可绕过资产卡的正向reader gate；该问题已由下述
接口替代。已认可正文的ZotFlow定位使用navigation={pageIndex:非负物理页索引}，
不能只接受page，也不能删掉已有原文入口来冒称完成。同一次原文读取生成text/hash与
同点opaque link_id，点击仅提交该ID；服务端重读原文/字面链接并核
目标单元和reader，保留page/annotation/受限navigation。禁止浏览器任意URL/路径、
原生<a>旁路、跨单元猜配或静默改换版本。仅对点击的链接做probe，不批量启动阅读器。
本地正文反链仍须对应明确已登记资产并保留锚点；未知/歧义目标可见诊断，不伪造归属。
接口已在开发树实现：GET /api/preview/{work}/{asset}返回text/document_revision及UTF16
链接跨度；GET /api/reading-link/{link_id}准备；POST /api/open-link仅接收link_id。
合成输入包括实际reference_source_link生成的navigation、中文/emoji、正文/代码/图片
中的链接、已声明块锚点和同名歧义。检查原文与YAML字节、同点标签、精确URI及无native
href旁路，并覆盖原文/声明/symlink变更、跨session和参数注入。结果单独记录；
实际安装、原生窗口显示及准确跳转仍需各自证据，不能由开发检查替代。
