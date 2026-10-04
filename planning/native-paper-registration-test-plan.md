# 单篇论文正式归属：独立测试与结果

## 范围

这轮先只测试合成论文、临时已登记 Source/Field 和临时本机 PDF。真实 Zotero、test Vault、
正式 Vault、已安装插件、运行服务和 main 不变。产品入口必须在正常 hotfix 安装后才能做真实验收。

## 输入与独立预期

- 本地 API fixture 明确给出论文 key、PDF key、父子关系、文库、标题和本机 locator。
- 初始 Field 有可读 README，registry/便携 manifest 已由正式登记函数生成，无 provider、无论文目录。
- paper-plan 连续两次摘要相同，零正文/manifest/provider 写入。
- register-paper 的新资料笔记、导航和 provider owner 一致，原 README、身份和既有对象不变；
  只记录登记回执，不把 analysis_committed 或 backup_verified 置真。
- member-1/2/3 分别模拟中断；原摘要重试完成，不重复身份/回执。人工修改、根/状态目录
  变更、来源/hash/权限变化拒绝继续，不覆盖人工内容，不把 prepared journal 报为 committed。
- 路径逃逸、symlink、错误附件父项、重复论文身份、已有目录、journal 摘要篡改均拒绝。
- 后续增加第二篇时保留第一篇/provider 回执；旧登记请求仍可安全重查当前归属。
- 显式新 owner 能接入既有 v5 render/baseline/paired commit/provider apply，全套三文件归属一致。
  根 Field `.` 的路径合法；缺少 resources/papers、分散三文件和非实际 Field owner 仍拒绝。
- CLI runner 只用假 Local API；零写入 plan 和显式 digest 注册的公开参数实际可调用。

## 实测与纠偏记录

首轮 43 项定向通过；补 existing provider、公开 CLI 和目录替换后46项通过。
第一轮完整 unit/contract 1555项通过、11既有警告、77.64秒。该结果不含后来新增联测与最终修正。

追加v5登记→成对提交用例后129通过/1失败：旧AnalysisCommitRequest强制路径含Field前缀，
与合法根Field `.` 矛盾。修正父目录最少层数4→3；保留resources/papers、同目录三文件及实际
Source/Field/provider owner核验。独立路径反例改为真正缺少resources的浅目录，并保留根Field正例。
随后定向137项通过，覆盖登记、v5、provider apply及成对提交。新增模块/测试/model Ruff通过；
文档与规则已记录命令、恢复和完成边界。最终权限/完成回执检查后的完整回归1557项通过、
11既有警告、78.41秒。发布前再增加损坏journal的4个拒绝用例：列表、非文本status、非对象plan、缺少摘要；
预期明确安全拒绝、零资料/provider发布、损坏日志原字节保留。版本改为0.38.0后再核完整回归。

0.38.0完整回归1560通过/1失败、11既有警告、99.01秒：旧Hub terminal worker的2秒计时
用例出现timed_out；不属于新登记路径。独立原样复测1通过/1.30秒，不改旧worker或放宽断言。
最终完整回归重新执行以区分偶发环境计时与产品回归；没有用单项通过冒充完整全绿。
最终原样完整回归1561通过、11既有警告、77.66秒。变动模块/测试Ruff、skill validator和
diff检查通过；未修改旧worker或放宽计时断言。准备正常runtime-only发布安装0.38.0，
随后仅做上述单篇安装态验证；此处不提前记录实机或人工通过。

## 安装后唯一真实对象

计划只在已有清洁test Source/Field的全新V-JEPA2目录，经安装版paper-plan审阅当前输入；
确认后登记真实资料笔记与owner，再用已有冻结v5内容构造正式CAS提交请求。旧审阅包不接管、
不覆盖、不丢内容；无PDF复制/下载/批注修改，不进行整库或正式Vault迁移。
正式归属、paired commit/provider apply及Obsidian原生打开分别记录，不以开发测试替代安装态。
GUI/人工审美因锁屏保持pending；不能截旧画面或以metadataCache解析代替人为点击通过。
