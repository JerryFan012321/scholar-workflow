# recommend-papers（推荐与审阅）

多个独立 agent 或定时任务可以通过同一个入口提交论文、项目主页和 Blog，在同一页面查看。
页面合并重复资源，保留各任务的推荐记录，并支持按领域、资源类型和推荐任务筛选。

## 统一入口

```bash
scholar-research recommendations --profile personal schema
scholar-research recommendations --profile personal submit --input recommendations.json
scholar-research recommendations --profile personal open
```

让 agent 使用 `recommend-papers`，并遵循[统一入口契约](../../references/recommendation-intake.md)。
`schema` 输出当前安装版本接受的数据格式；[提交示例](references/submission.example.json)
全部是合成数据，不要把它提交到个人候选池。

长期推荐任务使用稳定的 producer ID；每次执行有独立 run ID。重试复用原 submission ID
和相同内容。回执逐项说明已接收、重复、冲突或无效，不能把超时猜成失败后重复新建。

## 页面展示

- 论文：经核实的论文信息、完整中文摘要译文、可展开的原摘要，以及相关项目主页。
- 项目主页和 Blog：来源信息、原文简介或摘录，以及已有译文；没有论文的项目也可推荐。
- 平台原始数据：例如仓库 stars，注明对应对象、来源链接和采集时间，不作热度评价或合成总分。
- 领域标签、推荐任务和发现渠道，以及独立的人类审阅与选择状态。

**Reading Report** 是其中的论文呈现部分，只包含论文信息、摘要和相关项目主页。
不添加推荐理由、科研分析或阅读覆盖报告；来源失败等运行问题另行说明。

## 审阅后选择入库

论文入库前先看完整中文摘要译文，原文也保留供核对。选择完成后，可导出入库交接清单：

```bash
scholar-research recommendations --profile personal handoff
```

该清单交给常规 `find-resource` / `ingest-resource` 流程，并以你的实际入库要求为依据。
导出不会写入 Zotero 或 Vault，原有身份检查、目的地和来源规则继续有效。
摘要内容改变后需要重新审阅，单纯刷新 stars 不影响已经完成的摘要审阅。

## 查看状态、停止和测试隔离

```bash
scholar-research recommendations --profile personal list
scholar-research recommendations --profile personal status
scholar-research recommendations --profile personal stop
```

测试使用 `--profile test`；需要独立状态位置时，再显式设置 `SCHOLAR_WORKFLOW_HOME`。
测试池和个人池分开。页面认证信息和服务记录只用于当前本机服务，不能作为长期知识链接。

## 现有论文来源和配置

| 来源 | 提供的内容 |
|---|---|
| Semantic Scholar Recommendations | 与人提供或已核实 Zotero arXiv 种子相关的论文 |
| Scholar Inbox | 已配置且会话可用的个性化推荐 |
| S2 作者关注名单 | 已登记研究者的新论文 |
| Hugging Face Daily Papers | 社区提交论文及投票数据 |

原聚合器继续作为候选来源，返回元数据和未成功来源的诊断。它不会自动产生通用提交格式，
也不会自动入库或证明已阅读全文。译文须依据完整权威摘要，不能用摘要片段代替。

全局配置为 `~/.config/scholar-workflow/recommend.yml`，可选项目配置为
`~/.config/scholar-workflow/projects/<cwd-name>.yml`。
可按需使用[配置示例](references/recommend.example.yml)。项目兴趣和作者关注名单在全局值上追加，
其他键覆盖。Scholar Inbox 会话保存在配置和 Git 之外；不可用时跳过该来源并说明。
各来源现有网络代理方式保持。旧 `notebooklm_classification` 配置会被忽略，不需要 NotebookLM。

关注作者时，先确认实际 Semantic Scholar `authorId`，重名时消歧，再更新关注名单。

## 平台热度与无摘要资料

有已核验GitHub/HF对象链接时，提交可使用`submit --refresh-metrics`采集原始数值；
已有候选使用卡片“更新热度”或`refresh-metrics --candidate-id <id>`。
页面显示具体对象及采集时间，失败保留旧值，未知不填零；HF点赞与GitHub stars分开标识。
无作者摘要时，依据实际正文提供`summary_zh`和`summary_sources`，明确标注agent总结并审阅后交接。
相关Blog继续通过灵活`links`附上。完整约定见[推荐入口](../../references/recommendation-intake.md)。
