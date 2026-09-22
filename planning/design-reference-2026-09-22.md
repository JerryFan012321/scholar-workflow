# 简洁前端与图表模板参考库

检索日期：2026-09-22。范围：前端操作界面、思维导图、知识关系图、流程与架构图、网页数据图表、科研绘图。审美取向：**前端以信息和操作为中心，尽量减少装饰**。

本文收集 **80 个资源入口**，并从中整理 **24 个具体模板与示例切入点**。80 个入口包含成品模板、组件库、图表示例、真实产品参考和设计资料，不能等同为 80 套可直接安装的完整模板。同一生态下用途不同的入口分开列出，例如 shadcn 的页面、任务表和图表。

资源事实以链接对应的官方页面、作者页面、官方示例或源仓库为依据；“适合借鉴什么”“建议如何简化”是本次选型判断。已做网页与仓库检索，未逐个安装运行，也未完成所有页面的视觉验收。登录限制、动态页面和抓取失败单独说明；不把这些情况写成资源失效。免费浏览、开源代码、可商用素材和完整免费产品是不同概念，具体模板仍以其自身说明为准。

## 阅读导航

| 章节 | 内容 | 数量 |
|---|---|---:|
| [1. 前端模板与设计系统](#frontend) | 应用布局、表格、表单、侧栏、轻量 CSS | 20 |
| [2. 产品界面与交互参考](#products) | 真实工作台、知识库、界面与操作流程图库 | 6 |
| [3. 思维导图](#mindmaps) | Markdown 导图、可编辑导图、模板市场 | 6 |
| [4. 关系图、流程图与画布](#diagrams) | 图编辑器、自动布局、知识网络、白板 | 12 |
| [5. 网页数据图表](#web-charts) | 交互图表、统计图、时序图和组合视图 | 15 |
| [6. 科研与报告绘图](#scientific) | Python/R 图库、绘图样式、论文组图 | 9 |
| [7. 无代码图表工具](#no-code) | 可视化编辑与模板 | 3 |
| [8. 配色、图标与选图资料](#foundations) | 克制的视觉基础与图表选型 | 9 |

后续章节包括：[24 个具体切入点](#recipes)、[图表与任务的对应关系](#chart-selection)、[少装饰的设计参数建议](#design-rules)、[针对当前 Hub 的建议](#hub)、[状态与访问核验说明](#verification)。

<a id="frontend"></a>
## 1. 前端模板与设计系统：20 个

这里优先收录 Application UI。营销首页的巨大标题、光晕背景、滚动动画，与日常操作工作台的需求不同；同一网站若同时提供营销区块和应用区块，重点看后者。

| 编号 / 资源 | 资源形态与技术栈 | 可以借鉴或复用的部分 | 使用边界与简化方向 |
|---|---|---|---|
| U01 [shadcn/ui Blocks](https://ui.shadcn.com/blocks) | 开源区块；React、Tailwind；预览与代码同页 | `dashboard-01`、可折叠侧栏、分组导航、数据表；中性色、细边框和一致的控件高度 | 是代码区块，需要接数据和业务逻辑；只需要资源目录时，可省略示例中的 KPI 卡片 |
| U02 [shadcn Tasks](https://ui.shadcn.com/examples/tasks) | 可操作的任务表范例；React | 搜索、状态与优先级过滤、行选择、行菜单；适合论文表、任务表和实验记录 | 示例数据不代表真实后台能力；状态标签保留必要差异，避免每列都有彩色徽标 |
| U03 [Shadcn Admin](https://github.com/satnaing/shadcn-admin) | 多页面管理界面；React、Vite；仓库标注 MIT | 应用侧栏、全局搜索、任务与用户页面、响应式布局；适合研究完整页面之间的关系 | 作者明确说明它并非完整 starter；不能把演示登录、页面和真实业务服务混为一谈 |
| U04 [Tremor Blocks](https://blocks.tremor.so/blocks) | 数据应用区块；React、Tailwind | 图表与表格组合、图例、筛选器、表单、统计布局；数据对齐比装饰更突出 | 当前首页宣布 Blocks 与 Templates 已开源；部分页面仍保留旧的 Premium 文案，获取时看具体仓库 |
| U05 [Tremor Templates](https://blocks.tremor.so/templates) | 多页面模板；React/Next.js 等，具体版本随模板而异 | `Overview`、`Dashboard`：概览、表格过滤、设置、通知面板；适合实验监控工作台 | 模板间依赖版本不同；可拆用一页，不必继承整套产品结构 |
| U06 [Tabler](https://tabler.io/admin-template) · [实时预览](https://preview.tabler.io/) | HTML/Bootstrap 管理界面；开源版与付费产品并存 | 文件、表格、表单、分页、布局与状态显示；适合传统 HTML 项目借鉴 | 相比当前纯 CSS，完整引入 Bootstrap 仍有成本；页面装饰和统计卡片可以减掉 |
| U07 [HyperUI](https://www.hyperui.dev/) | 免费开源 Tailwind HTML 片段 | Application 分类中的表格、详情列表、按钮组、分隔线、导航；便于拆分复用 | 不等于完整交互应用；避开 Neobrutalism 等与本次偏好不符的风格分支 |
| U08 [Preline Application UI](https://preline.co/blocks/) | Tailwind 区块与模板；免费和付费混合 | Application UI 的侧栏、表格、弹窗、表单和多栏布局；覆盖面广 | 区块依赖与交互脚本需要一并看；采用简单配色，省略宣传插画与装饰背景 |
| U09 [Flowbite](https://github.com/themesberg/flowbite) · [Blocks](https://flowbite.com/blocks/) | Tailwind 组件与区块；核心开源，另有付费内容 | 表格筛选、CRUD 表单、分页、模态框、导航；仓库还列有 minimal/mono 主题入口 | Blocks 页面本次抓取返回 403；核心信息通过官方仓库核验。不能把全部 Pro 内容视为免费 |
| U10 [Tailwind Plus Application UI](https://tailwindcss.com/plus/ui-blocks/application-ui) | 商业区块；包含应用布局、列表、表单等 | Sidebar Layouts、Multi-Column Layouts、Stacked Lists、Tables、Description Lists；适合信息密集的工作界面 | 本次访问跳转登录。HTML 交互片段也可能依赖其 Elements 库；不是复制 HTML 就获得全部交互 |
| U11 [Catalyst](https://tailwindcss.com/blog/introducing-catalyst) | Tailwind Plus 的 React UI kit | 精简应用外壳、表单、表格、按钮与导航；适合借鉴统一的字号、间距和控件层级 | 商业资源；React 依赖。当前 Hub 可参考外观参数，直接采用需要技术栈调整 |
| U12 [Mantine UI](https://ui.mantine.dev/) | 官方及社区组件范例；React；页面标注 MIT | Navbars、Headers、Tables、Inputs、Application Cards；组合成后台较方便 | 需要 Mantine；部分演示配色较强，可统一成灰阶与单一强调色 |
| U13 [Nuxt UI Templates](https://ui.nuxt.com/templates) | Nuxt/Vue 模板入口；各项提供预览和仓库入口 | Dashboard、Editor、Calendar 等完整场景；适合多栏布局、收件箱式信息浏览 | 属于 Vue/Nuxt 路线；各模板独立核对依赖与许可证，不能无成本接入原生 JS |
| U14 [Radix Themes](https://www.radix-ui.com/) | 带主题的 React 组件系统 | 中性色阶、表单、菜单、弹窗、表格及状态层级；适合建立一致的基础界面 | 是设计系统与组件，不是完整业务模板；需要自己组织页面和内容 |
| U15 [Vercel Geist](https://vercel.com/geist/introduction) | 公开设计系统参考 | 文字层级、状态、表格、细边框、黑白灰界面；适合工具型产品的视觉参考 | 不把它当作随取随用的完整后台模板；组件可用方式需逐项核对 |
| U16 [GitHub Primer](https://primer.style/) | 设计规范与组件生态 | 高频操作、密集列表、筛选、导航、详情面板；适合工程工具和研究资源管理 | GitHub 的业务结构不可照搬；可以复用信息组织原则和控件交互 |
| U17 [IBM Carbon](https://carbondesignsystem.com/) | 开源企业设计系统 | 高密度表格、筛选、工具栏、表单、状态反馈；适合复杂专业工具 | 视觉更严整，完整采用会带入较多系统约定；只借鉴必要的布局与行为即可 |
| U18 [Ant Design Pro](https://pro.ant.design/) | React 管理界面方案；入口转向官方演示 | 搜索表单、复杂表格、详情页、步骤表单、结果页；中文业务场景可参考 | 多层面板与信息密度较高，需要主动删减；不必把每个模块都包成卡片 |
| U19 [Pico CSS](https://picocss.com/) | 面向语义 HTML 的轻量 CSS 框架 | 原生表单、按钮、表格和对话框的统一外观；适合小型本地工具 | 默认留白与字号需要按密集工作台调整；不提供完整文件管理、图编辑等业务能力 |
| U20 [Simple.css](https://simplecss.org/) | 以少量或无 class 为主的 CSS | 文档阅读页、设置说明、简单表格与表单；适合正文占主导的界面 | 面向简单页面；复杂多栏后台需要额外布局，适合作为“减少样式复杂度”的参照 |

<a id="products"></a>
## 2. 真实产品与交互参考：6 个

本组用于观察布局和操作流程，不意味着能直接复制产品源码或图片。

| 编号 / 资源 | 形态 | 观察重点 | 边界 |
|---|---|---|---|
| P01 [Linear 产品功能](https://linear.app/features) | 真实项目管理产品 | 列表的行密度、分组、筛选、详情展开、命令入口；适合项目和任务管理 | 重点研究产品截图里的操作界面；其营销网站的光效和宣传构图不属于本次目标 |
| P02 [Outline](https://www.getoutline.com/) | 知识库产品与公开预览 | 左侧文档树、正文阅读、目录、搜索、编辑入口；适合研究知识库 | 产品有托管与自行部署方式；本清单把它作为阅读体验参考，未审核其全部部署许可 |
| P03 [Plane](https://plane.so/) | 项目管理产品 | 项目、任务列表、看板、详情侧栏和页面之间的切换；适合 Operations | 不需要把项目管理产品的全部菜单移入 Hub；按实际工作任务取用 |
| P04 [Mobbin](https://mobbin.com/) | 真实产品截图与流程资料库 | 按 Web、Dashboard、Search、Table、Settings、Empty State 等寻找具体操作页面 | 不是代码模板库；完整访问范围取决于账户方案。适合先定模式再找实现 |
| P05 [Refero](https://refero.design/) | UI/UX 参考图库 | 适合作为工作台、设置页、列表和详情页的补充检索入口 | 本次仅取得站点标题，未取得可读图库正文；覆盖量和付费范围未核实，不据此推荐购买 |
| P06 [Page Flows](https://pageflows.com/web/flows/sorting-and-filtering/?page=2) | 操作流程与页面参考 | 搜索、排序、筛选、创建、编辑等连续动作；补充静态截图看不到的交互过程 | 部分内容需要订阅；首页抓取失败，已通过官方 Sorting and Filtering 分类核验用途 |

检索词建议：`web app table filtering`、`split view document reader`、`command menu`、`settings form`、`empty state`、`file manager`、`research dashboard`。先用任务名找界面，能减少营销首页和装饰性效果图的干扰。

<a id="mindmaps"></a>
## 3. 思维导图：6 个

思维导图通常表达一个中心主题向下展开的层次。需要大量跨分支关系时，应考虑概念图或关系网络；需要前后顺序时，则更适合流程图。

| 编号 / 资源 | 输入与产物 | 模板与可借鉴部分 | 边界与少装饰用法 |
|---|---|---|---|
| M01 [Markmap](https://markmap.js.org/) · [在线编辑器](https://markmap.js.org/repl) | Markdown 标题与列表 → 可缩放、可折叠的导图 | 文献大纲、研究问题树、方法分解、学习目录；文字与细连线为主 | 更适合由文字层级生成视图；不是任意自由摆放的图编辑器。控制分支颜色，保留正文链接 |
| M02 [Mermaid Mindmap](https://mermaid.js.org/syntax/mindmap.html) | 文本语法 → 思维导图 | 小型主题树、文档内总览；能与 Markdown 一起维护 | 宿主支持的 Mermaid 版本可能不同；减少节点形状混用和无语义的多色分支 |
| M03 [Xmind 模板市场](https://templates.xmind.com/) | 现成思维导图模板 → 在 Xmind 中继续编辑 | 项目规划、知识整理、概念图、鱼骨图、逻辑结构；能快速查看布局范例 | 官方与社区模板并存，免费和付费混合；“模板可下载”不等于可复制为自己的前端组件 |
| M04 [SimpleMindMap / 思绪](https://github.com/wanglin2/mind-map/blob/main/README.md) | JavaScript 库与 Web 导图项目；另有客户端产品 | 可编辑节点、主题、布局、导入导出等能力值得参考；库不依赖前端框架 | 当前 README 明确：库/Web 进入低维护状态，客户端与插件闭源。完整客户端功能不能当作开源库能力承诺 |
| M05 [jsMind](https://github.com/hizzgdev/jsmind) | JavaScript 思维导图库 | 简单中心主题与分支、基础节点操作；适合研究低复杂度导图实现 | 视觉需要统一重做；采用白底、深色文字、细线，避免默认色块过强 |
| M06 [React Flow Mind Map 教程](https://reactflow.dev/learn/tutorials/mind-map-app-with-react-flow) | React 节点与连线模型 → 可交互导图应用 | 增加节点、编辑标签、连接和拖拽；适合真正要操作节点的任务 | 教程是开发起点；保存、历史、冲突处理和业务语义仍需实现。并非导入即成品 |

**选择依据：**大纲是主数据时，文本生成导图的维护成本低；用户直接编辑节点与连线时，需要图编辑器；只想做一张汇报图时，现成 Xmind 模板更省开发。

<a id="diagrams"></a>
## 4. 关系图、流程图、架构图与画布：12 个

| 编号 / 资源 | 形态与技术 | 适合的图与可复用内容 | 边界与简化方向 |
|---|---|---|---|
| G01 [Mermaid Flowchart](https://mermaid.js.org/syntax/flowchart.html) | 文本定义流程 | 工作流、模块依赖、资源流向；文档与图可以一起版本管理 | 跨线很多时可读性下降；拆成几个主题明确的小图，使用方向一致的连线 |
| G02 [React Flow Examples](https://reactflow.dev/examples) | React 图编辑器示例 | 自定义节点、分组、连接、布局、交互；适合可操作的研究流程和分析树 | 核心库、普通示例和 Pro 内容分别看；节点编辑与自动布局属于不同能力 |
| G03 [AntV G6 Examples](https://g6.antv.antgroup.com/examples) | JavaScript 图可视化引擎 | 思维导图、缩进树、组织结构、鱼骨图、关系网络；官网中文示例丰富 | 选择 tree/mindmap/compact 等结构化布局；力导向动画不是所有知识图的合适默认 |
| G04 [Graphviz Gallery](https://graphviz.org/gallery/) | DOT 文本与自动布局 | 有向无环图、模块依赖、聚类子图、技术谱系、树形结构 | 默认外观偏技术文档；可统一字体、节点间距、灰色边框，再保留少量重点色 |
| G05 [D2](https://d2lang.com/) | 声明式图语言 | 系统结构、组件关系、分组容器；有主题与文本布局能力 | 引擎与布局选项需按项目核对；选普通主题即可，不必开启手绘或动画 |
| G06 [Cytoscape.js](https://js.cytoscape.org/) | JavaScript 网络图与图分析库 | 论文引用关系、知识实体网络、局部邻域高亮、搜索与过滤 | 图规模、布局与交互需求决定成本；避免把全库所有节点一次铺满 |
| G07 [Sigma.js](https://www.sigmajs.org/) | WebGL 网络图渲染；与图数据结构生态配合 | 较大规模节点/边网络、社区分布、关系探索 | 主要解决网络可视化，不是流程编辑器；长文本节点和阅读型树图需另做评估 |
| G08 [draw.io 模板](https://www.drawio.com/docs/manual/templates/) · [扩展模板说明](https://www.drawio.com/docs/diagram-types/template-diagrams-on-github/) | 可视化编辑器与 `.drawio` 模板 | 流程、泳道、UML、ER、架构与网络图；适合手工精修可编辑文件 | 模板有大量行业图标；研究流程常用矩形、文本和箭头就足够 |
| G09 [Excalidraw](https://excalidraw.com/) | 白板与手绘风格图形工具 | 讨论草图、概念关系、方法流程的初稿；适合边讨论边改 | 手绘线条本身有风格，未必适合所有正式结果图；需要严整排版时可换规整图形或其他工具 |
| G10 [tldraw](https://tldraw.dev/) · [许可与定价](https://tldraw.dev/pricing) | React 无限画布 SDK 与示例 | 白板、卡片、连接线、内容画布；适合深度定制图形工作区 | 当前生产使用有商业 SDK 许可要求，也提供试用及 hobby 申请；不能按“无条件免费 SDK”选型 |
| G11 [JSON Canvas](https://jsoncanvas.org/) | 开放的无限画布文件格式 | 保存文本/文件节点、分组与边；适合可移植画布数据和已有 Canvas 资产 | 是格式，不是现成渲染器、自动布局库或 UI 模板；渲染与编辑仍需实现 |
| G12 [ELK.js](https://github.com/kieler/elkjs) | 自动布局引擎 | 分层布局、端口与复杂边路由；可与自己的渲染器或图编辑器组合 | 是布局基础件，不负责完整交互和审美；节点尺寸与标签测量仍要由应用提供 |

**需要分清的四层：**图的文件格式、自动布局、视觉渲染、用户编辑。JSON Canvas、ELK、Sigma 与 React Flow 分别侧重不同层面，不能因为都能“做图”就互相替代。

<a id="web-charts"></a>
## 5. 网页数据图表：15 个

| 编号 / 资源 | 技术与示例形态 | 适合的内容 | 简洁使用方式与边界 |
|---|---|---|---|
| C01 [Apache ECharts Examples](https://echarts.apache.org/examples/en/index.html) | JavaScript 图表示例与配置；可用于原生页面 | 折线、条形、散点、热图、树图、桑基、缩放和联动；覆盖面广 | 自定义统一主题，减轻网格和边框；官网也有复杂炫技示例，只选任务需要的图型。页面依赖 JS |
| C02 [shadcn Charts](https://ui.shadcn.com/charts) | React + Recharts；预览与复制代码 | 标准折线、面积、条形、图例和 tooltip；适合与 shadcn 界面保持一致 | 是图表组件，不负责业务数据管道；可移除重复的外层卡片标题和装饰性趋势文案 |
| C03 [Recharts 示例](https://recharts.github.io/en-US/examples/SimpleLineChart/) | React 图表及源码 | 常见业务曲线、柱状图、散点、组合图；组件方式组合 | 默认颜色和网格需要定制；当前官方示例链接用 `recharts.github.io`，旧入口本次返回 404 |
| C04 [Tremor Components](https://www.tremor.so/) | React、Tailwind、Recharts 生态 | 折线、条形、进度式数据展示、分类对比与数据控件 | 偏数据应用；信息没有自然“增长/下降”含义时，不套用营销指标卡的红绿箭头 |
| C05 [Observable Plot Gallery](https://observablehq.com/@observablehq/plot-gallery) · [官方介绍](https://observablehq.com/framework/lib/plot) | JavaScript 统计可视化与可编辑示例 | 点图、分面、分布、密度、回归和数据探索；适合分析型视图 | 与 D3 有关联但抽象层更高；不等于所有 Observable 服务都免费，也不是节点编辑器 |
| C06 [Vega-Lite Gallery](https://vega.github.io/vega-lite/examples/) | JSON 图形规格、在线编辑器 | 置信区间、分面、小多图、选择高亮、刷选和关联视图 | 图表定义适合机器生成与复现；需要约束规格与数据来源，不能把任意图配置直接当可信内容 |
| C07 [Vega Gallery](https://vega.github.io/vega/examples/) | 更底层的声明式可视化规格 | 更复杂的交互、树图、网络、时间线及自定义图形 | 表达力较强，规格也更长；普通统计图可先考虑 Vega-Lite |
| C08 [D3](https://d3js.org/) | 底层 JavaScript 可视化工具与示例入口 | 自定义坐标、布局、层次图、特别的数据编码与交互 | 设计自由度高，但要自己处理布局、响应式与可访问性；不应为了普通条形图增加开发量 |
| C09 [AntV G2 Examples](https://g2.antv.antgroup.com/examples) | JavaScript 图形语法与大量中文示例 | 分组/堆叠条形、点线、区间、分布、多视图；适合统计与业务图 | 与 G6 分工不同：G2 偏数据图，G6 偏关系图；统一坐标轴与主题即可获得克制外观 |
| C10 [Chart.js Samples](https://www.chartjs.org/docs/latest/samples/) | Canvas 图表；JavaScript | 少量常见图、基础交互、轻量监控页面 | 复杂关系图不是主场；Canvas 图还需提供可读数据或摘要，不能只依赖鼠标悬浮 |
| C11 [Nivo](https://nivo.rocks/) | React + D3 的图表组件与配置演示 | 常见统计图、热图、日历、桑基、树图；可探索图表参数 | 示例默认较多彩；调主题与网格后再嵌入，不直接继承所有默认装饰 |
| C12 [visx](https://visx.airbnb.tech/) | React 可视化基础组件 | 需要精细布局和交互的自定义统计图；适合建立自己的图表体系 | 比现成图表库更需要工程投入；旧 `airbnb.io/visx/gallery` 已跳转新站 |
| C13 [Unovis Gallery](https://unovis.dev/gallery/) | 模块化可视化组件与多框架支持 | XY 图、桑基、网络等组合；适合多种图型共用样式 | 各框架接口与图型支持分别核对；不是无限画布编辑器 |
| C14 [uPlot](https://github.com/leeoniya/uPlot) | Canvas 时序图；公开示例与仓库 | 高频训练曲线、长时间序列、多个指标的同步观察 | 重点在时序绘图效率；复杂分类统计、图编辑和完整 dashboard 需要其他组件 |
| C15 [Plotly.js](https://plotly.com/javascript/) | 开源 JavaScript 科学与交互图表 | 科学散点、统计、3D、等高线与探索图；适合交互分析 | 图型全面但依赖规模与默认工具栏需要评估；普通结果图可去掉多余边框和按钮 |

<a id="scientific"></a>
## 6. 科研与报告绘图：9 个

这组重点是可复现、字体与轴标可读、可导出图形以及多图一致性。网页上的“看起来漂亮”不能代替论文中的误差表达、单位与数据说明。

| 编号 / 资源 | 形态 | 具体可用内容 | 使用边界 |
|---|---|---|---|
| S01 [Matplotlib Gallery](https://matplotlib.org/stable/gallery/index.html) | Python 官方完整示例 | 误差条、曲线、直方图、箱线图、子图、标注、色条和矢量输出 | 用作可执行起点；很多示例为演示 API 而设计，需要统一成自己的版式 |
| S02 [Seaborn Gallery](https://seaborn.pydata.org/examples/index.html) | Python 统计图示例 | 误差带、分组箱线、分布、小提琴、散点矩阵、热图、分面 | 同时检查统计聚合行为；美化主题不会自动保证统计口径正确 |
| S03 [SciencePlots](https://github.com/garrettj403/SciencePlots) | Matplotlib 样式集合 | `science`、`ieee`、`nature`、色彩循环与相关示例 | 样式不代表期刊当前全部规范。部分样式需要 LaTeX；可按场景用 `no-latex`，中文仍需字体支持 |
| S04 [Python Graph Gallery](https://python-graph-gallery.com/) | 作者维护的 Python 示例和教程图库 | 按图型找代码，学习标注、配色、分面、分布和完整成图 | 第三方教学库，不是 Python 官方标准；逐项检查数据、依赖和示例适用条件 |
| S05 [R Graph Gallery](https://r-graph-gallery.com/) | 作者维护的 R 绘图库 | ggplot2 等图型示例、统计分布、排版和图形细节 | 适合 R 项目；不是所有范例都适合简洁论文风格，优先选平面、直接标注的图 |
| S06 [Altair Gallery](https://altair-viz.github.io/gallery/) | Python 声明式统计图 | 分面、交互选择、区间、联合图；适合 notebook 与可复现分析 | 基于 Vega-Lite 生态；静态导出环境与目标宿主支持需要确认 |
| S07 [Plotly Python Templates](https://plotly.com/python/templates/) | 图表主题与模板机制 | `plotly_white`、`simple_white` 等主题以及自定义默认配置 | 是样式模板，不是替你确定图型；在多个实验图间保持轴、颜色与标注口径一致 |
| S08 [ggplot2](https://ggplot2.tidyverse.org/) | R 图形语法与文档 | 分层统计图、分面、主题、图例；适合批量生成一致结果图 | 可从简洁主题出发；主题简化不能省略单位、基准和必要的置信区间 |
| S09 [patchwork](https://patchwork.data-imaginist.com/) | R/ggplot2 组图工具 | 多面板布局、统一图例、对齐与分组；适合论文结果页 | 解决组图，不替代单张图设计；先统一各图的字号、范围和标签再拼接 |

<a id="no-code"></a>
## 7. 无代码图表工具：3 个

| 编号 / 资源 | 可获得的材料 | 适合的任务 | 使用边界 |
|---|---|---|---|
| N01 [Datawrapper Charts](https://www.datawrapper.de/charts) | 交互示例、在线图表编辑 | 清晰的条形、折线、点图与注释；报告和文章中的结果解释 | 是服务产品；具体导出、品牌定制和团队功能按方案核对。官网图表页本次可访问 |
| N02 [Flourish Examples](https://flourish.studio/examples/) | 在线可视化模板与案例 | 交互报告、叙事型图表、演示；适合快速做可以操作的数据说明 | 部分模板很强调动画；本次应优先选静态可读的折线、条形和关系结构 |
| N03 [RAWGraphs](https://www.rawgraphs.io/) | 开源可视化工具与范例 | 桑基/流向、分布、矩形树图和不常见图型；适合先生成图形再排版 | 工具能画不等于值得使用该图型；输出后仍要检查标签、数据编码与拥挤情况 |

<a id="foundations"></a>
## 8. 配色、图标与选图资料：9 个

| 编号 / 资源 | 用途 | 可以直接借鉴什么 | 少装饰取向 |
|---|---|---|---|
| D01 [Radix Colors](https://www.radix-ui.com/colors) | UI 色阶与语义颜色 | 背景、悬浮、边框、实色、文字等不同层级的颜色组织 | 灰阶为主体，只给选择、主操作和必要状态使用强调色 |
| D02 [ColorBrewer](https://colorbrewer2.org/) | 顺序、发散和分类调色板 | 按数据类型和色盲/打印需求筛选颜色 | 连续数量不要随意用彩虹色；类别颜色控制在能辨认的数量 |
| D03 [Scientific Colour Maps](https://www.fabiocrameri.ch/colourmaps/) | 科学可视化色图 | 感知有序的连续色图、发散色图、多工具格式 | 热图与连续场的颜色应反映数值变化，不靠鲜艳程度制造结构 |
| D04 [Lucide](https://lucide.dev/) | 一致线性 SVG 图标 | 文件、搜索、打开、编辑、折叠、下载等动作图标 | 全站采用一套图标；含义不明显的按钮保留文字标签 |
| D05 [Tabler Icons](https://tabler.io/icons) | 线性与填充图标库 | 可调整线宽和尺寸的图标；适合管理界面与工具栏 | 与 Lucide 二选一更容易保持一致；避免图标成为主要视觉负担 |
| D06 [From Data to Viz](https://www.data-to-viz.com/) | 由数据结构选择图型的资料 | 比较、分布、关系、层次、流向等任务与图型的对应 | 先确定比较对象，再选样式；不因为模板新奇就采用难读图型 |
| D07 [Fundamentals of Data Visualization](https://clauswilke.com/dataviz/) | 作者公开书稿 | 颜色、坐标、分布、不确定性、多面板、图例与解释 | 为图表审美提供可读性依据，避免只靠“看起来高级”选图 |
| D08 [FT Chart Doctor](https://github.com/Financial-Times/chart-doctor) | 图表示例与 Visual Vocabulary 资料 | 按变化、排名、分布、相关性等用途组织图型 | 可把它当作团队共用的选图菜单；原仓库路径已重定向 |
| D09 [Data Looks Better Naked](https://darkhorsevisualization.com/blog/data-looks-better-naked) | 图表逐步去除干扰的演示 | 理解背景、边框、阴影和网格为什么应有所节制 | 删除的是干扰信息；轴、单位、必要标注和状态不能因“极简”而消失 |

<a id="recipes"></a>
## 9. 24 个具体模板与示例切入点

前面的表用于广泛选型，本节直接回答“打开后先看哪一个”。改法一栏是针对本次需求的设计建议，不是原作者宣称的唯一用法。

### 9.1 前端页面：6 个

| 编号 | 模板或示例入口 | 适合移用到什么任务 | 建议保留与调整 |
|---|---|---|---|
| T01 | [shadcn Blocks：dashboard-01](https://ui.shadcn.com/blocks) | 数据概览 + 明细表 | 保留导航、筛选、图表与表格对齐；若没有明确指标任务，删去顶部统计卡 |
| T02 | [shadcn Blocks：sidebar-07](https://ui.shadcn.com/blocks) | 可折叠工作区导航 | 保留展开/收起与分组；默认让核心栏目有文字，不把操作全部缩成图标 |
| T03 | [shadcn Blocks：sidebar-03](https://ui.shadcn.com/blocks) | 主题树与分层导航 | 使用少量层级与一致缩进；过深结构进入主内容区浏览 |
| T04 | [shadcn Tasks](https://ui.shadcn.com/examples/tasks) | 论文、任务、实验记录列表 | 标题列占主要宽度；状态次要显示；筛选与排序集中在列表上方 |
| T05 | [Tremor Templates：Overview](https://blocks.tremor.so/templates) | 实验状态、资源使用或运行统计 | 保留有意义的图表组合；多个指标共享筛选时间范围，减少重复图例 |
| T06 | [Mantine UI：Tables / Navbars](https://ui.mantine.dev/) | 数据表 + 固定侧栏的基础工作台 | 抽取行高度、表头、页内筛选和导航组织，统一成同一色阶 |

### 9.2 思维导图与关系图：6 个

| 编号 | 模板或示例入口 | 适合的内容 | 建议保留与调整 |
|---|---|---|---|
| T07 | [Markmap 在线编辑器默认示例](https://markmap.js.org/repl) | 论文阅读大纲、研究问题分解 | 以短标题为节点；细节放正文；导图可折叠，避免初始全展开 |
| T08 | [Mermaid Mindmap 基本示例](https://mermaid.js.org/syntax/mindmap.html) | 文档中的小型主题总览 | 统一节点形状；颜色用于一级分组，其他层级使用中性色 |
| T09 | [React Flow Mind Map App](https://reactflow.dev/learn/tutorials/mind-map-app-with-react-flow) | 用户需要编辑、拖动和增加节点的导图 | 保留明确的新增/编辑动作；细边框、短标签，降低节点装饰 |
| T10 | [G6 树图场景：思维导图 / 缩进树](https://g6.antv.antgroup.com/examples/scene-case/tree-graph/) | 文献树、任务分类、知识目录 | 长标题更适合横向树或缩进树；选中后显示局部信息 |
| T11 | [draw.io 模板对话框](https://www.drawio.com/docs/manual/templates/template-diagrams/) | 手工编辑流程、泳道或架构图 | 同一层用相同形状；统一连线方向；只保留参与表达的容器与颜色 |
| T12 | [Graphviz Gallery](https://graphviz.org/gallery/) 的 Clusters / Data Structures | 模块依赖、方法谱系、组成结构 | 按模块分组，使用层次布局；减少边交叉，图例说明箭头含义 |

### 9.3 数据图与科研图：12 个

| 编号 | 模板或示例入口 | 适合的内容 | 建议保留与调整 |
|---|---|---|---|
| T13 | [shadcn Bar Charts：horizontal / label](https://ui.shadcn.com/charts/bar) | 方法排名、类别计数、资源数量比较 | 长方法名使用水平条形；排序后直接标数，统一基线 |
| T14 | [Recharts Simple Line Chart](https://recharts.github.io/en-US/examples/SimpleLineChart/) | 少量实验曲线比较 | 缩减网格；方法映射固定颜色和线型；明确横轴是步数还是时间 |
| T15 | [Vega-Lite：Line Chart with Confidence Interval Band](https://vega.github.io/vega-lite/examples/layer_line_errorband_ci.html) | 均值趋势与不确定性 | 对应多次独立运行数据；图注明确区间含义，不把单次运行波动称为置信区间 |
| T16 | [Vega-Lite：Layering text over heatmap](https://vega.github.io/vega-lite/examples/layer_text_heatmap.html) | 方法 × 数据集、参数扫描或结果矩阵 | 单元格足够大才显示数值；色条要有单位，文字随背景亮度调整 |
| T17 | [Vega-Lite：Gantt Chart](https://vega.github.io/vega-lite/examples/bar_gantt.html) | 实验尝试的开始、结束和并发时段 | 横轴用时间，纵轴用任务；状态少量着色，排序明确 |
| T18 | [Vega-Lite：Ranged Dot Plot](https://vega.github.io/vega-lite/examples/layer_ranged_dot.html) | 同一对象改进前后的两点比较 | 两端点与连接线显示差值；直接标注前后含义，避免误认为误差区间 |
| T19 | [Vega-Lite：Interactive Line Highlight](https://vega.github.io/vega-lite/examples/interactive_line_hover.html) | 多条曲线的局部阅读 | 未选中曲线降低强调，保留背景上下文；键盘和触摸也应能选择 |
| T20 | [Seaborn：Timeseries with error bands](https://seaborn.pydata.org/examples/errorband_lineplots.html) | 多被试或多次实验的趋势比较 | 认真核对分组与聚合；同图中不要混用不同时间口径 |
| T21 | [Seaborn：Diagonal correlation matrix](https://seaborn.pydata.org/examples/many_pairwise_correlations.html) | 指标之间的相关性 | 使用零点居中的发散色；三角遮罩减少重复，不把相关性解释成因果 |
| T22 | [Seaborn：Scatterplot with categorical variables](https://seaborn.pydata.org/examples/scatterplot_categorical.html) | 每组样本的分布与数量 | 样本量较少时显示原始点，避免只画均值柱；密集时调整透明度或分组 |
| T23 | [SciencePlots 样式示例](https://github.com/garrettj403/SciencePlots) | 论文中多张图的统一样式 | 统一图宽、字体、线宽和导出方式；逐次检查中文、数学字体和长图例 |
| T24 | [patchwork 组图示例](https://patchwork.data-imaginist.com/) | 一页多个实验结果 | 保持面板字母、轴标题和图例一致；相同量纲需要比较时使用相同尺度 |

<a id="chart-selection"></a>
## 10. 根据任务选择图型

以下是本次整理后的使用建议，适用于研究工作台和结果汇报。重点是让图型与问题匹配。

| 需要回答的问题 | 常用图型 | 可从哪里开始 | 容易出的问题 |
|---|---|---|---|
| 这个主题分成哪些部分？ | 横向树、缩进树、思维导图 | Markmap、Mermaid、G6 | 大段正文塞入节点；层级过深；所有分支同时展开 |
| 这些概念之间是什么关系？ | 有标签的概念图或局部关系网络 | G6、Cytoscape、React Flow | 连线没有关系语义；所有节点同等突出；无止境力导向运动 |
| 工作按什么顺序进行？ | 流程图、泳道、状态图 | Mermaid、draw.io、D2 | 箭头方向混乱；流程依赖和数据流混用一种线 |
| 哪个方法更高或更低？ | 排序条形图、点图、带区间的点图 | ECharts、Vega-Lite、Matplotlib | 用饼图比较接近的值；条形基线截断后夸大差异 |
| 指标随时间如何变化？ | 折线、小多图 | uPlot、ECharts、Seaborn | 平滑抹掉异常；未注明平滑；把不规则采样当等间距 |
| 样本是如何分布的？ | 直方图、ECDF、箱线 + 原始点、小提琴 | Seaborn、Observable Plot | 只显示均值；样本很少仍画光滑密度；未标样本量 |
| 两个变量有何关系？ | 散点、hexbin、回归与区间 | Plotly、Vega-Lite、Seaborn | 重叠遮盖；横纵轴单位缺失；把相关理解为因果 |
| 参数改变会影响哪些指标？ | 热图、分面曲线 | ECharts、Matplotlib、Altair | 每幅图用不同色标却直接比较；色条范围未交代 |
| 几个数据集上的结果是否一致？ | 共享尺度的小多图、结果矩阵 | Vega-Lite、Seaborn、patchwork | 图例重复；轴范围不同；为了紧凑把字缩得过小 |
| 计算资源花在哪些阶段？ | 时间区间图、堆叠条形 | Vega-Lite Gantt、ECharts | 只有总耗时而看不到重叠与等待；饼图掩盖时间顺序 |
| 质量、速度和内存如何权衡？ | 散点 + 标签、分面；必要时标 Pareto 前沿 | Plotly、Matplotlib | 用雷达图拼接不同单位；归一化过程未说明 |
| 数据从哪些来源流向哪些去处？ | 桑基/Alluvial | RAWGraphs、Nivo、G2 | 没有实际流量也用流图；连线拥挤，颜色与对象不一致 |

对于 3DGS/视觉实验，PSNR、SSIM、LPIPS 可分别成图或放在清楚标注的结果表；速度—质量图要说明 FPS 的分辨率和硬件条件；LPIPS 等“越低越好”的指标应写明方向。这里只提供表达建议，不预设具体实验结果。

<a id="design-rules"></a>
## 11. 少装饰的设计参数建议

以下数值是可供试用的设计起点，不是已经批准的全局规范，也不需要机械套用。最终以真实中文内容、长标题、窗口宽度和信息密度校验。

### 11.1 前端界面

| 项目 | 可试用的起点 | 目的 |
|---|---|---|
| 页面底色 | 白色或很浅的中性灰，例如 `#FAFAFA` | 保持长时间阅读稳定 |
| 主文字 / 次文字 | 深灰 `#202124` / 中灰 `#5F6368` | 依靠字重与层级分配注意力；再实测对比度 |
| 强调色 | 一种低饱和蓝或绿；例如 `#245B8F` | 只突出主动作、选择与关键数据 |
| 边界 | 细分隔线，例如 `#E2E5E9`；每个区域不必都有外框 | 用对齐和间距先表达分组 |
| 字体 | 一套清楚的无衬线字体；正文与数字按用途调整 | 避免装饰性标题抢占工作内容 |
| 操作界面字号 | 14–16 px 起；说明文字通常不低于 12 px | 长标题与表格易读，不用缩字解决布局问题 |
| 阅读区字号 | 16–18 px 起；中文行高约 1.65–1.8 | 提高正文阅读舒适度 |
| 页面标题 | 20–28 px 起 | 清楚标识当前位置，减少过大的标题留白 |
| 间距 | 4 / 8 / 12 / 16 / 24 / 32 px 的有限刻度 | 建立可预期的对齐与密度 |
| 圆角 | 4–8 px 起，按层级统一 | 避免所有元素都呈胶囊或大圆角卡片 |
| 阴影 | 常驻内容通常不需要；弹窗、悬浮菜单按需使用 | 让阴影表达浮层关系 |
| 动效 | 状态反馈短促、必要；尊重减少动态效果偏好 | 界面稳定，阅读内容不随悬浮跳动 |
| 图标 | 同一套线性图标，通常 16–20 px；生僻动作配文字 | 减少风格混杂与猜测 |
| 表格 | 文字左对齐、可比较数字右对齐、等宽数字 | 方便扫描和比较 |
| 状态 | 少数语义色，并有状态文字 | 不能只靠颜色判断成功、失败或禁用 |

可以优先减少：大面积渐变、无业务含义的背景纹理、重复卡片外框、每行一个彩色图标、大块品牌色侧栏、卡片悬浮上移、同屏多个主按钮、没有决策意义的统计数字。

应保留：可辨认的交互边界、键盘焦点、当前位置、选中状态、错误解释、单位、必要的加载反馈。减少装饰不应让操作变得难以发现。

### 11.2 思维导图与关系图

先建立文字层级和布局，再做颜色。一级分支可有少量分类色，普通节点保持统一。长内容放详情或正文中，节点承担目录功能；连线有明确含义时才加箭头和关系标签。

可试用的起点：白底、细边、14–16 px 节点文字、少量主分支颜色、稳定布局、可折叠子树、点击节点显示详情。节点大小由内容与层级决定，不为视觉热闹随机变化。大图以搜索、局部展开和邻域查看降低拥挤。

对于阅读任务，横向逻辑树与缩进树通常更容易容纳长论文标题；放射状导图适合短词与少数主分支。这是布局取舍，不能理解为某种图型一律更好。

### 11.3 数据图表

白底或透明底、适量浅网格、明确单位、稳定的颜色映射、必要的直接标签，通常比背景与渐变更有用。数据系列较多时，优先分面或允许突出选中系列。图例、色条和 tooltip 是解释数据的一部分，应有一致格式。

连续变量使用有序色图，偏离基准的正负变化使用发散色图，类别使用分类色。相同方法跨页面保持同一颜色，并辅以线型、形状或文字。论文图还需检查黑白打印、缩放后的标签与字体嵌入。

可试用的起点：网页线宽约 1.5–2 px、重点线略粗；数据标签 12–14 px 起；非必要的网格和边框减弱。论文图以最终排版物理尺寸判断字号，不能直接把网页像素数当作论文规范。

<a id="hub"></a>
## 12. 针对当前 scholar-workflow Hub 的建议

### 12.1 当前条件

本次只读检查了当前 `AGENT.md`、`planning/GOALS.md` 中的界面目标，以及 `src/scholar_workflow/hub/static/hub.css` 的开头样式。Hub 以原生 HTML/CSS/JS 实现，已有阅读优先的目标。样式中可见深绿色侧栏、较大的衬线标题、资源卡片、阴影和悬浮位移。以下是基于代码的设计观察，未完成当前 Hub 的实屏视觉验收。

### 12.2 三种实施路径的取舍

| 路径 | 能得到什么 | 成本与局限 |
|---|---|---|
| 保留原生 HTML/CSS/JS，重整排版与样式 | 页面、数据与动作结构延续；可借鉴 Primer、Geist、Pico、HyperUI 的局部设计 | 复杂表格、可访问菜单、图编辑器需自己补齐或单独接库 |
| 迁移到 React + shadcn/Tremor | 组件、表格和图表生态较完整，可复用更多代码示例 | 涉及构建、状态、渲染和测试方式变化；视觉调整与架构迁移会一起发生 |
| 采用整套后台模板 | 很快得到多种完整页面和统一控件 | 会带入认证、路由、业务演示、依赖和冗余页面；需要较大删改 |

**建议：当前优先保留原生技术栈，做一次集中的视觉与信息布局调整。**少装饰目标主要依赖层级、对齐、字体、状态与间距，不必先更换框架。若后续大量需求集中在复杂表格、联动图和节点编辑，再独立评估前端架构。

### 12.3 页面模式建议

| Hub 任务 | 适合的页面模式 | 参考资源 |
|---|---|---|
| 查找论文与资源 | 窄侧栏 + 搜索/筛选 + 密集列表或表格 | Primer、shadcn Tasks、Linear |
| 阅读 Markdown / PDF | 目录或结果列表 + 主阅读区；辅助信息按需展开 | Outline、Nuxt Editor 类模板 |
| 查看项目与运行记录 | 任务列表 + 详情侧栏；结果图进入对应任务 | Plane、Tremor Tables/Overview |
| 浏览文献或分析结构 | 大纲与可折叠树；需要空间关系时再进入画布 | Markmap、G6、React Flow |
| 查看实验结果 | 筛选条件 + 少量核心图 + 原始结果表 | ECharts、Vega-Lite、Tremor |
| 修改设置 | 分组表单 + 一致保存反馈 | Radix、Mantine、Pico |

### 12.4 可以先试的五项改动

1. **资源浏览增加列表视图。**论文标题、作者、年份、资源类型和主要动作形成稳定列；卡片保留给确实受益于缩略图的内容。
2. **减轻导航与标题的视觉重量。**尝试浅色侧栏、明确选中态、小一级的无衬线标题，将更多空间留给内容。
3. **统一表单、按钮与行高。**主要动作明显，次要动作平静，重复操作集中在行末；必要的键盘焦点清楚可见。
4. **去掉常驻卡片阴影与位移动效。**用分隔线和间距表达区域；浮层仍保留必要的层次提示。
5. **把图与具体问题放在一起。**导图帮助定位知识结构，结果图服务实验比较；默认页面不堆没有具体用途的统计卡与全库网络图。

这些是后续可执行的设计建议。本次收集没有修改 Hub 的 HTML、CSS、JS 或业务逻辑，也没有将这些参数写成运行期 skill 规则。

### 12.5 本次推荐的优先阅读顺序

在前面的资源与路径取舍基础上，建议先看以下 10 项：

1. **shadcn Tasks**：最直接的少装饰列表与操作表参考。
2. **Primer**：学习高密度工作界面的操作组织。
3. **Outline**：学习知识库正文阅读与目录关系。
4. **HyperUI Application / Pico CSS**：评估原生页面可以低成本借鉴什么。
5. **Tremor Blocks**：学习数据表、过滤器和图表的统一布局。
6. **Markmap**：文本大纲生成导图的起点。
7. **React Flow / G6**：明确需要节点交互以后再进入。
8. **ECharts**：当前原生网页接入常见交互图的候选。
9. **Vega-Lite Gallery**：寻找清楚的统计图型和可复现规格。
10. **Seaborn + SciencePlots**：科研图表的示例与样式起点。

<a id="verification"></a>
## 13. 核验记录与访问边界

本次以官方站点、作者资料与项目源仓库为主要证据；没有根据 GitHub 星数评美观，没有把搜索结果页作为最终资源入口。以下是影响使用的具体核验结果：

| 资源 | 本次观察 | 在清单中的处理 |
|---|---|---|
| [Tremor Blocks](https://blocks.tremor.so/) | 首页写明 Blocks 与 Templates 已开源，部分其他文案仍出现 Premium | 按当前公告记录，不沿用“全部付费”的旧判断；具体模板看仓库 |
| [SimpleMindMap README](https://github.com/wanglin2/mind-map/blob/main/README.md) | 开源库/Web 低维护；客户端和插件闭源、继续开发 | 降低它作为新项目长期核心依赖的优先级，保留布局与编辑能力参考 |
| [Shadcn Admin](https://github.com/satnaing/shadcn-admin) | 作者称其为 dashboard UI，并明确不是完整 starter | 不把多页面演示说成具有全部后端功能的应用模板 |
| [tldraw 许可页](https://tldraw.dev/pricing) | 生产 SDK 商业许可、试用与 hobby 申请并存 | 清楚注明许可门槛，未提供固定购买价格 |
| [Tailwind Plus](https://tailwindcss.com/blog/tailwind-plus) | 当前若干产品入口跳转登录；官方文章说明产品更名和商业内容关系 | 根据官方介绍归类为商业资源，未访问付费内部代码 |
| [Tailwind HTML 文档](https://tailwindcss.com/plus/ui-blocks/documentation/using-html) | HTML 交互片段依赖 Elements，文档注明商业许可要求 | 不把“HTML 格式”误当作无依赖、无限制 |
| [Xmind Templates](https://templates.xmind.com/) | 当前模板市场含免费与付费项 | 使用新入口，替代本次无法访问的旧 mindmaps 路径 |
| [Recharts](https://recharts.github.io/en-US/examples/SimpleLineChart/) | 旧 `recharts.org/en-US/examples` 返回 404，官方 GitHub Pages 示例可访问 | 使用已检索到的现行具体示例链接 |
| [draw.io Templates](https://www.drawio.com/docs/manual/templates/) | 原 example-diagrams 路径本次返回 404，现行模板文档可访问 | 链接现行模板文档与扩展仓库说明 |
| Flowbite / Page Flows / Refero | 分别有 403、首页失败或只返回标题的情况 | 提供可核验的官方替代入口或明确保留项限制 |
| ECharts / Markmap 编辑器 / Excalidraw 等 | 部分页面主要依赖浏览器 JavaScript，正文抓取有限 | 记为动态预览入口；没有声称完整交互已逐项测试 |

更新这份清单时，优先复核资源链接、维护状态、免费/付费边界和所选具体示例，不必追逐每一个依赖的小版本。
