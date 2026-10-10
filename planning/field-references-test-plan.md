# Field 引用兼容与只读解析独立测试方案

编写时状态：测试准备，尚未实现。实际执行结果见 `field-references-test-results.md`；
当前已完成开发树验证，未发布安装。

## 本轮交付边界

只在既有 `fields.yml` 中增加显式 schema 2 的 Field 引用，并复用已有声明解析。
不新增全局 owner 数据库、Hub 前提、跨库同步或外部正文副本；引用增删的受控写事务
不在本轮切片中。schema 1 清单不自动升级。论文 Markdown/Canvas/sidecar 内容契约不变。

引用记录固定为 `reference_id`、`target: {source_id, object_id}`、`purpose`。
同 Field 的引用 ID 和目标组合均唯一；同论文可被多个 Field 引用，但 provider 仍唯一归属。
目标 ID 不含路径或 URL，引用不授予导航读写权限。缺失/停用/未登记目标保留诊断，
指定 Source 不得遮蔽其他已登记 Source 中的重复 owner。

## 独立输入与预期

在 pytest 临时目录构造两个已登记 Source 和多个 Field，以及一个既有论文 owner。
使用手写 schema 1 原样字典、schema 2 引用、用途和目标身份；使用既有合成 provider，
不以新解析器输出生成预期。独立预期另见 `tests/fixtures/field-references/EXPECTED.md`。

- schema 1 输入与序列化保持旧字段，输入额外 `references: []` 也不能冒充版本 1。
- schema 2 接受多个 Field 复用同一 owner；重复 ID/目标、未知版本、非法 ID、空用途、
  额外路径/URL 字段拒绝。公共 JSON schema 与 Python 模型一致。
- preview、list 和登记摘要呈现已选择的用途；默认不宣称已解析或已通过原生阅读器验收。
- 历史 Field/论文迁移重新构建清单时保留 schema 和引用；旧 override 不得静默删引用。
- 复现包同时保留引用结构与清单原字节；外部被引用文档不进入本 Source 文件 inventory。
- 只读解析返回唯一 owner、文件状态和未验证阅读器；目标 Source 不匹配/不可用显示
  incomplete，重复 owner 显示 conflict，不任取首项。
- 引用不被当作 placement；多个引用不影响 owner 数量，不读取正文、秘密、网络或应用。
- schema 1、已有 Source 初始化、单篇归属、Project 解析和复现回归保持原行为。

## 执行与影响

先执行新增独立测试记录 RED，再实现并执行相同测试及必要回归、Ruff、diff 检查。
测试只写临时合成输入和开发记录，无正式 Vault/项目/provider/Zotero 变更、原生应用启动、
发布、安装、服务切换或 main 合并。记录夹具错误和真实产品失败，不篡改预期来适配实现。
输出：新增 contract 测试、独立预期、单独测试结果报告和可读的合成 Field 引用清单。
自动测试不替代后续正常安装和人工导航评鉴；本轮不要求用户重复评审已认可的论文图。
