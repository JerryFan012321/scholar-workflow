# 研究来源候选与 0.48.0 安装后验收准备

核查日期：2026-10-24。这里是开发阶段的候选清单和验收方案，不是用户关注台账。
未登记订阅、未创建定时任务、未安装候选包，也未写 test 或正式 Vault/Zotero。
候选不进入插件的默认配置；发布时本文件不进入 runtime-only 产物。

## 首批候选来源

| 来源 | 官方入口 | 建议渠道类型 | 能观察什么、不能据此推断什么 |
|---|---|---|---|
| Lilian Weng · Lil’Log | [博客](https://lilianweng.github.io/)；[FAQ](https://lilianweng.github.io/faq/) 明确链接 [RSS](https://lilianweng.github.io/index.xml) | `rss` | 可观察 feed 中的文章及修订；有限 feed 窗口不等于全部历史，个人博客不代表任职机构的正式公告。 |
| Berkeley AI Research · BAIR | [研究博客](https://bair.berkeley.edu/blog/)；[关于](https://bair.berkeley.edu/blog/about/) | `webpage` | 可观察研究列表页正文变化；本次没有确认官方 feed，[Subscribe](https://bair.berkeley.edu/blog/subscribe/) 是邮件表单，不据此猜 RSS 地址。 |
| Danijar Hafner | [研究主页](https://danijar.com/) | `webpage` | 个人研究进展与材料入口，不冒充独立博客 feed；页上不同材料仍需分别确认身份。 |
| Stanford CRFM | [博客列表](https://crfm.stanford.edu/blog.html)；[中心介绍](https://crfm.stanford.edu/) | `webpage` | 基础模型研究文章列表；单页变化不能称为逐篇订阅或全站历史采集。 |
| Google DeepMind | [News](https://deepmind.google/blog/) | `webpage` | 模型、研究和机构公告；页面列表变化不证明具体模型可用，也不自动归档每篇公告。 |
| Mistral AI | [Research](https://mistral.ai/research/) | `webpage` | 模型和 publications 入口；模型介绍、技术报告、权重和许可证分别核实，不把宣传语当复现结果。 |
| Alibaba Cloud · Qwen | [官方模型组织](https://huggingface.co/Qwen) | `hf_models` | 公开模型仓库元数据及修订；不包括该组织全部数据集、Spaces 或活动，不下载权重。 |
| NVIDIA · Cosmos | [仓库](https://github.com/NVIDIA/cosmos)；[Releases](https://github.com/NVIDIA/cosmos/releases) | `github_releases` | 正式 Release 及修订；登记仓库根 URL，而非 `/releases`。README/文章变化不一定产生 Release，不能称覆盖全部进度。 |

以上入口均通过公开官方页面核查。Lil’Log 的官方 RSS 另做了一次有界的直接读取：
XML 根为 RSS，channel 为 Lil’Log，本次响应 79,640 字节、53 项，样本具备标题、链接、
GUID 和发布日期。这仅是输入来源核验，不是候选插件、实际代理/TLS 或安装态通过证据。
条目数量和响应大小不是固定验收值；其他候选的适配器联网和分页也尚未实机验收。

网页渠道当前只能观察一张已选页面的可读正文变化，不抓取其全部子页面。组织模型列表、
公告和技术文档不是同一种资源。正式关注范围、检查周期、通知方式仍待用户选择，
不把这些候选做成所有用户必须订阅的名单，也不将一次网站变化直接写成“技术进步”。

## 安装后只验一个来源

本轮对象：Lil’Log 官方 RSS。用户已批准0.48.0提交、发布、正常安装及test单来源验收；
先完成正常 hotfix 发布和安装再执行。这里不扩大为正式入库、全网抓取或再次分析论文。

### 输入与隔离范围

- 输入是上表官方 RSS 和下面的单个渠道规格；不提供旧动态结果或预写好的正文。
- 在 test Vault 的一个新目录“Scholar Workflow 实验/研究来源跟踪-0.48.0”保留可见报告
  和回执；该目录尚未创建，执行前确认不重名，不能覆盖旧验收对象。
- 当次以其专用私有 `_state` 作为 `SCHOLAR_WORKFLOW_HOME`，不触碰日常配置根。
  仅创建这一份渠道登记和观察历史；不登记正式 Knowledge Source/Field。
- 使用正常安装的命令和随包 Skill/reference；不注入源码、修改缓存或换临时解释器。

```json
{
  "channel_id": "acceptance-lillog",
  "name": "Lil’Log",
  "publisher": "Lilian Weng",
  "publisher_kind": "researcher",
  "kind": "rss",
  "url": "https://lilianweng.github.io/index.xml",
  "enabled": true,
  "topics": []
}
```

### 操作、预期结果和证据

| 操作 | 通过标准 | 留存证据 |
|---|---|---|
| 核对安装身份 | 插件、两个 CLI 的版本及发布回执对应；记录实际命令、解释器和 runtime commit。身份不符则不继续。 | 安装回执和版本/路径结果，不把源码运行算安装。 |
| 读取隔离空状态，再登记单渠道并读回 | 空读取不创建状态；登记后只有该渠道，稳定 ID、URL、publisher 正确。 | 命令结果、登记读回；日常配置根不变。 |
| 明确使用首次 `report` 模式检查 | 为展示动态，主动选择当前可见条目；类型是“首次发现”，不是“新增发布”，保留来源与观察时间，输出不宣称完整历史。 | 当次 JSON、中文 Markdown；不保存模型/PDF、网页全文或秘密。 |
| 对同一渠道再次检查 | 若内容未变，不重复发事件；若源恰好改变，如实核实变化并记录，不伪造稳定输出或重试到全绿。 | 前后事件身份和实际检查结果；不把此项当成真实新增/修订已全部验收。 |
| 对一条实际可见记录标为 `selected` 并读回 | 只改变处理选择；人类标签明确“已选待归档”，Zotero/Vault 中不会据此出现新知识单元。 | 状态读回及可读表格。 |
| 在 Obsidian 打开本轮报告 | 来源、原文链接、检查时间和选择状态清楚，无技术 hash/ID 淹没正文；首次可见条目不伪装成刚发表。 | 报告原生展示和用户评阅，未确认前为“待人工评鉴”。 |

默认 `baseline`、内容修订、失败恢复、分页、安全拒绝仍有开发合成用例；上面的一次真实
RSS 验收不代替所有渠道类型的真实联网证明，不为了演示增量而改写官方源或注入假事件。
测试报告是一次独立的可读投影，不需要新前端，也不成为第二份订阅/观察权威。

### 独立上下文复现

若进入此项，只给独立执行者已安装 Skill、用户目标、官方来源和隔离 test 位置；
不传入旧报告、内部实现提示或人工逐步指令。由执行者正常发现并使用已安装接口，
记录一次产物和真实失败。调用方不在结果生成后补写正文或手工修正状态再称一次成功。
该项只证明本轮研究来源跟踪的复现，不证明完整论文分析、项目或实验 Skill 的 one-shot。

### 人工评鉴如何进行

执行后在会话中给出本轮报告的直接打开链接，请用户在 test Vault 打开，点击一条原文链接，
检查“谁的什么内容、什么时候检查、首次发现还是后来变化、是否已入库”能否独立读懂。
人工认可只记录到本报告的可读性/链接体验，不代替科学支持或其他产物的验收。

## 当前未执行的边界

实际发布/安装/验收结果见0.48.0-release.md，未执行的步骤不记通过。正式关注名单、定时调度、完整模型档案、
选中资源的正式归档与分析各有后续范围；不因此修复 Genie3/L1-cache 的正式库登记异常。
原有论文正文、五分支 Canvas、模范领域库、项目和实验输出契约保持不变。
