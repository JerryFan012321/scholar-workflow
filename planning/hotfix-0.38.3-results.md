# 0.38.3 单篇复现能力与完整摘录

分支：codex/hotfix-project-context。main 不合并；正式文库、服务与模范项目既有清单不修改。

## 改动

- 已归属单篇 Canvas 的独立 portable manifest plan/register，复用现有 provider、CAS 和恢复日志。
- 正文 quote 的模型与公开 schema 容量从 400 提高到 1600 字符。完整原句及必要语境是硬输出要求，容量不是凑满目标，也不免除适用引用限制。
- Canvas 不重复摘录，已认可五分支、节点、连线和几何限制不改变。

## 独立验证

输入：既有合成论文/Source fixtures，新增两段事先手写的 SOURCE-CONTEXT.md，不使用真实文库。

1. 修改实现前，新增容量测试10失败、6通过，失败均定位400字符限制。
2. 容量修正后PDF/Markdown span、claim/point的400/401/1600边界通过，1601拒绝；模型及公开schema一致。
3. v4/v5逐字完整摘录呈现和局部更新通过；原Canvas完整数据保持相同，不以语义hash替代图数据比较。
4. 摘录与五分支定向127通过；最后增加逐字反转义核对后摘录58通过。
5. 完整unit/contract：1620通过、11既有警告，82.80秒；Ruff、skill quick_validate、git diff --check通过。

测试曾有一处五分支摘录缩进预期误用旧格式，已纠正测试，未更改渲染器或布局。

## 安装态与真实内容

正常发布安装及实际版本身份需另行记录。此处测试不证明真实V-JEPA2摘录已经修订或验收，
也不证明整份知识provider能在新主机自动恢复。现有0.38.2仍是安装回退基线。
真实测试仅使用原有单篇test资料包，正式Vault、Zotero及原PDF不参与调试写入。
