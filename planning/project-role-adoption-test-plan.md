# 已有项目角色声明接入：独立验证方案

日期：2026-10-19。补旧schema2项目缺失management声明的前置能力，不称完整迁移，
不重跑initializer、不替换UUID、规则或Git策略。只使用pytest合成目录，无实际项目/
Vault/服务器写入，未发布安装，现用仍0.46.1。

## 输入和预期

一个非空旧项目，完整layout schema2、固定UUID、原AGENTS/Git忽略规则、已有唯一计划、
报告与配置；所有原始字节均纳入独立测试快照。请求角色和child的parent UUID由调用者
明确指定，不从目录名、报告或聊天推导。

| 情形 | 预期 |
|---|---|
| parent/child预览 | 零写入、无锁/工具/配置查询；原UUID及profile保持，清楚列出仅创建management和未执行事项 |
| 显式apply | 绑定当前根身份及选定声明/规则字节摘要，只exclusive创建management；原文件集合/字节守恒 |
| 原规则/layout/context在预览后变化 | exit5，不新建声明、不覆盖变化；重新预览 |
| 已有同角色声明 | 保留全部children等现有内容，返回unchanged，不重置已有登记 |
| 角色/parent/primary不同或已有未知内容 | 拒绝，不覆盖；不是再次初始化或更换身份 |
| parent仍选用了源码profile/addon | 拒绝；另行审议源码布局，不清空profile字段 |
| 不合法role/parent、自关联或缺预览摘要 | exit2；未写入 |
| symlink根/受保护文件、文件过大、根被替换 | 拒绝，不跟随到外部写入 |
| 受保护入口stat被权限拒绝 | 明确安全错误exit7、零写入，不以未处理异常或缺文件处理 |
| 发布点发生同名冲突 | exit5，保留对方字节，不能replace/overwrite |
| 文件同步前故障 | 声明未生效；只清理本操作自己的暂存，不触及未知文件 |
| exclusive创建后目录同步失败 | partial/exit6，保留实际声明供读回；不能报完全完成或破坏性回滚 |
| 暂存内容被改动、发布后规则再变化 | 未知暂存不发布/删除；已发布后变化报partial，不冒称依据仍一致 |

最后在既有collection单Run fixture构造旧父/旧子：保留原UUID和源码/配方/五状态，
仅补完整旧layout输入、移除原管理声明。通过公开CLI依次preview/apply角色、登记双方、
预览/接收原Run、require-run核对。原文件逐字节保持，不运行Git、SSH、模型或Vault。

调用的清单/摘要是操作预览，不是新项目事实源。角色声明只用既有management schema1，
layout仍schema2；不建立新的迁移registry或自动收集实验。未审议的PROJECT/计划、
AGENTS/Git策略与原生Git验证须保留为剩余工作。

## 执行

先新增真实CLI及故障用例，确认新接口不存在时失败；再实现最小声明writer。使用已有
安全root/有界读操作，预览不读取秘密或源码，apply不用shell/Git/SSH。测试分别记录
正常、冲突、故障，不因一次元数据创建宣称全部旧项目可迁移或整个G17完成。
