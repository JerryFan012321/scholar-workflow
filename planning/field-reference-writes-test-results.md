# Field 引用安全增删：开发测试结果

日期：2026-10-09。分支：codex/hotfix-knowledge-ownership。
对象：独立临时根的合成 Sources/Fields/owner/provider，非正式 Vault 或本机业务。
预期与影响范围先写于 field-reference-writes-test-plan.md 和 fixture EXPECTED.md。
未提交、未发布安装、未切换服务、未写真实 Zotero/Vault/项目，不改变已认可的论文格式。

## 结果

- 新增 82 例：工作流 57、CLI 25；与 681 项必要回归合计 **763 passed**，21.15 秒。
- 5 个既有 PyMuPDF/SWIG 弃用警告，不是测试失败。
- 所改实现/新增测试的 Ruff 与 `git diff --check` 均通过。
- 运行说明/eval同步后，另复跑10项eval结构校验通过（0.01秒）；不将schema校验当行为验收。
- 正常安装入口重新只读报告 `scholar-workflow, version 0.42.0`。
- 实际合成 CLI 展示见 field-reference-writes-demo.md，不冒充正常安装或人工验收。

## 过程与失败留证

| 阶段 | 实测 | 解释/处置 |
|---|---|---|
| 实现前首份 CLI 测试 | 20 failed，0.83秒 | 模块尚未存在，真实 RED；独立测试后续扩为25例 |
| 首版实现后联合 | 46 passed / 22 failed，1.18秒 | 4个摘要前缀、5个观察器误拦测试快照、8个首次主机锁文件属于夹具错误；其余5个暴露错误类型未规范化 |
| 修正后基础联合 | 68 passed，2.26秒 | 保持业务快照断言；正常锁由夹具提前准备，移除产品调用仍禁止 provider 读取 |
| 加6个最终发布边界与只读回归 | 157 passed，2.23秒 | 同字节新inode/FIFO/超限叶替换、root/state交换、unchanged fsync拒绝，以及既有解析保持 |
| 新增最终读集窗口 RED | 5 failed，0.42秒 | 临时文件fsync后目标/owner元数据或声明inode变化仍可发布，确认为产品缺陷 |
| 补最终读集检查 | 57 passed，1.23秒 | 最终replace前复核全部声明identity/hash、目录binding和目标元数据 |
| CLI不确定结果 RED | 1 failed，0.39秒 | 应为exit6，实际exit7；独立异常分型测试先于修正 |
| 补CLI分型后 | 80 passed，1.51秒 | 不确定结果exit6并保留fresh plan提示，不报成功或未写入 |
| 相同用途的移除展示 RED | 2 failed，0.26秒 | 缺少所选引用名称，人工无法区分；补显示唯一的本地引用名 |
| 最终定向联合 | 763 passed，21.15秒 | 82新增加681必要回归；不是完整发布回归 |

独立手写预期先于实现；首份20项CLI做了实现前RED，其余基础案例由另一agent按冻结预期
编写，首次联合运行发生在首版实现后。新增具体边界的预期分别先写后测；不将后测通过
改写为“所有测试都在实现前失败过”。首次Ruff暴露导入排序、pytest fixture F811及
嵌套if静态问题，修正后通过；夹具错误不冒充产品缺陷。

## 可证明的边界

新增仅选取既有唯一owner，不新增归属或复制。重复ID换目标/用途、重复qualified目标、
未知/错Source/缺失或symlink文件、无法证明唯一性的provider声明均拒绝。
同Source及跨Source的论文/分析可增引；引用不授予目标写权限。
移除不读取provider，即使目标未登记、离线或所有provider缺失，也仅移除选定本地引用。
其他引用、Field、导航、YAML注释、原文、Canvas、provider和项目文件保持。

计划零写入，审批绑定全读集；apply使用registry→sorted providers（仅add）→Vault锁。
最终CAS每次限长/NONBLOCK并比较已批准叶identity，临时文件fsync后再次检查外部输入。
故障不回滚人改内容；单文件完整发布，可能可见但持久性未确认独立exit6，fresh plan后观察
真实终态。并非对任意外部writer提供文件系统硬原子，确认后也不锁定目标内容。

## 最终命令

```sh
rtk proxy uv run --offline --with pytest python -m pytest \
  tests/contract/test_field_reference_writes.py tests/contract/test_field_reference_write_cli.py \
  tests/contract/test_field_reference_contract.py tests/contract/test_field_reference_legacy_preservation.py \
  tests/contract/test_field_reference_resolution.py tests/contract/test_knowledge_ownership.py \
  tests/contract/test_knowledge_registration_cli.py tests/contract/test_knowledge_reproduction_inventory.py \
  tests/contract/test_knowledge_reproduction_restore.py tests/contract/test_knowledge_reproduction_assets.py \
  tests/contract/test_knowledge_rebinding.py tests/contract/test_paper_registration.py \
  tests/contract/test_paper_owner_uniqueness.py tests/contract/test_source_inventory_initialization.py \
  tests/contract/test_paper_owner_concurrency.py tests/contract/test_canvas_registration.py \
  tests/contract/test_hub_v3_field_registration.py tests/contract/test_hub_field_transaction_public.py \
  tests/contract/test_hub_field_analysis_write.py tests/contract/test_legacy_field_transaction.py \
  tests/contract/test_legacy_field_payload_contract.py tests/unit/test_hub_field_transaction.py \
  tests/unit/test_hub_field_lock_order.py tests/unit/test_hub_joint_field_transaction.py \
  tests/unit/test_hub_paper_placement.py tests/unit/test_hub_v3_fields_zotflow.py \
  tests/unit/test_module_ownership.py tests/unit/test_evals_schema.py -q --tb=short
```

完整G17、正常安装态、Field实际导航与PROJECT/literature候选人工评鉴仍未完成。
