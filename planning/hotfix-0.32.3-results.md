# 0.32.3 单篇可见成果

范围见 `hotfix-0.32.3-test-plan.md`。仅改 bounded gutter cap、契约和版本，保留内容与2:1等硬门禁；不合并main，不改正式Vault、旧稿、Zotero或服务。

## 开发验证

独立四间隙反例：修正前2 failed；修正后定向70 passed（1.27s），全量1425 passed/11 warnings（73.48s），四文件Ruff、diff空白通过。修正后的四间隙9144高输入宽4572、gutter341；9208高输入在cap344时仍不满足2:1，不会无限扩展。

## 安装态与可见结果

已正常发布、安装：source `fdb35225a39acf52b8114b02447a4a2b0ab27621`，runtime `c0fa2000a7b8d56a841bc753be12d5f3898e7114`；Codex cache与pipx包/公开CLI均0.32.3，direct_url绑定该runtime，未从源码仓库运行样张。远端main仍`ccb60b793d9fd5db6032499bf2ca2c8dda3f1183`。

唯一真实样本的public `analysis batch-run`：batch `vjepa2-0323-review-01`，completed/validated，repair_count0，diagnostics空。read-only `audit-batches`也无finding。正文/Canvas/baseline原样副本放入test Vault的 `Scholar Workflow 实验/V-JEPA 2/0.32.3-完整框架候选/resources/papers/2025-v-jepa-2/`，三文件hash均与staging相同，打开Obsidian后再核对仍相同；不是canonical commit或正式Field登记。

实际结果：36 claims、68内容、105可编辑text节点/104边、4572×9144、最大节点高150；完整摘要/引言/方法/实验/局限。68原文入口均是Obsidian内ZotFlow Library Reader投影，68正文段落反链均解析到实际anchor；Markdown无机器claim注释，Canvas无摘录节点。附完整非秘密输入、批次返回、阅读说明、复现说明和验收记录；均留在test Vault，不提交业务样张到插件。

本机Obsidian1.13.7、Advanced Canvas7.1.0、ZotFlow1.6.6启用本机PDF模式，Local API确认附件归属与当前PDF hash一致。68原文短摘录在对应物理页存在性已核对；保留旧内容并修正八处，不声称逐条论证充分性全部重审完成，7处分析推断和1处证据空缺保持明确。

已通过Obsidian公开CLI打开正文与Canvas，应用内实际载入105节点/104边，正文也提交Codex文件面板打开。Mac锁屏导致原生GUI截图/点击无法可靠评鉴；现有截图是诊断，不作为验收通过，已在会话明确告知并询问解锁。用户审美/编辑/点击仍pending，main不合并；G17整个阶段未完成。

回退方式（未执行）：正常pipx固定提交安装0.32.1 runtime `14e20b44afbf84d3bb278fa4a04290e754006ec0`；Codex插件须经对应marketplace快照正常恢复，不能手改cache。无服务切换或未知进程停止。
