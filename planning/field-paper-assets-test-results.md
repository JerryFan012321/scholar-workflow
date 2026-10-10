# 单 Field 论文附件清单修复与测试记录

日期：2026-10-10。当前仅为未发布的开发修复，基于
`codex/hotfix-knowledge-ownership` 的 `b34aca828009d2f0a9aef3daa0f7af6f35bee80b`。
本轮没有提交、发布、安装或切换服务；现有 0.43.0 安装结果不能证明本修复已生效。

## 要解决的问题

此前正常安装 0.43.0 的单 Field 查询列出了论文、分析、Canvas 和 sidecar，
却遗漏同 Source `assets.yml` 中明确关联的六项附件。原始结果保留在 test Vault，
仍为“完整资产覆盖未通过”；本记录不能替代修复后的安装态复验。

本修复仅补论文清单的附件读取和诊断。不改论文正文、解析树、论文归属、登记库、
项目、实验或外部工具，不扫描同名或邻居文件，不把资产变成新的 primary owner。

## 独立输入、预期与测试步骤

预期先由独立代理写入
`tests/fixtures/field-paper-units/ASSETS-EXPECTED.md`，用例随后写入
`tests/contract/test_field_paper_assets.py`，先执行红测才修改实现。
主代理只给既有读取守卫增加各合成 Source 的精确 `assets.yml` 路径，
没有放开目录或正文读取。生产实现与预期没有相互生成答案。

输入是两个合成 Source、三个选定论文单元，以及另一个 Field 的排除对象。
它们覆盖 provider 与便携资产、四种角色、sidecar producer、共享附件、
同名/同 ID 的跨 Source 对象、Markdown 补充文档和明确未声明的邻居。

通过标准：

- 仅沿明确 artifact→paper 关系归入既有单元；去重但不丢用途，不借用外部 Source owner。
- 语义一致的双声明合并；owner 集顺序无关；冲突 ID/路径的双方均不作为确定文件输出。
- 缺失、不安全、不可读、无效和变化声明不冒充完整或空库；独立有效条目继续可见。
- 可选清单稳定不存在不算失败，首读不存在而后出现须报告变化，不补造尚未知关系。
- 初读中替换时不采用未建立的 portable 关系；完成重检中替换时保留已观察条目并撤销 URI。
- 只有安全 Markdown/Canvas 使用现有原生入口；其他类型列出“不支持原生打开”。
- 不读取或哈希正文/附件字节，不发网络请求、不启动进程/应用，不写状态、锁或业务文件。
- 普通 Field list、已有清单和论文/项目/实验契约不回归。

专项命令：

```sh
rtk uv run --with pytest pytest -q tests/contract/test_field_paper_assets.py tests/contract/test_field_paper_units.py --tb=short
```

必要联合回归：

```sh
rtk uv run --with pytest pytest -q tests/unit tests/contract --tb=short
```

仅用临时测试依赖与合成 fixture；不是正常安装、实机阅读或业务执行证据。

## 实际结果

| 阶段 | 结果 | 含义 |
| --- | --- | --- |
| 实现前专项红测 | 24 failed / 43 passed，1.72 秒 | 旧清单 41 项通过；新增覆盖实际揭示漏列、缺少诊断和未观察 manifest |
| 首版修复专项 | 67 passed，3.43 秒 | 原有与初始附件用例通过，仍不代表边界完全闭合 |
| 独立复核补测红测 | 4 failed / 74 passed，2.68 秒 | 揭示跨声明 first-wins 与 owner 顺序误报，先补预期再改实现 |
| 边界修正专项 | 78 passed，2.54 秒 | 冲突双方排除、owner 集规范化及补充边界通过 |
| 最终完整 unit/contract | 2525 passed / 11 warnings，107.65 秒 | 包含最终 39 项资产测试及全部既有回归；11 项为既有 SWIG/fork 弃用警告 |

Ruff 初次通过临时依赖下载失败（PyPI TLS EOF），未冒称检查完成；
改用已缓存的离线 Ruff 后发现 I001/B023，最小修正后所改五个 Python 文件检查通过。
两名独立代理复核确认冲突双方排除与 owner 顺序修正闭合；其静态复核不代替运行测试。
最终五个 Python 文件离线 Ruff 与整个工作树 `git diff --check` 均通过。
新增 outcome 保持 pending；原 outcome 的历史证据与范围未改写成完整验收。
回填最终测试数量后，10 项 eval schema 检查再次通过（0.02 秒）。

## 尚未证明的部分与下一步

- 尚未发布安装本修复；不能用源码查询真实 Vault 冒充安装态验收。
- 下一轮获得相应发布安装授权后，按正常 hotfix 流程安装，再只复验已登记 test Field
  的既有 V-JEPA 2 单元是否包含六项已声明附件及安全 Markdown 入口。
- 原 0.43.0 四文件 stdout 与“部分通过”记录不覆盖、不改成新结果。
- 人工美观、实际原生跳转、全篇科学支持及第一阶段整体目标仍不由本次合成测试认证。
  已认可的论文正文、Canvas 和折叠摘录体验不因本修复重审。
