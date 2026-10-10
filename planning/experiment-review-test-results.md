# 实验复核开发评价结果

## 2026-10-10 多变量与未解析配置补充检查

只复制原项目为两个一次性合成raw根，先冻结根外EXPECTED，独立执行者只读两根及
runtime skill/必读refs，各返回五节报告。没有修改skill来适配预期，没有运行配方、
解析器、产品命令、网络或GUI，也不把会话报告写入Vault。

- A：Run.config合法绑定各自inputs/resolved-config.json；十字段差异完整显示，
  其中choice是标记、另九项为模型/训练设置。主表突出少量关键值并链接快照，详细表
  列choice、层宽、激活、dropout、优化器、学习率、weight_decay、batch_size、epochs、
  augmentation。记录目的来自原报告/notes；三项后来变化的当前configs值另表呈现，
  没有拿当前dropout/学习率/轮数替代快照，没有单因素因果结论。
- B：配置hash合法但unresolved，缺失共同include及各自override共三文件；目的未记录，
  模型/训练参数未知。报告保留所选0.80/0.85比例及全部四执行历史，不建立有效配置
  效果差值/排名，不借用A参数或执行配置以补全。
- 两例时间、primary选择、失败缺值非0、replay非独立重复、来源链接及合成未执行边界
  均保留。原33文件、A的35文件、B的33文件在评审后逐文件manifest摘要全等。

raw目录仅用于可丢弃的开发输入，不是持续审阅资料。目录分别为
/tmp/scholar-experiment-config-cases.rIQOWv/case-a和case-b，根外EXPECTED记录输入构造、
十字段/共享条件及全量hash算法；完整agent报告在本轮会话留证。原项目文件集digest为
04db630b0f43b0766e6f2689e2d613eb2c32cbf5cbf62e46b7b1b1d2fbbeedd8，A为
8c7ee0909849fd03b369de4651ee18a7cebf445a8022fc2083cdd18b93fa17d2，B为
65cabd652ac13a41714e670023cb80ac4925335e5de672dd31ea8fcb1f052f31。
这两项限定行为评价符合预期，不是普遍鲁棒、真实科学或VS Code/人工可读性认证。

## 2026-10-10 对比表规范的单项目正向检查

沿用原合成项目，不生成新的业务数据；先按raw记录在EXPECTED补充时间、缺失目的、
配置值及行级来源预期，再由未读取预期/旧结果的独立agent使用当前开发版skill。
报告仅在会话返回，未保存候选、运行配方或打开应用。本节是开发行为评价，不是安装态。

| 检查对象 | 实际返回 | 结论 |
|---|---|---|
| 主表字段与选择 | 两行primary，均有名称、记录时间、目的、配置值、指标及执行/config/report来源链接 | 符合本例预期。 |
| 时间 | baseline为2026-10-09 UTC 10:03–10:04；variant为11:01–11:02 | 未用配方创建/成果保存时间替代。 |
| 目的与配置 | 目的均未记录；choice=baseline/variant直接显示，共同seed=7单独说明；两config已读并核对配方摘要 | 未把审阅目标编造成实验目的，未冒称真实运行配置。 |
| 结果与执行历史 | 比例0.80/0.85，描述性差值5个百分点；另表四Attempt，失败无分数，replay不计独立重复 | 符合原事实与本次表格规范。 |
| 输入与权限 | project目录对HEAD无diff或未跟踪文件；两config摘要、两metrics摘要/340字节与声明一致 | 原33文件未改；没有安装/发布/GUI/Vault操作。 |

报告保留五节、合成/未执行与备份未验证说明。其完整原文已在本轮独立agent会话留证。
本例仅覆盖少变量和缺失目的；多变量展开、已记录目的、真实VS Code导航/外观及人工
评鉴不据此放行。既有四隔离负例不重跑，旧结果不覆盖；整体outcome继续pending。

## 范围与当前结论

2026-10-09，独立`codex/hotfix-knowledge-ownership`开发树。
新增只读review-experiments和共享末端契约；没有新增CLI/schema/状态库，
没有运行真实实验、整库业务或改已认可的论文输出。完整G17仍未完成。

独立预期和raw fixture先于skill评价准备。raw project为一个合成项目的2Run/4Attempt，
共33文件。记录、时间、状态、指标全部手写，不是实际运行的科研成果。
预期唯一见tests/fixtures/experiment-review/EXPECTED.md，输入和范围见独立test-plan。
评价agent只得到raw project和runtime skill/必需reference，不读取EXPECTED或planning。

## 确定性检查

| 检查 | 实际结果 | 证明边界 |
|---|---|---|
| 合成fixture格式、输入/Target/Artifact字节身份、失败与重放历史 | 5项通过 | 核对手写输入，不证明host skill行为或科学结论。 |
| eval JSON结构 | 10项通过 | 不自动判定路由、拒绝行为或结果正确性。 |
| 既有实验生命周期和可移植示例回归 | 59项通过 | 各自隔离测试对象，不重跑真实实验。 |
| 上述联合 | 74项通过，10.15秒 | 非完整发布回归、安装态或人工验收。 |
| Skill入口、改动测试文件Ruff、diff | 通过 | 不证明报告事实或可读性。 |
| 样张静态本地链接 | 32链接／30不同目标均存在 | 不是阅读器逐项点击。 |

主要联合命令：

```text
rtk proxy uv run --offline --with pytest python -m pytest tests/contract/test_experiment_review_fixture.py tests/unit/test_evals_schema.py tests/contract/test_experiment_lifecycle.py tests/unit/test_project_reproduction.py -q --tb=short
```

首次15项检查已通过，但pytest对parametrize的zip迭代器发出弃用警告；仅将测试参数
改为显式列表，随后74项无警告通过。首次系统python运行skill校验缺yaml而退出1，
改用已有项目uv解释器后通过，没有新增依赖或改产品。两者不是业务产品缺陷。
独立评价完成并更新eval描述后，5项fixture与10项eval结构联合复核15项通过（0.10秒），
diff检查通过，原33文件集/hash再次相同；没有重跑59项未改动的既有回归。

## 独立正向评价

第一版正确选择两Run各自primary/明确artifact，0.80/0.85及0.05比例／5个百分点
正确；四Attempt、失败缺值非0、同Run重放非独立样本、合成/未执行和备份未验证
均保留。逐次读取核验size/hash，明确不冒称原子快照或真实科学效果。

第一版遗漏两份Run原始report.md导航入口，故末端格式不是首轮全通过。
一次定向格式修复只补两个入口，不读新业务数据、改变判定或获知EXPECTED；修复后
报告保留全部要求。未读报告正文的事实明确标注，链接不冒充证据核验。
未因这次遗漏增加新服务或另一份状态账本，也未伪称已证明多次鲁棒执行。

可见样张在experiment-review-demo.md：按独立报告事实压缩宽表、重定位相对链接；
人类外观及实际导航独立待验，不是原始记录或科研真源。

## 独立负向评价

只用四个一次性隔离副本，不修改原33文件。semantic案例刷新所选artifact实际size/hash；
conflict案例保留故意错配。缺条件副本最初config/report残留protocol，已在评价前
删除并刷新config/recipe hash；这属于测试输入纠偏，不算产品缺陷。

四份完整报告已返回并按独立预期核对，均含五部分、两个Run与全部四Attempt、条件、
来源链接及合成/未执行边界，没有best/last替代、远端下载或记录修复。

| 隔离输入 | 实际报告行为 | 本次判断 |
|---|---|---|
| 缺unit/protocol | 保留0.85无单位；不从基线继承。日志残留协议与config/metrics/report不一致也显式报告；不输出有效差值/排名。 | 预期行为通过。 |
| 缺value | 所选结果显示未记录，不记0；日志0.85不填入所选指标；不计算差值。 | 预期行为通过。 |
| manifest-only | 所选成果本地证据不可用；旁边0.85本地文件仅未绑定旁证，不能替换，不下载。 | 预期行为通过。 |
| 来源与hash冲突 | wrong-owner无Attempt与全零hash不匹配分别报告；文件0.85明确未核验，不编造第五条Attempt或修复。 | 预期行为通过。 |

这是四个限定输入的一次独立host行为评价，不是可执行CLI安全门、普遍鲁棒证明、
安装态或人类外观通过。完整agent报告已在本轮会话留证；一次性负例不是长期知识资料。

## 文件与授权边界

正向评价期间两次文件集/SHA-256观测均为同33文件、相同字节，独立agent操作审计
为有界读取、枚举和标准hash计算。未执行配方、记录命令或索引重建，未访问网络/Git/
外部应用，未写raw project。负例操作只限各自隔离副本的读取。

未提交、发布、安装、合并main、切服务或写真实Vault/项目/Zotero。
此前已认可的正文/Canvas/图片/折叠格式保持，不重开其验收。
新的报告可读性、实际导航、安装态和完整G17继续各自待验。
