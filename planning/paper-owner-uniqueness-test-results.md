# 登记前唯一归属：独立回归结果

2026-10-09。当前为开发实现与定向验证；未发布或安装新版本，完整归属能力仍未完成。
输入和手写预期先于产品改动，见`paper-owner-uniqueness-test-plan.md`及
`tests/fixtures/paper-owner-uniqueness/EXPECTED.md`。

## 实际结果

| 轮次 | 结果 | 意义 |
|---|---|---|
| 初始13项 | 12失败、1通过，0.46秒 | 其中2项在夹具构造时被旧receipt/catalog不一致校验拒绝，不能记为产品漏洞 |
| 修正合法旧式声明夹具后13项 | 12失败、1通过，1.59秒 | 12项均明确为本应拒绝而未抛异常；只有跨Source不同文库预览通过 |
| 加入3项独立正反对照后16项 | 13失败、3通过，0.51秒 | 新增同Source跨文库正例暴露key-only误拒；未变条件恢复和人工编辑保护通过 |
| 新增测试文件Ruff | 通过 | 未改产品或放宽断言 |
| 外部读集/完整身份初次实现16项 | 16通过，0.44秒 | 仅覆盖原独立预期；不证明可信空Source初始化 |
| 追加边界后28项 | 4失败、24通过，0.79秒 | 其中2项是测试receipt格式/锁helper目录前置条件错误，不记产品缺陷 |
| 修正上述夹具后28项 | 3失败、25通过，0.76秒 | 明确暴露kind矛盾、前导零文库、committed目标内重复检查遗漏 |
| 对应最小修正后28项 | 28通过，0.77秒 | 保留跨文库正例、CAS、恢复、同字节替换/根漂移拒绝及锁排序 |
| 必要既有回归159项 | 159通过，2.68秒 | paper_registration、knowledge_registration_cli、knowledge_ownership、knowledge_rebinding、canvas_registration |
| 本次实现与测试Ruff | 通过 | 不改格式、版本或安装 |

上述秒数为pytest报告，不包含环境准备，不将多轮重跑算作更多独立用例。
两个旧式声明夹具显式移除注册receipt，模拟允许无receipt的既有导入声明；
没有伪造receipt或生产历史，没有因夹具失败修改产品验证器。

## 实现前证明的缺口（历史）

- 不同Source可为同一已声明Zotero论文提出第二owner计划。
- 旧ID缺文库证明、规范ID与item声明矛盾、外部provider不可读/缺失或Source不可用时，
  现有plan仍忽略外部声明并放行，不能证明全体唯一。
- 同一Source内仅按item key判重，会把明确不同文库中的同key论文误拒。
- 其他Source声明在preview后、journal恢复前或两个发布成员之间变化，现有apply未绑定/复核它。

不是每个失败一项独立生产事故；这里是13个合成失败用例，归纳为上述行为缺口。

## 保留的有效行为

- 跨Source且明确不同文库的同key预览零写入，身份为`paper:zotero:456:ABCD2345`。
- 外部声明未变时，中断事务可恢复至固定目标`resources/papers/new-owner/Paper.md`。
- 目标半成品被人工修改时，已有CAS保护拒绝覆盖并保留字节；后续修复不得破坏它。

## 当前影响与下一步

`workflows/register_paper.py`已补规范身份、外部注册Source声明读集、排序provider锁、
逐成员/恢复/完成重放复核；读集包含内容hash及文件/根identity，不能只靠同字节hash放行替换。
没有新增owner库。测试、EXPECTED和开发记录同步；`references/`、`skills/`、`contracts/`
当时尚无差异；后续已同步相关运行reference和配置说明，contracts/及论文格式保持。
没有真实Vault/Zotero/项目写入、网络、论文分析、实验、安装或服务切换。
当前正常安装仍0.42.0，不把开发测试当安装态证据。PROJECT/literature候选的评鉴独立保持。

后续同一切片已在既有公开Source登记入口组合空provider、Field与registry的可恢复事务，
移除selected missing-as-empty旧fallback；历史或已attach Source不猜空。独立27初始化
及1项真实spawn双进程用例通过：两个合法预览同时申请同一论文，恰1成功/1拒绝，
只产生一个owner/目录/导航，失败方与原件保持。最终225项联合定向检查通过（4.27秒）；
独立Source初始化结果与失败记录见source-inventory-initialization-test-results.md。
这不是压力测试或安装态证据。正常安装仍0.42.0，Field引用写入及完整G17继续未完成。
