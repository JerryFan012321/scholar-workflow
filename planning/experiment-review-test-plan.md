# 实验审阅独立测试计划

## 状态与边界

2026-10-09：先准备手写预期和合成输入，未执行测试或实验。
本切片只评价 `review-experiments` 的只读流程与人类 Markdown 末端结果，不新增
CLI、schema、状态台账，不改已有论文输出，不发布安装，不读取真实项目或 Vault。

独立预期唯一位于 `tests/fixtures/experiment-review/EXPECTED.md`；原始输入放其
`project/` 下。独立评审 agent 只获得 raw project 与运行期 skill/结果契约，不能读取
EXPECTED 或本文。后续实际结果单独记录，不能把夹具准备记为通过。

## 输入与手写预期

- 两个合成 Run、四个 Attempt，按现有 Run/Attempt/Target/Artifact 格式手写；
  不调用初始化、create_run 或 experiment 命令生成档案。
- baseline：wrong-cwd 失败、primary 成功、replay 成功；两次成功指标均为 0.80。
- variant：primary 成功，指标 0.85。选定的是两 Run 各自 primary，不是最高分或最新。
- 同 synthetic 数据 manifest/fixed test split、同 seed/env、相同 `synthetic-eval-v1`；
  指标 JSON 明示 fraction、范围、方向；配置的 choice 明示不同。
- 预期描述差值 0.05 fraction / 5 个百分点，保留 failed 和 replay；不推断显著性、
  独立重复实验或真实科研效果。合成 commit 不冒充核验过的 Git 版本。
- 提供可解析的 report/notes、配置、数据 manifest、环境、指标与 Attempt Target
  snapshot。文件 size/hash 按实际夹具字节填写，只做文件身份记录，不执行计算实验。

## 评价步骤（准备后执行，结果另记）

1. 评价者先记录 fixture 文件字节基线和明确的两个 Run/primary 选择。
2. 独立 agent 仅阅读 raw fixture 与 runtime 契约，在会话返回中文或英文统一的
   Markdown 审阅，不修改项目、不运行实验、不访问网络或 Git。
3. 按独立 EXPECTED 核对选择、单位/条件、差值、四 Attempt、来源链接、合成与
   科学结论边界；复核 fixture 字节保持。需要人评的可读性在会话明确展示并保持待评。
4. 必要负例各用隔离副本，定向移除单位/protocol/指标，或改为远端 artifact/制造
   身份矛盾；不静态造第三 Run，不扩大为框架。缺条件必须 unknown，缺指标不当 0，
   远端不下载，不自动 best/last。实际测试范围变化先更新说明。

可见产物：一份两 Run 的结果审阅、完整 Attempt 解释、可点击资料来源和诚实限制，
另有实际检查结果。它是 G17 上层组合切片，不代替完整四类交付或安装态/人工验收。

## 实际执行范围说明（2026-10-09）

准备完成后开始离线开发评价：一个不知道EXPECTED的独立agent仅读33文件raw project，
按新skill返回中文报告，不写文件、不启动工具。根agent按独立预期复核，并记录前后
fixture文件集/hash；未把真实项目/训练执行当测试。

确定性检查包括5项fixture格式/字节身份/Attempt历史、10项eval结构和59项既有实验
生命周期/可移植示例回归，共74项；后两者仅使用各自隔离测试对象，不操作真实资料。
另外运行skill入口校验、改动测试文件Ruff及diff检查。这些检查不判断报告科学或外观。

负例只在一次性隔离副本：缺unit+protocol、缺value、remote-only、source Attempt/hash
冲突，各保持明确同一结果选择。semantic案例刷新成果字节声明，冲突案例故意不刷新；
独立agent只得到各副本和skill，不读EXPECTED。通过标准仍以先写的预期为准。
全部网络/执行/修复/索引重建被禁止。测试产物先返回会话；选定报告由根agent另保存
到planning作为开发样张，正式项目/Vault不写。
