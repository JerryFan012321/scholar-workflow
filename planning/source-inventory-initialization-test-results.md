# 新知识目录初始化：开发验证结果

日期：2026-10-09。状态：开发实现与定向验证完成，**未发布安装，未操作真实 Vault**。
正常安装 CLI 当日重新只读核验仍报告 0.42.0；本轮变更不属于该已安装构建。

## 用户能得到什么

| 场景 | 当前开发行为 |
|---|---|
| 登记一个真正的新知识目录 | 先零写入预览；确认摘要明确包含空资源清单初始化，再依次发布清单、Field、主机登记 |
| 两个知识目录使用同一论文 | 正式论文包只能有一个主归属；不能用第二次新 owner 登记代替引用 |
| 挂接已有知识目录但原清单丢失 | 报未知并拒绝新论文登记，不猜成空库；走已有显式恢复流程 |
| 创建中断 | 用原命令和已审阅摘要恢复，保持最初生成的 Source/Field 身份 |
| 恢复时有人改了正文或清单 | 停止并保留当前字节与 journal，不覆盖、不假报成功 |

没有增加另一套 owner 台账、公共命令或 Hub 前提。资源清单初始化不把现有 Markdown
自动收编成论文单元。已有 Source 挂接、追加 Field 保持原语义，不自动补造 provider。
领域引用写入仍未实现；本轮没有借此复制、迁移或重新分析论文。

## 独立输入、执行范围与预期

输入与手写预期先于对应实现：

- `tests/fixtures/source-inventory-initialization/EXPECTED.md`；
- `tests/contract/test_source_inventory_initialization.py`；
- `tests/fixtures/paper-owner-uniqueness/CONCURRENCY-EXPECTED.md`；
- `tests/contract/test_paper_owner_concurrency.py`。

所有操作只在 pytest 临时根。假 Local API 返回固定文库、论文、附件及合成 PDF 字节；
没有网络、真实论文业务、GUI、插件安装或服务操作。结果通过 JSON/YAML、文件字节和
进程状态直接核对，不把生产验证器、锁或 hash helper 当作预期结果的 oracle。

## 实际结果

| 轮次 | 实际结果 | 解释 |
|---|---|---|
| 原 18 项实现前 | feature RED | 入口/初始化行为尚未实现，selected 缺失清单仍被当空库 |
| 初次实现 | 17通过、1失败，0.52秒 | selected 的历史 missing-as-empty fallback 尚未移除 |
| 移除 fallback 后 | 18通过，0.57秒 | 新目录明确初始化，历史缺失拒绝 |
| 更新既有夹具后必要回归 | 205通过，4.14秒 | 原空库由正式登记创建；保留判重、CAS、恢复和 Canvas 登记要求 |
| 审查后增加8项边界 | 5失败、21通过，0.55秒 | 其中一项是测试未接受既有 provider 安全异常，不是产品放行 |
| 修正该异常预期后 | 4失败、22通过，0.50秒 | 三种重算checksum的成员注入与锁后父目录替换确实未被拒绝 |
| 语义及目录绑定修正后 | 26通过，0.66秒 | 核对完整待发布语义、批准前态与锁定目录身份 |
| 公共CLI安全异常新增检查 | 1失败、26通过，0.51秒 | 原命令抛未捕获异常，而不是要求的退出7 |
| CLI修正后必要回归 | 224通过，4.17秒 | 包含27初始化、28归属边界、既有159回归及10 eval schema检查 |
| 真实spawn双进程竞争 | 1通过，0.33秒 | 恰1成功/1拒绝，恰1owner/论文目录/导航；失败方及原件保持，无存活子进程 |
| 最终联合定向检查 | 225通过，4.27秒 | 同一受影响集合联合执行，不把多轮重跑累加成独立用例 |
| Ruff及diff whitespace | 通过 | 两处类型/导入lint和子进程异常上报的lint已最小修正 |

最终命令：

```bash
rtk proxy uv run --offline --with pytest python -m pytest \
  tests/contract/test_source_inventory_initialization.py \
  tests/contract/test_paper_owner_uniqueness.py \
  tests/contract/test_paper_owner_concurrency.py \
  tests/contract/test_paper_registration.py \
  tests/contract/test_knowledge_registration_cli.py \
  tests/contract/test_knowledge_ownership.py \
  tests/contract/test_knowledge_rebinding.py \
  tests/contract/test_canvas_registration.py \
  tests/unit/test_evals_schema.py -q --tb=short
```

秒数是 pytest 报告，不含环境准备。并发用例只是一对真实进程的一次受控竞争，
不是压力测试、任意调度证明或多个物理主机验证。独立审查只读复核两处安全修正，
未独立运行测试，不把它重复计作另一份执行证据。

## 实现与诚实边界

`workflows/register_source.py` 组合现有登记模型与 provider：registry → provider → Vault
锁顺序，主机 journal 先冻结生成身份，按成员 CAS 发布，再标记完成。校验不仅比较
可重算 checksum，也核对 fields、严格空 provider、registry before hash 及唯一批准新增。
路径必须与实际持有锁的 parent FD 指向同一目录；后续每次写前复核。

成员落盘而 progress 尚未落盘时，可以识别同一 after 字节继续。已发布成员丢失或被改，
不恢复成 before。完成 journal 不能作为重建丢失 provider 的许可。精确 completed replay
只在创建成员保持时幂等；后续合法业务变更不是再次运行旧创建事务的理由。
这是可恢复逻辑事务，不是全文件系统硬原子，也不是 verified backup。

运行契约、配置说明、中英文 README、eval 和当前状态记录已同步；没有变更论文分析
IR/Markdown/Canvas 模板、版本或 plugin manifests。五分支、对齐无交叉、证据链接、
正文图片与折叠摘录要求保持。未进行正式迁移、论文重分析、实验执行或 main 合并。

下一步分别处理正常 hotfix 安装态单对象验证、Field 引用写入与上层模板人工评鉴。
这些尚未通过，不能把225项定向检查或本切片完成等同于完整G17完成。
