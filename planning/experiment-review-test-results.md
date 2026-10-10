# 实验复核开发评价结果

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
