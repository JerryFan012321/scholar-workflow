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

## 正常发布与安装的实际记录

- source：12f054003773cd14dce274030cefa448c8422e89。
- runtime-only release：8f2cdacbabb2d7b963ae805e0fbc4bae9d435a6a；hotfix和release正常推送，main未合并。
- 独立干净clone通过既有make-release脚本构建。没有planning/tests/dev-guide/evals/AGENT/CLAUDE，scripts只保留guard-sqlite；目标个人路径/密钥模式检查无匹配。
- pipx固定运行提交正常安装；CLI/module/dist均0.38.3，direct_url.commit_id为上述runtime提交。
- Codex marketplace正常upgrade及plugin add返回0.38.3正常cache路径，两manifest均0.38.3；没有手工编辑缓存。
- 安装版PDF和Vault span实际schema均报告maxLength1600。
- 回退：0.38.2 runtime 7b6f89432b03619224e7d7907c66117c99b6d6d5。回退安装不自动删除业务清单。

## 安装版单对象登记

现有test Source的V-JEPA2已有完整provider归属，安装版零写入plan确认便携清单不存在，
只包含一个已核的Canvas声明。公开register成功，回执为
canvas-registration:9368df8d40ce538499b3f8f09b9605b5cee7468f7bfc20f107b7bff513ce92a3。
新增manifest hash：sha256:74999b240f403cb9143940a376edbf02a13d5ade48848cf10a998b6e4952088e。

同摘要重放返回字段值一致；首次比较误用JSON字符串而显示键顺序差异，递归排序后确认
对象字段值相同，未为此改变业务代码。正文/Canvas/sidecar/Field/registry/provider六文件
SHA-256前后全部相同；没有重排106个节点和105条边。

本地test论文目录新增“复现/便携声明-0.38.3/使用说明.md”，机器plan/receipt单列。
installed knowledge open已请求Obsidian打开说明，但这里只记录请求成功，不声称目视确认。
本轮没有扩写真实旧摘录、没有生成新图，也没有重跑整篇分析或批量迁移。
