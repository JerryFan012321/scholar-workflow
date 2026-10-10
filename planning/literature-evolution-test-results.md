# 文献演进预览：开发测试结果

2026-10-09；独立 hotfix 开发树，未发布、未安装，正常安装仍是既有 0.42.0。
本轮没有正式 Vault/Zotero/项目写入、服务切换、论文重分析或实验重跑。

## 输入与实现边界

手写 EXPECTED、计划先落盘，再准备七篇合成输入和独立测试；不是用 renderer 生成预期。
先纠正两个输入契约问题：位置待定可以保留已知类别，未核验不能自动变成原文未报告。
新 knowledge 模块只持契约与纯渲染，CLI 是薄预览入口。旧 schema、分类树 writer 和单篇
论文五分支/Canvas/图片/摘录格式原样保留。不增 Hub、登记库、owner 或业务写入口。

## 实际结果

| 检查 | 结果 | 证据边界 |
|---|---|---|
| 实现前公开 CLI 基线 | exit 2：No such command `literature-preview` | 先前 `python -m scholar_workflow.cli` 空返回是错误调用方式，不计验证；正确入口是 console script |
| 实现后首次独立 pytest | 30 项：29 通过，1 失败，0.13 秒 | 下划线 sentinel 被正常 Markdown 转义，观察器未解码；不是产品丢失正文 |
| 观察器修正 | 改为无 Markdown 分隔字符的 sentinel | 没有取消产品转义或降低科学预期；pending fixture 采用 unverified，cost 的 not_reported 保留 |
| 完整归属连线断言 | 手写六条 parent 边要求集合完全相等 | 独立复核指出子集断言可能漏线；当前产品本就输出全部六条，无需产品修复 |
| 首次定向联合 | 89 通过，1.09 秒 | 30 新接口 + 12 旧 schema + 15 旧 renderer + 21 模块边界 + 10 eval schema + 1 旧 CLI |
| 最终定向联合 | 89 通过，0.30 秒 | 补足四类图例、合成链接非实测提示和节点前景色后，同一范围复验；不是 178 项独立测试 |
| Ruff | 最终通过 | 新模块/CLI/新测试先通过；纳入既有模块边界文件时暴露旧空行与重复 startswith 风格问题，等价整理后通过 |
| Skill 入口 | quick_validate 通过 | 只证明入口格式，不证明科学支持、原生图形显示或人工接受 |
| diff | `git diff --check` 通过 | 不代替完整发布回归 |

最终命令：

```bash
rtk proxy uv run --offline --with pytest python -m pytest tests/contract/test_literature_evolution.py tests/contract/test_literature_tree_schema.py tests/unit/test_novelty_tree.py tests/unit/test_module_ownership.py tests/unit/test_evals_schema.py tests/contract/test_hub_cli.py -q --tb=short
```

## 可见产物与未完成项

`literature-evolution-demo.md` 是最终开发 console script 的实际 stdout，7 篇论文、8 项贡献、
6 条归属边和 2 项完整科学关系说明。图只表示归属；科学关系在正文逐项保留，未把它
冒称最终演进图。来源 key/hash/页与笔记路径都是合成测试输入，不能用于阅读器实测。
声明路径不冒充可打开的跨 Source wikilink；真实路径、来源归属和科学支持没有被验证。

自动检查证明格式/引用/副作用边界及旧接口回归，不证明图像无交叉、外观美观、
Obsidian 原生显示或真实文献的技术进步。最终载体/紧凑外观、有限真实语料以及安装态
仍独立待验；PROJECT 与实验比较不在此切片实现。G17 全目标未完成。
