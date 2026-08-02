# 功能规格(草案)— 两级 AI 论文阅读:略读(推荐上游)+ 详细分析(落 vault)

> 规划层文档(永久,不归档)。意图对照 `GOALS.md`,变更史 `../CHANGELOG.md`。
> **状态:草案,待用户审阅后再落地。** 本文只记方案,不动代码。
> 参照学习:sjh-skills `scholar-agent`(推荐→筛选→NotebookLM 略读→反馈闭环)。

## 缘起(为什么做)

用户要细化"论文的 AI 阅读",明确分两类:
- **略读**:服务于**论文推荐功能**的批量总体阅读,**外包给 NotebookLM 省 token**。
- **详细分析 / 局部详细分析**:用户按需单独发起,产物是**论文的附属文件之一**。

调研确认:直接读 20 页论文 ≈50K token,NotebookLM 提问 ≈500 token/问(sjh 实测量化);
5 篇即省约 250K token —— 这是"略读外包"的经济学依据。

## 设计哲学对齐(AGENT.md 上位准则)

**"读论文、写摘要、跨文比较、判断归类"是模型内在能力,一律不写进 skill。**
本功能值得固化的只有**外来规定**:每级读什么源、产物落哪、什么格式、跟现有
Zotero/Obsidian/Notion 管线怎么接、引入哪些外部依赖。skill 只编排数据进出与落点,
不教模型"怎么读"。

## 已锁定的决定(经 grill)

1. **略读进出 NotebookLM**:走**非官方 CLI/MCP 自动化**(`notebooklm-py`,Google 内部
   RPC API,比 DOM 抓取稳)。属 AGENT.md「Ask First:给 skill 加外部依赖」,落地前须批准。
2. **略读产物临时**:摘要喂完推荐决策即弃,**不落 vault**。略读是推荐功能内部一环。
3. **详细分析读什么源**:只读论文正文(zotero-mcp `get_content`),**不解析 PDF 本体**
   (承 INV10);**与人工批注分立**,靠 frontmatter `related` 互链(复用 export-annotations
   现有避让逻辑)。
4. **局部分析组织**:一篇论文一份"分析笔记",每次局部分析**追加一个小节**;写在**受管块之外**
   人工区,由 INV4 保护、不被重投影覆盖。挂到该论文相关资料枢纽(INV20)下。
5. **推荐源 = 多源聚合器**:四类源各一适配器,吐规范化候选(arXiv id + 元数据 + 来源标签),
   按 arXiv id 合并去重。四个信号面互不重叠:
   - **Semantic Scholar Recommendations**(库派生个性化):**Zotero 库当 positive 种子**,官方 REST、
     零登录;个性化与权威库同源(承 G2),不必另养平台画像。
   - **Scholar Inbox**(训练型个性化):平台上长期 up/down vote 训出偏好,每日带分 digest,越用越准。
     需 playwright-cli 登录 + session cookie(~7 天过期);sjh `scholar_inbox` 模块是现成适配器。
   - **S2 author papers**(watchlist 定向):按你指定、已登记 authorId 的实验室/研究者盯新作。
   - **HuggingFace Daily Papers**(社区热度):upvote 热度榜,无 auth。
6. **watchlist 半自动登记**:你给名字(+ 机构 / 代表作),经 S2 解析出稳定 `authorId` 存进
   watchlist 台账(类 env-records 登记模式),之后按 id 盯梢——规避 S2 重名(如 "He Wang" 2881 条)。
7. **每日略读漏斗**(四源汇入 → 全量呈现 → 细化 → 略读 → 推荐清单):
   ① 四源合并去重 → **所有可选项列表**(元数据级,便宜,不 skim);
   ② **细化选择**(兴趣过滤 + 用户挑,可按来源筛)→ shortlist;
   ③ 仅 shortlist 走 **NotebookLM 略读** → source-grounded 简要描述;
   ④ **推荐论文清单 + 简要描述**(临时)→ 喂推荐决策 → 看中的接 ingest。
   **NotebookLM 只略读 shortlist、不略读全池**——全量层用免费摘要/元数据初筛,守住"省 token"初衷。

## 架构与数据流

```
[略读级 — 推荐上游,不落 vault]  每日漏斗
┌─ Semantic Scholar Recommendations(Zotero 库当 positive 种子)
├─ Scholar Inbox(训练型个性化,带分 digest;playwright 登录态)
├─ S2 author papers(watchlist:已登记 authorId 的实验室/研究者)
└─ HuggingFace Daily Papers(社区 upvote 热度)
    │ 四源各一适配器 → 规范化候选(arXiv id + 元数据 + 来源标签)
    ▼ 按 arXiv id 合并去重
① 所有可选项列表(元数据级:标题/作者/来源/分数/摘要片段 —— 便宜,不 skim)
    │ ② 细化:兴趣过滤 + 用户挑(可按来源筛)
    ▼ shortlist
notebooklm-py ──source add arXiv URL──→ NotebookLM 建/选 notebook
    │ ③ notebooklm ask ──→ source-grounded 简要描述(≈500 token/问;仅 shortlist)
    ▼
④ 推荐论文清单 + 简要描述(markdown,临时)──→ 喂推荐决策
    │ 看中的论文 ↓ 接现有管线
    └──→ find-resource / ingest-resource(入 Zotero,判重两步核验)

[详细分析级 — 落 vault 附属文件]
用户对某篇已入库论文发起(全文 / 局部)
    ▼
zotero-mcp get_content ──→ 论文正文(不碰 PDF 本体,INV10)
    │ 宿主 LLM 分析(内在能力,不编码)
    ▼
Obsidian 分析笔记(<论文名>分析.md 或枢纽下)
    ├─ 受管块外人工区,局部分析多小节追加(INV4)
    ├─ frontmatter related ←→ 批注笔记(export-annotations 产物),两者分立
    └─ 挂论文相关资料枢纽(INV20)
```

**分层原则**(承 Phase 2):四个推荐源 + NotebookLM 都是**推荐与略读的外部服务**,
**非权威库** —— 权威始终是 Zotero(G2)。略读只影响"收不收"的决策,不改库、不落 vault。

## skill / agent 结构(已决)

**已决(2026-08-02):拆两个 skill**,六条轴全发散(源 / 产物寿命 / 触发面 / 依赖 / agent /
动作性质),合成一个会让 description 精神分裂、伤路由:

- **`recommend-papers`(略读级)** → 挂 **intake agent**(发现入口)。
  四源聚合(S2 推荐 + Scholar Inbox + S2 author watchlist + HF Daily)+ NotebookLM 驱动、
  产物临时、接 find/ingest 上游。每源一适配器(套 `adapters/` 既有模式),共用"emit 规范化候选"接口。
  **网络层坑(已探活)**:S2 API 走 `--noproxy` 直连,HF Daily 需走代理(`127.0.0.1:7890`);
  Scholar Inbox 走代理待落地时验。适配层各自固定路径。watchlist authorId 台账落 env-records 式登记文件。
  watchlist 半自动登记**不单开 skill**,是 recommend-papers 的一个子模式(类 setup)。
  与 find-resource 是**推 vs 拉**姊妹(feed 发现 vs 定向查),同属 intake。

- **`analyze-paper`(详细分析级)** → 挂 **knowledge agent**。命名取动词开头,合六个主流 skill 惯例。
  经 zotero-mcp `get_content` 读正文、落 vault 附属笔记;与 export-annotations 是姊妹
  (AI 通读/局部分析 vs 人工批注导出,`related` 互链),同属"产 vault 知识件"的 knowledge。
  **落地待办**:export-annotations SKILL.md 里那处 `paper-analyzer` 前向引用改成 `analyze-paper`。

### 跨 skill:文献树复用 NotebookLM 批读(已决 2026-08-02)

"notebook 与 novelty-tree 打通"经用户澄清,**不是分类桶对齐,而是把 NotebookLM 当
build-literature-tree 的批量阅读引擎** —— 同略读级的省 token 原理复用。

- **操作**:建树要把一批论文归进 `task→pipeline→叶`、判 novelty 锚点(首提者),需理解每篇贡献。
  方向内论文多时,宿主 LLM 直接吞全文 ≈50K token/篇会爆。改为:批论文 arXiv URL 加进 NotebookLM
  笔记本 → 问 source-grounded 问题(每篇核心贡献/解决哪个 task/谁最先提出 X pipeline)→ 拿
  ≈500 token/问摘要 → 宿主 LLM 据此建树。**分类与判首提仍是宿主 LLM(内在能力),NotebookLM 只做批读 substrate。**
- **软复用(非硬桥)**:略读级若已为某主题建过 notebook 并攒了论文,建同主题文献树时直接复用那本;
  没有则临时建。只是"碰巧同名就复用",不写成强制的分类映射规则。
- **不违反 INV10/G3**:这是**内容理解**(判贡献),非**元数据提取**;叶子 title/authors 仍取自
  Zotero/权威网源,NotebookLM 不喂元数据字段、不下载 PDF 入库(树论文本就已在 Zotero)。
- **不碰 INV22**:树拓扑(task→pipeline→叶+锚点+flat list+受管块+Mermaid)不动,NotebookLM 仅建树前读料。
- **回落**:NotebookLM 挂 → 回落 zotero-mcp `get_content`(能用、token 贵)或减小批量。
- **不编码(内在能力)**:"多少算大量"阈值、怎么读/归类/判首提 —— 交模型现场判,不写死。
- **依赖**:build-literature-tree 因此也用 notebooklm-py(插件已批准依赖,不新增审批面)。
- **落地待办**:build-literature-tree SKILL 加一条"批量读料优先经 NotebookLM"的编排提示(优化约束)。

### 配置分层(已决 2026-08-02:乙 = sjh 两层)

recommend-papers 的设置分两层,承 sjh 模型,落到本项目目录约定:

- **全局层** `~/.config/scholar-workflow/recommend.yml`(与 `config.yml` 同目录平级;路径配置留
  config.yml 不动)。存:全局兴趣关键词、四源开关、每日额度、分数阈值、NotebookLM 分类模式、
  **全局 watchlist**(一直盯的研究者/实验室 authorId)。
- **项目层** `~/.config/scholar-workflow/projects/<cwd名>.yml`,**按当前工作目录名自动加载**。
  存该项目专属关键词 + **项目级 watchlist 追加**。命中则叠加过滤(匹配者优先、其余降权不隐藏,
  承 sjh);未命中只用全局。
- **格式 = YAML**(对齐现有 config.yml + env-records 的结构化 YAML,不用 sjh 的 markdown)。
- **watchlist 两层叠加**:authorId 台账是"登记产生的个人数据",gitignored、模板可留(承 env-records 调性)。

### 外部依赖(已批准 2026-08-02)

两个带登录态的非官方依赖,经用户明确批准引入(AGENT.md「Ask First」已过闸):

- **`notebooklm-py`**(`pipx install "notebooklm-py[browser]"` + Google 登录):略读级自动化。
  doctor 加可达性探针;挂了回落手动交接。安全提示:存真 Google 登录态,建议用小号跑。
- **Scholar Inbox**(playwright-cli 登录 + session cookie ~7 天):四源之一。挂了降到三源。

**Scholar Inbox 适配器 = vendor sjh `scholar_inbox`(决定 A)**:
- 拷 **`api.py`(187 行)+ `auth.py`(140 行),纯标准库、零第三方、已生产验证**,进本 skill
  `scripts/` 或 `bin/`。**不拷 1456 行的 cli.py**(我们按需薄封装)。config 自写、对齐 env-records 台账。
- **归属声明(必做)**:sjh-skills 为 **MIT License(Copyright (c) 2026 Jiahao Shao)**。vendor 的每个
  文件头标 `Adapted from https://github.com/jiahao-shao1/sjh-skills (MIT License, Copyright (c) 2026
  Jiahao Shao)`;并在本 skill 目录保留一份其 LICENSE 文本(如 `scripts/THIRD_PARTY_LICENSES`)。
- 端点:`ScholarInboxClient` 打 `https://api.scholar-inbox.com/api`,方法齐(check_session/get_digest/
  get_paper/rate/rate_batch/get_trending/get_similar/collections)。我们只用 digest/paper 为主。

## 构建顺序(tracer-bullet,落地时执行)

承设计原则「先贯穿系统的最小路径,而非先把某层做完」。两 skill 无数据依赖(不同 agent、
各自独立),是两条平行 tracer 序列。

**A. recommend-papers**(先用**单源**贯通漏斗 + NotebookLM 管道,再加源)
- A0:vendor sjh `api.py`+`auth.py` + 归属声明;`recommend.yml` 配置骨架 + 加载。
- A1(tracer):**只接 HF Daily**(无 auth 最简)→ 合并 → shortlist → notebooklm-py 略读 → 打印
  Reading Report。**打通"源→漏斗→NotebookLM→报告"最小闭环。**
- A2:补另三源适配器(S2 推荐 / S2 author watchlist / Scholar Inbox),四源合并去重。
- A3:watchlist 半自动登记子模式(authorId 台账 + 模板);项目层配置按 cwd 加载。
- A4:doctor 探针 + 回落(NotebookLM 挂→手动交接;Scholar Inbox 挂→降三源)。

**B. analyze-paper**(独立于 A)
- B1(tracer):`get_content` 读一篇 → 写一份分析笔记(受管块外)+ `related` 互链到批注笔记。
- B2:局部分析多小节追加;挂相关资料枢纽(INV20)。
- B3:改 export-annotations 的 `paper-analyzer`→`analyze-paper` 前向引用。

**C. 文献树批读复用**(依赖 A0 的 notebooklm-py 到位)
- C1:build-literature-tree SKILL 加"批量读料优先经 NotebookLM"编排提示 + 同主题 notebook 软复用。

依赖:C 依赖 A0(notebooklm-py 装好);A、B 内部有序;A 与 B 可并行。

## 待定(全部已拍板 2026-08-02)

~~1. 外部依赖批准~~ **已决:批准 notebooklm-py + Scholar Inbox;Scholar Inbox 适配器 vendor
   sjh `api.py`+`auth.py`(MIT,标归属)。** 详见上「外部依赖」节。
~~2. 推荐源?~~ **已决:四源聚合(S2 推荐 + Scholar Inbox + S2 author watchlist + HF Daily)**,
   四个互不重叠的信号面(Scholar Inbox 出局的旧结论已推翻)。
~~3. 两 skill 拆分?~~ **已决:拆 `recommend-papers`@intake + `analyze-paper`@knowledge**;
   watchlist 登记为 recommend-papers 子模式;命名取动词式(需改 export-annotations 一处引用)。
~~4. 配置分层?~~ **已决:乙 = sjh 两层(全局 recommend.yml + 按 cwd 项目级),YAML,
   watchlist 两层叠加。** 详见上「配置分层」节。
~~5. notebook 与 novelty-tree 打通?~~ **已决:不是分类桶对齐,而是文献树建树时的批量读料
   交给 NotebookLM(省 token),同主题 notebook 软复用。** 详见上「跨 skill」节。

## 新增不变量(草拟,落地时定稿)

- **INV23(略读临时)**:略读经外部服务(推荐 API + NotebookLM)进行,产物为临时 Reading
  Report,**不落 vault、不改 Zotero**;看中的论文经 find/ingest 正式管线入库(判重两步核验)。
- **INV24(详细分析源)**:详细分析只读 zotero-mcp `get_content` 正文(承 INV10 不解析 PDF),
  产物落 Obsidian 附属笔记,与人工批注笔记分立、`related` 互链,局部分析受管块外多小节追加(承 INV4)。

## 参照来源

- sjh-skills `scholar-agent`(GitHub jiahao-shao1/sjh-skills):推荐+NotebookLM 略读闭环的现成范式。
- `notebooklm-py`(GitHub teng-lin/notebooklm-py):Google 内部 RPC API 的非官方 CLI。
- 现有 `skills/export-annotations/`:批注笔记产物,与详细分析分工互链。

