# 0.31.1 hotfix：提交、发布、正常安装与 test Vault 验收

日期：2026-10-02。用户已批准本方案，并要求 V-JEPA 2 文档包使用新文件夹、保留旧稿。
分支：`codex/hotfix-project-context`。不合并 main，不启停 Hub/worker。

## 发布前回归：只证明提交候选的代码安全性

输入为当前版本化源码、tests/unit、tests/contract 及合成 fixtures；新增摘录测试也在范围内。
不使用真实 Vault/Zotero/Notion，不运行整库业务操作。

```sh
rtk proxy uv run --locked pytest tests/unit tests/contract -q
```

预期：完整 unit/contract 通过，旧分析与摘录兼容、安全/冲突检查不回归。
影响只限开发环境、缓存及 pytest 临时文件；没有安装态业务验收。
失败先报告，不改变输入或静默扩展修复/测试范围。依赖缺失需要联网时另行说明。
随后按批准范围检查发布文件的个人路径/密钥泄漏、版本一致性及 diff 空白问题。
可见产物是独立结果记录，包含实际命令、退出码、计数、警告和失败原因。

## 提交、发布与正常安装

回归通过后，提交本能力批次的源码、运行文案、测试输入与规划状态；生成预览和截图不作为
运行文件发布。不删除或覆盖既有未提交文件。使用独立临时 clone，从确定的 hotfix 提交调用
仓库 make-release.sh；检查 runtime-only 文件清单后推送 hotfix 与 release，不合并 main。

Codex 插件通过 jerry-plugins 的正常 marketplace 更新/安装入口更新，pipx CLI 从确定的
runtime release 提交正常安装，不能从脏源码目录构建产品安装。核对两份 manifest、CLI
包版本、实际导入路径及 release/source SHA；不手改插件缓存，不使用 editable 或临时 venv。

旧版本回退基线：0.31.0 release `199792dee442df4d60da98c19d2e365b3d096ed4`。
若需回退，用正常安装指定该提交；不擅自执行回退。安装不是业务测试通过，也不解除人工评鉴。
新技能的宿主自动加载按实际安装状态核实；当前会话若仍持有旧技能，不冒称新插件已生效。

## 安装后：只在 test Vault 使用实际安装插件

对象只有现有 `Scholar Workflow 实验/V-JEPA 2/v4-审议候选/` 内的 IR、Markdown、Canvas、sidecar。
不运行该目录内旧 build 脚本，不重新分析论文，不新增批注，不读取 ZotFlow 密钥，不写正式 Vault。

1. 从安装缓存读取 0.31.1 的 SKILL 和 reference；实际运行仅用正常 pipx 已安装包。
   禁止源码导入、PYTHONPATH 指向仓库或复制源码模块作为测试实现。
2. 对上述四文件做只读成对校验，记录实际 findings；检查前后内容 hash 不变。
   预期旧 v4 文档包仍可校验，不能把四分支兼容通过写成新版格式通过。
3. 按已安装 check-consistency 的交互呈现契约，只针对本对象汇报范围、问题、证据、建议与
   覆盖缺口。不检查其他对象或整库；没有核实的来源/科学论点明确列为未检查。
4. 在 test Vault 新增唯一目录 `Scholar Workflow 实验/V-JEPA 2/0.31.1-hotfix-验收/`，仅放人类可读验收
   报告与必要的结构化结果；重名则拒绝，不覆盖。报告记录安装身份、真实观察与未实现功能。
   Obsidian CLI 显式选择 test Vault 打开报告和现有 Canvas；不使用最近活跃 Vault 默认值。
5. 当前代码缺少 Experiments role 和独立子节点，最新五分支格式记为「未实现／未通过」，
   不手写新 Canvas、不创建不合格 canonical 分析、不用旧样张或旧测试冒充支持。

新报告的写入属于用户要求的 test Vault 实验，不是正式 Field 注册、迁移或同步。
若文件系统不允许写该 test 目录，按正常权限流程请求所需窄授权，不改用 tmp 展示结果。

## 需要用户人工评鉴

实际报告生成后，在会话明确给出打开位置，请用户判断：范围与结论是否清晰、每项问题是否
有证据和可操作建议、未检查/未实现是否醒目、是否有机器元数据淹没正文。
无需重复已通过的旧 Canvas 全套审美/跳页验收。最新五分支样张尚不存在，本次不能验收它。

每阶段分别记录：回归、提交、发布、安装、安装态测试、人工评鉴。任一未执行或失败不标 pass。
