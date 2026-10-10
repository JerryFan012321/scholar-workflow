# 实验比较样张（合成输入）

## 摘要与范围

选定结果为 **baseline：0.80；variant：0.85**，单位均为比例，越高越好。
字面差值为 **0.05，即 5 个百分点**。这些数字来自手写合成输入，不能据此宣称
真实方法改进、排名或显著性。材料整理完整，真实效果比较仍未建立。

本样张整理独立 agent 的只读报告，缩窄表格并将链接重定位到当前文件；不改变事实。
[项目说明](../tests/fixtures/experiment-review/project/README.md)明确所有状态、时间、
分数和执行观察都是合成记录，没有运行实验。外观及实际导航仍待人工评鉴。

| 所选 Run | 所选 Attempt | 所选指标成果 |
|---|---|---|
| `20261009-1000-baseline` | `primary` | `art_1111111111111111`，accuracy |
| `20261009-1100-variant` | `primary` | `art_2222222222222222`，accuracy |

同时保留 baseline 的失败和重放历史，不把它们包装成另外两个实验方案。

## 比较条件

| 条件 | 两条 Run 的记录 | 核验与边界 |
|---|---|---|
| 数据 | `synthetic-review`，版本 `1`，`fixed-test` | 引用同一[数据清单](../tests/fixtures/experiment-review/project/dataset/synthetic/metadata/manifest.json)，文件哈希匹配；只有合成标识，没有真实数据。 |
| 指标 | accuracy，比例 `[0,1]`，越高越好 | 两份选定指标显式声明单位、范围和方向；计算公式、分母和汇总方式未记录。 |
| 协议 | `synthetic-eval-v1` | 标识一致；具体评测过程未记录，指标明确声明未执行。 |
| 配置 | `choice: baseline` → `choice: variant` | [基线配置](../tests/fixtures/experiment-review/project/configs/baseline.json)与[变体配置](../tests/fixtures/experiment-review/project/configs/variant.json)各自匹配配方哈希；choice对应的真实算法未说明。 |
| 种子 | `7` | 声明相同，不是随机过程的执行证明。 |
| 环境 | 同一[合成环境](../tests/fixtures/experiment-review/project/env/synthetic.json) | 文件哈希匹配；Python为占位值，实际OS/GPU/驱动/CUDA/Python未记录。 |
| 源码与入口 | 相同占位提交、相同入口 | [基线配方](../tests/fixtures/experiment-review/project/experiments/20261009-1000-baseline/run.yaml)与[变体配方](../tests/fixtures/experiment-review/project/experiments/20261009-1100-variant/run.yaml)一致声明占位提交，不是核验过的Git版本；入口只读未执行。 |
| 执行Target | `synthetic-local`，项目根`.`，输出根`experiments` | 使用Attempt的[基线Target快照](../tests/fixtures/experiment-review/project/experiments/20261009-1000-baseline/attempts/primary/target.yaml)及[变体Target快照](../tests/fixtures/experiment-review/project/experiments/20261009-1100-variant/attempts/primary/target.yaml)，内容相同且匹配各自记录哈希；不是实际主机核验。 |

两条配方均声明冻结；Attempt的实际源码提交与实际配方哈希为空。
记录声明相同，不代表真实执行条件已核验，也不保证比较具有科学效力。

## Run 结果

| Run／Attempt | accuracy | 本地证据 | 可比性 |
|---|---:|---|---|
| baseline／primary | 0.80，比例 | metrics角色、primary来源和Run身份一致；实际340字节、SHA-256匹配清单，并与Attempt输出逐字节相同。 | 可描述合成数值差；真实效果未建立。 |
| variant／primary | 0.85，比例 | metrics角色、primary来源和Run身份一致；实际340字节、SHA-256匹配清单，并与Attempt输出逐字节相同。 | 可描述合成数值差；真实效果未建立。 |

| Run | 配方 | 原始报告 | 成果清单 | 选定成果 | Attempt输出 |
|---|---|---|---|---|---|
| baseline | [打开](../tests/fixtures/experiment-review/project/experiments/20261009-1000-baseline/run.yaml) | [打开](../tests/fixtures/experiment-review/project/experiments/20261009-1000-baseline/report.md) | [打开](../tests/fixtures/experiment-review/project/experiments/20261009-1000-baseline/artifacts.yaml) | [打开](../tests/fixtures/experiment-review/project/experiments/20261009-1000-baseline/artifacts/metrics.json) | [打开](../tests/fixtures/experiment-review/project/experiments/20261009-1000-baseline/attempts/primary/metrics.json) |
| variant | [打开](../tests/fixtures/experiment-review/project/experiments/20261009-1100-variant/run.yaml) | [打开](../tests/fixtures/experiment-review/project/experiments/20261009-1100-variant/report.md) | [打开](../tests/fixtures/experiment-review/project/experiments/20261009-1100-variant/artifacts.yaml) | [打开](../tests/fixtures/experiment-review/project/experiments/20261009-1100-variant/artifacts/metrics.json) | [打开](../tests/fixtures/experiment-review/project/experiments/20261009-1100-variant/attempts/primary/metrics.json) |

原始报告链接仅供导航，独立评审未读取其正文，不把它当作本次数值判定依据。
两个成果均为本地必须保留；备份仍未验证。本地字节匹配不是执行、promotion操作
发生或备份可恢复的证明。

## Attempt 历史

以下时间是合成的2026-10-09 UTC记录；状态不是实际进程执行证明。

| Run | Attempt | 状态／退出码 | 时间 | 含义与入口 |
|---|---|---|---|---|
| baseline | [wrong-cwd](../tests/fixtures/experiment-review/project/experiments/20261009-1000-baseline/attempts/wrong-cwd/attempt.yaml) | 失败／2 | 10:01–10:02 | 工作目录错误、未产生指标；[错误日志](../tests/fixtures/experiment-review/project/experiments/20261009-1000-baseline/attempts/wrong-cwd/stderr.log)。缺失不是0。 |
| baseline | [primary](../tests/fixtures/experiment-review/project/experiments/20261009-1000-baseline/attempts/primary/attempt.yaml) | 成功／0 | 10:03–10:04 | 明确选定的0.80结果；[日志](../tests/fixtures/experiment-review/project/experiments/20261009-1000-baseline/attempts/primary/stdout.log)。时间在失败之后，但未记录重试父关系。 |
| baseline | [replay](../tests/fixtures/experiment-review/project/experiments/20261009-1000-baseline/attempts/replay/attempt.yaml) | 成功／0 | 10:05–10:06 | [重放日志](../tests/fixtures/experiment-review/project/experiments/20261009-1000-baseline/attempts/replay/stdout.log)及[指标](../tests/fixtures/experiment-review/project/experiments/20261009-1000-baseline/attempts/replay/metrics.json)；与primary指标字节相同，不是独立Run或统计重复样本。 |
| variant | [primary](../tests/fixtures/experiment-review/project/experiments/20261009-1100-variant/attempts/primary/attempt.yaml) | 成功／0 | 11:01–11:02 | 明确选定的0.85结果；[日志](../tests/fixtures/experiment-review/project/experiments/20261009-1100-variant/attempts/primary/stdout.log)。 |

[wrong-cwd Target](../tests/fixtures/experiment-review/project/experiments/20261009-1000-baseline/attempts/wrong-cwd/target.yaml)
和[replay Target](../tests/fixtures/experiment-review/project/experiments/20261009-1000-baseline/attempts/replay/target.yaml)
也分别匹配记录哈希；同一Target声明不能消除wrong-cwd记录的实际目录差异。
[基线备注](../tests/fixtures/experiment-review/project/experiments/20261009-1000-baseline/notes.md)
与[变体备注](../tests/fixtures/experiment-review/project/experiments/20261009-1100-variant/notes.md)保持原样。

## 差异与限制

可核对的是配置choice及合成数值不同；没有证据把差值归因于真实方法变化。
所选文件、身份、大小和哈希未发现冲突，但缺少真实数据、执行事实、源码/环境核验、
accuracy定义和完整评测过程。因此不输出真实效果排名、显著性、置信区间或生产适用性。

文件分次读取，不宣称文件系统原子快照。可读性和来源链接尚未在阅读器中逐项验收。
若要研究效果结论，需要另行提供真实执行及评测证据；本次只读整理不自动补跑。
