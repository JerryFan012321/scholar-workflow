# 项目/实验复现能力：独立测试方案

范围：新增 init-project 便携示例 assets 和 example_project.py；版本 0.33.0。
安装态示例与开发测试分开；不重做已有效的 V-JEPA2 正文/Canvas、整库或正式迁移。

## 固定输入与手写预期

- 新目的地、祖先不在 Git 中；四数 `1,2,3,4`；预期 count=4、sum=10、mean=2.5。
- 空目录不等于允许覆盖，示例 apply 只接受不存在的目的地。普通项目 initializer 的幂等行为不改。
- plan 不写文件；apply 只生成骨架、模板与明确本地资料清单，不提交、不运行、不联网。
- 目标或祖先 symlink、已有目标、祖先 Git 均拒绝且不得新增/改写任何项目内容。
- 模板不包含私人路径、账号/附件 ID、token、固定端口、虚构论文或科学结论。
- 没有 Git commit 时 replay 拒绝建正式 Run；完成显式本地源码 commit 后才能执行。
- 一次真实 wrong-cwd 失败，两个成功 Attempt；成功输出等于独立 expected.json 且逐字一致。
- promotion 成果 hash 与源输出一致，backup=not-verified；机器记录与人类报告分开。
- 已有 Run 重放拒绝，原文件 hash 不变；改变输入 manifest 拒绝，不覆写用户内容。
- 只读 overview 的外部可用性不能当科学内容证明；模板只关联示例自己的源码/实验/成果。
- 普通系统 Python 不需要 pydantic；helper 使用已安装 console entry 的产品 Python 调初始化器。
  CLI 不可用或 launcher 无法识别时，在创建目标之前诊断，不猜测源码环境或自动安装依赖。

## 执行与证据

1. 定向单元/公开脚本测试：临时合成根、symlink/祖先Git/已有目录、无提交和输入冲突。
2. 普通 unit/contract 完整回归、两脚本 Ruff、skill frontmatter、diff 空白检查；无真实业务写入。
3. 复核相关 routing/safety/outcomes；行为评鉴不能由 schema 测试冒称通过。
4. hotfix 提交并正常发布安装后，使用安装缓存的 plan/apply 创建一个新独立 canary项目。
5. 仅提交该新示例明确源码；执行公开 replay，保存真实CLI身份、结果与命令返回。
6. 新克隆同一源码、安装器补目录后再次执行，比较 ID、配方和结果；不复制旧实验。

可见成果：示例 README、资料清单、实验 report、失败日志、成功成果、重放说明、独立验收记录。
人工评鉴仍需明确确认：资料入口是否方便、报告是否可读。新安装不代替这个确认。
回退点：已安装 0.32.3 / runtime c0fa2000a7b8d56a841bc753be12d5f3898e7114。
