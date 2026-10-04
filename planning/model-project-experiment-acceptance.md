# 模范项目与实验：独立验收输入

范围：安装版 0.32.3；一个全新独立 Git 项目；不执行论文代码，不触碰已有业务项目。

## 输入与预期

- 数据固定为 `1,2,3,4`，配置为求和及均值，不随机、不联网、无第三方计算依赖。
- 预期 JSON：count=4、sum=10、mean=2.5；重复执行的结果字节与 SHA256 一致。
- 配方源码在新示例 Git 中本地提交，不 push；数据、docs、experiments 依初始化器规则本地优先。
- 使用安装插件内 `init_project.py plan/apply` 建骨架；同选项 rerun 不改变 project_id 或已有文件。
- 通过已安装公开 `experiment` 命令建立 Run/Target/Attempt，记录真实执行 cwd、日志与退出码。
- 故意从 Attempt 子目录启动同一配方：无法找到相对脚本，实际非零退出，记 failed；修正 cwd 后记 succeeded。
- 两个成功 Attempt 的输出相同；metrics promotion 校验副本 hash，但 backup 必须 not-verified。
- 资料清单包含实际代码、论文稳定身份、实验报告和成果。外部论文链接保持 unverified，不伪造可用性。

## 操作与影响

1. 检查目标不存在且不受祖先 Git 管理，安装器 plan，再 apply。
2. 在新目录准备源码、输入、手写预期和复现入口；仅本地提交明确新增源码清单。
3. 创建一个 Run、一个本机 Target、三个 Attempt，执行及记录失败/成功/重放。
4. promote、validate、index；保存真实 stdout、日志和单独验收记录。
5. 重跑初始化 plan，核对 ID、冻结配方与结果 hash。通过公开 overview 展示材料清单。
6. test Vault 仅新增一个展示目录；人工评鉴打开方式、材料组织与可读性，不改原 V-JEPA 2 pair。

预期可见产物：独立项目 README、项目资料清单、实验报告、三个 Attempt、promoted metrics、
复现说明与输入、test Vault 展示笔记。失败必须保留诊断，不自动修饰为成功。

本次不测试：整库迁移、论文科学事实全量审议、真实训练、远端执行、真实备份或原生工具 GUI。
