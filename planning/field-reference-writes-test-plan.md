# Field 引用安全增删：独立测试计划

## 范围与公开接口（先于实现）

仅改引用方 `.scholar-workflow/fields.yml`；引用不构成 owner、复制、同步或目标写权限。
新入口为 `knowledge reference-plan` / `knowledge reference`。
必选 source-id、field-id、operation（add/remove）、reference-id；add 另需
target-source-id、object-id、purpose，remove 拒绝这些附加参数。
工作流接口为 `reference_plan(registry, **selection)` 和
`change_reference(registry, approved_digest=..., **selection)`。

- plan 零写入，不建锁/目录；给出明确增减、现有正文不变及确认摘要。
- add 必须经全体登记 Source 的声明确认唯一 owner、指定 Source 匹配、目标及主资料文件可用。
  不按标题匹配；已有相同引用是 unchanged；同 ID 不同内容或同目标不同 ID 拒绝。
- remove 只按本 Field 的 reference-id 精确选择，不读目标 provider；目标离线也可移除。
  不存在的 reference-id 拒绝，不删除任何目标文件或 owner。
- 只变更所选 Field.references，首次 add 将 schema 1 升为 2，remove 不降级。
  保留其他 Field、导航、原有引用、YAML 注释及正文/provider 的原字节。
- apply 只接受当前计划摘要。固定锁顺序：registry →（add 时）已登记 providers → 所选 Vault。
  重新核验声明读集、目录身份和目标文件元数据，然后以单文件 CAS 发布。
  临时文件 fsync 后、最终 replace 前再核对全部声明 identity/hash 与目标元数据；
  每次 CAS 读取均限长/NONBLOCK，并比较已批准叶 inode。正常主机协调锁不属于业务清单写入。
- 不为一个文件另建事务数据库/journal。若 rename 后持久化确认失败，报告不确定结果，
  不回滚可见清单；旧摘要不得覆盖现状，重新 plan 后显示 unchanged 或真实差异。
  持久化/发布不确定独立报 exit 6；写前安全拒绝为 exit 7，不能混称“未写入”。

## 合成输入与独立预期

复用已有 ownership_scope，仅临时根；显式赋予引用方 read/write，目标仅 read。
手写预期存在 tests/fixtures/field-reference-writes/EXPECTED.md。
测试不以生成器输出作为期望，不访问本机 Vault、Zotero、网络、应用、密钥或模型。

| 组 | 输入/操作 | 预期 |
|---|---|---|
| 预览 | schema1/2、同源/跨源、论文/分析 | 零写入，摘要稳定，显示明确用途与相对位置 |
| 增加 | 已审阅当前摘要 | 仅清单更新，只有1引用，owner及provider不变 |
| 保留 | 第二Field、导航、注释、已有引用 | 原语义与注释不丢失，无正文更新 |
| 冲突 | 重复ID不同内容、重复目标、未知身份/Source、重复owner | 拒绝，无业务文件更新 |
| 移除 | 目标离线/删除provider/未登记 | 仅移除选定引用，其他引用不变 |
| 输入 | dirty purpose、越界ID、remove额外参数、未知operation | 拒绝 |
| CAS | 清单/registry/provider/目标元数据变动、根重绑、symlink | 旧摘要拒绝；不覆盖人工修改 |
| 故障 | 单文件发布后故障 | 清单完整，无半份YAML；旧摘要拒绝，fresh plan识别unchanged |
| CLI | md/json、en/zh、确认/取消、错误 | 薄入口，安全错误exit7；正文不展示机器路径/身份 |

## 执行与产物

先运行新增独立测试记录 RED；实现后复跑新增测试及受影响 ownership、registration、
Field兼容、reproduction和模块职责回归，另做 Ruff/diff 检查。
结果单独记于 field-reference-writes-test-results.md；展示合成的人类增减预览。
普通测试无需额外批准；本轮不发布、不安装、不写正式资料、不重开单篇分析人工验收。
