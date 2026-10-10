# 领域论文单元导航：开发验证结果

2026-10-10。分支 `codex/hotfix-knowledge-ownership`，基线提交
`b9f2ffeeb344e2524401ebcf48f8f40301da190a` 加未提交开发改动；不是已安装产品证据。
独立预期和计划于实现前落盘，分别见 `tests/fixtures/field-paper-units/EXPECTED.md`
与 `field-paper-units-test-plan.md`。本轮不提交、发布、安装或操作真实资料。

## 实际交付

现有 `knowledge list` 增加显式 `--paper-units --source-id ... --field-id ...` 模式。
复用 provider、全局归属与原生 reader 解析，只读组合选中 Field 的本地论文及明确引用。
分析/Canvas 沿 owner 归一，同名不同身份不合并，重复引用的全部用途保留。
资料、分析、Canvas、笔记及其他附件来自声明；缺失、未声明、冲突和不可用不冒充成功。
唯一且安全的 Markdown/Canvas 才给原生打开候选；不执行打开。

静态独立复核发现实际分析提交可能把 supporting title 设为 artifact ID，已仅在
人类 renderer 中对这个精确情形使用可读角色。JSON 原声明与自定义标题保持。
默认 list/resolve-reference 行为、旧 Paperlist 和论文分析/Canvas 契约不变。

## 运行与结果

| 检查 | 实际结果 |
| --- | --- |
| 首轮新增独立测试 | 38 通过、3 失败，1.03 秒；失败原因见下方，不删除记录 |
| 定向复跑新增测试 | 41 通过，1.35 秒 |
| 新增及受影响回归联合 | 562 通过，6.64 秒；包含上述 41 项，不重复加总 |
| 五个本轮 Python 文件 Ruff | 通过；首轮仅测试 import 顺序 I001，最小修正后通过 |
| build-literature-tree quick_validate | 通过；不是宿主触发或人工可读性证明 |
| 旧树四文件 SHA-256 与执行前基线 | 全部一致 |
| analysis 核心及 analyze-paper skill 与 HEAD | 无差异，退出 0 |
| git diff --check | 通过 |

三项首轮失败属于独立测试误设/观察器错误，没有为它们降低产品安全要求：

- 外部 provider 不可读时，既有 `resolve_declared_ownership` 无法证明全局唯一性，
  因而本地引用也保持 incomplete。旧测试误要求 unresolved 仅含外部引用；修正为
  保留三条完整原始声明、本地已知位置和来源诊断，所有不完整归属的 URI 均禁用。
- 两个语言用例的链接观察器仅识别裸 Markdown URI，漏了合法 `(<URI>)`。
  修正观察器支持两种 CommonMark 形式，继续核验 scheme、精确 Vault/file、标签与隐藏 ID。

测试在两个合成 Source 中检查 Alpha/Beta/Gamma、另一个 Field 和未声明邻近文件。
覆盖只读权限、不可读/损坏/不安全 authority、读取期间替换、重复 owner、缺失文件、
非论文/未知引用、reader 缺失/歧义、symlink、Source 子目录及标题/路径转义。
I/O guard 禁止正文读取、网络、子进程和原生打开；查询前后比较输入集合及字节。
并发替换仅由指定 fixture hook 模拟，不是产品写入。

## 可见产物与边界

`field-paper-units-demo.md` 保存相同合成 fixture 经实际 Click 命令输出的中文 stdout。
它得到恰三篇论文：两篇同名但不同所属领域，Gamma 两用途合为一行，Beta 未声明
分析/Canvas/笔记。样张是开发输出，合成链接不用于真实点击。

人工评鉴对象是清单的可读性、列安排、用途与文件入口是否容易理解；仍待用户确认。
正常安装态、真实 Field 导航和 Obsidian 点击未执行，不能由 URI 或测试通过代替。
没有重新分析论文、重跑实验、写 Vault/Zotero/真实项目、启动服务或合并 main。
这只是上层组合的有限切片，不是完整 G17、全套发布回归或全源 lint 认证。

## 实际回归命令

```sh
rtk proxy uv run --offline --with pytest python -m pytest \
  tests/contract/test_field_paper_units.py tests/contract/test_knowledge_ownership.py \
  tests/contract/test_field_reference_resolution.py tests/contract/test_field_reference_writes.py \
  tests/contract/test_field_reference_write_cli.py tests/contract/test_field_reference_contract.py \
  tests/contract/test_field_reference_legacy_preservation.py tests/contract/test_obsidian_source_reader.py \
  tests/contract/test_knowledge_registration_cli.py tests/contract/test_paper_registration.py \
  tests/contract/test_paper_owner_uniqueness.py tests/contract/test_source_inventory_initialization.py \
  tests/contract/test_literature_tree_schema.py tests/contract/test_literature_evolution.py \
  tests/unit/test_novelty_tree.py tests/unit/test_hierarchy.py tests/unit/test_projection.py \
  tests/unit/test_module_ownership.py tests/unit/test_evals_schema.py -q --tb=short
```
