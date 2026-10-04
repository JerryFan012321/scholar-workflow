# 0.38.0：安装态单篇登记与下一版可见成果

## 交付与身份

- 分支：codex/hotfix-project-context，未合并 main。
- source：4d604c19aa8a0a6ea6c5f61c5853c0f2d9b81f2b；runtime：29c8ad00e710112271e874bb6dfc2050b2823581。
- 正常 runtime-only 发布经边界/个人路径扫描后推送 release；pipx 固定 runtime SHA 安装，Codex marketplace upgrade/plugin add 正常安装。
- CLI/module/distribution/Codex cache 均为 0.38.0，direct_url 确认实际 runtime SHA；实机操作未使用开发树或私有渲染器。
- 回退：正常 pipx 安装 0.37.1 runtime45ccf0960ac0b4034f7b77e2a93b0e6bd2671603；既有资料不随安装回退自动删除。插件回退需正常市场的对应版本入口，不手改缓存。

## 独立开发测试

对象/预期提前写于native-paper-registration-test-plan.md；合成Source/Field、假Local API、本机假PDF，不用真实文库调试。
包含零写入、真实owner联测、三个中断点条件续行、人工冲突、目录替换、身份/hash/权限变化、已有provider/回执保留、重复身份、损坏journal拒绝及CLI入口。

根Field `.` 的合法路径曾被旧父层数条件误拒绝，最小修正4→3，仍验证实际Field/provider owner与三文件/CAS。
版本同步后完整回归曾1560通过/1失败（旧Hub worker2秒计时）；原样单项复测通过，最终原样全套1561通过、11既有警告、77.66秒。未改旧worker或放宽断言。
变动模块/tests Ruff、skill validator与diff检查通过；历史CLI四个I001未顺手修改。

## 唯一安装态对象

已有Source869b0864-f8c9-47e7-94a3-7b283ecc6b60，Fielda6c248d3-23e8-4620-be36-5578b0510de1。
Source根为test/Scholar Workflow 实验/模范知识目录-0.36.0，reader只是包含它的test Vault，不增加父目录权限。
只创建resources/papers/2025-v-jepa-2-0380；原两项导航保留，只添加当前Paper.md。没有新建世界模型首页或迁移旧包。

Zotero Local API实际核验T3RY3HUA→QR4ZU2S9、文库17685951及imported PDF。本机48页PDF SHA256为9cfcfde5fb0d9730637da5b9e7317825c3f3d09e91f3553e22eeba42c74d2226，68条span身份/hash匹配；每处quote在指定物理页匹配，仅规范化空白，零措辞/标点替换。这不是语义科学支持评鉴。
Obsidian1.13.7、ZotFlow1.6.6与Advanced Canvas已启用，仅查询两个非秘密本机PDF设置，local=true；不读SecretStorage或完整秘密配置，不下载/复制PDF，不修改批注。

## 实际公开操作与结果

1. paper-plan零写入，审阅新目标和可读资料笔记；摘要56679844cff9e868f6187d8f18b4c4221d4635bf4e3998dee593b2bcef749716。
2. register-paper登记新owner、资料笔记、Field导航和唯一provider；登记回执不冒充分析/备份成功。
3. public batch使用新canonical身份、batch ID和唯一note_stem；原冻结claims逐字保留，validated、零诊断、零修复。
4. commit-bundle核Source/Field/reader/provider/CAS，三个目标missing→created、state=committed；只处理test。
5. 对返回KnowledgeChangeSet调用public apply-change-set，三项产物归属及has-analysis关系成功；登记重查analysis_committed=true，backup_verified=false。
6. actual check-bundle conformant：五分支、68内容、105可编辑nodes/104edges。实际路径如下；机器输入/回执在复现/，不混入分析正文。

目录：/Users/jerryfan/Documents/3-knowledge base/test/Scholar Workflow 实验/模范知识目录-0.36.0/resources/papers/2025-v-jepa-2-0380/

- Paper.md：可读资料入口，直接ZotFlow与Zotero动作、完整正文/Canvas/复现/验收链接。
- V-JEPA 2分析-登记样本.md：完整五分支、逐点证据和原文短摘录。
- V-JEPA 2解析树.canvas：原完整格式，不手改节点/布局/链接绕过校验。
- analysis.baseline.json：成对基线；复现/保存实际输入、请求、方案、回执、检查和结果。

knowledge open后backend activeFile为新Canvas、view=canvas；native metadataCache的68个反链全部落到新正文实际块，Paper四个wiki入口解析4/4。
Codex打开Paper.md返回queued，不把queued冒充已经可见的前台效果。当前Mac锁屏，不截取旧画面作证据。

## 保留与未完成

host registry字节保持c8ac406bd2366d6aa25ba34430ceae9ace810ba41ae21664bdadd836c5b2bf2c；旧正文hash保持4c1c898400baf1e2a3455f0b85302e36d509e11bef9f88e5119500f0bf81c56a。
关闭旧Canvas时Advanced Canvas补metadata.version/frontmatter，字节hash由7aa31b1c变为b9aee810；对原stage逐项比较nodes/edges完全一致，旧包check-bundle仍conformant。不删除编辑器metadata来假装旧字节不变。

正式科研Vault、Zotero数据、main、已有服务未变；恢复journal不是真实备份。人工审美/编辑/实际点击、逐点科学支持、完整模范Vault/项目/工具交互全阶段仍未完成；G17保持进行中。可展示的新成果是具有真实owner与成对回执的单篇资料包，不再只是只读报告或未登记副本。
