# 推荐热度、总结与附件修复：源码结果

日期：2026-11-08。候选0.51.1，分支codex/hotfix-recommendation-metrics，基于已发布0.51.0。
范围仅为平台原始计数、缺值/失败显示、来源明确的无摘要总结、灵活附件和必要的并发锁初始化修复。
不包含待入库清单生命周期、共用文风Skill或原工作树Notion等未发布内容。

## 结果

- 热度放在卡片标题/标签后、正文前；支持GitHub stars与HF model/dataset/Space likes。
  无数据明确显示未采集；无已核验平台地址明确显示缺项。每卡可受控刷新，CLI支持显式补采。
- 独立平台观测不增加推荐次数；刷新保留摘要、总结、人工审阅/选择与原提交归属。
  限流或请求失败保留上次成功值及其时间，不填假零，不猜测仓库，不下载代码或模型。
- 无原摘要可用summary_zh + summary_sources提供明确标为agent整理的总结。
  有作者摘要缺译文仍需译文；Blog明确提供的总结优先显示，原始简介继续可展开。
  当前总结或依据变化后重新审阅；已有完整原摘要译文保持优先。
- 附件沿用现有自由kind/label/url链接。相关Blog按实际情况附上，不规定数量或固定栏目。

## 分项证据

| 检查 | 结果 |
|---|---|
| 初始推荐相关检查 | 136通过，1并发失败；原日志保留 |
| 并发诊断 | 捕获原os.open的FileNotFoundError/errno2；排他创建后打开现有锁，权限/NOFOLLOW/flock不变 |
| 修复后的推荐相关检查 | 138通过，4.70秒，含独立锁竞争fixture及原多进程提交 |
| 完整unit/contract | 4207通过、22跳过、11既有警告，224.01秒 |
| 全量之后的最后Blog优先级调整 | 推荐相关138通过，4.69秒；过期UI预期的两次失败均保留，未放松审阅门禁 |
| 公开API小元数据 | GitHub与HF各一项成功，仅公开计数；非正式推荐，不写个人池 |
| JavaScript | node语法检查与实际app.js的16个合成DOM场景通过 |
| 文件边界 | 两manifest/包版本0.51.1一致，runtime改动无个人路径/代理端口/疑似凭据；git diff --check通过 |

上述完整回归发生在最后Blog优先级调整之前；后者已独立覆盖当前总结显示、原文保留及审阅/选择保护。
不将不同快照的检查冒称同一次最终全量。源码与模拟DOM通过不证明安装态或人工GUI评阅。

原始回执只在test Vault：Scholar Workflow 实验/推荐热度与总结修复-20261108/_work。
包括targeted-results.xml、final-targeted-results.xml、full-results.xml、final-results.xml、
public-api-probe.json及对应日志；pytest basetemp有GIT_CEILING_DIRECTORIES隔离。

## 发布/安装边界

2026-11-09用户明确批准发布、安装及更新正在使用的推荐页，现已完成。
源码06faf41816aec0a4561a104fc17e26fbdd80246e与runtime
d6ce02c3cef0bb529cefd8dc5573d82f188b6b5b已原子推送；main未合并。
正常pipx安装的两个CLI、Codex/Claude插件均为0.51.1；两宿主各346个runtime文件与发布blob完全一致。
安装后的单个test合成Blog对象通过总结/附件、审阅选择保留及公开计数刷新检查。
日常服务已从0.51.0受控停止并以0.51.1启动，build ca24e98313b7fa29，HTTP 200；
全部13候选的正文、revision、审阅、选择及推荐归属保持相同。3个已声明GitHub目标刷新成功，
其他对象不猜测平台地址。页面打开返回queued，视觉评阅仍待用户确认。
机器回执见test对象_work/installed-release-receipt.json及installed-0511/receipt.json。
未写Zotero或正式知识库。保留上版runtime回退点
83a5e1c3002f199d3440d46c8c12064fd2c4f7f0。
