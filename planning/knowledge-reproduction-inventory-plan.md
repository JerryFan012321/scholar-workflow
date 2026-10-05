# 归属复现输入：独立导出切片

对象：一个已登记Source及其明确provider，不扫描或改写整个Vault。

本轮实现公开只读reproduction-plan：保留稳定Source/Field、资源/附属产物身份、关系及文件hash，
去除主机根绑定、provider历史回执和运行诊断，生成独立的版本化复现输入。它不是新的事实根，
也不是自动备份；当前provider与正文仍为权威。导出不宣称目的地provider已恢复。

只读取manifest/provider及明确声明的文件，包括Field首页和导航；检查已归属分析的三文件及
baseline/格式，不从同名文件或正文链接推断归属。PDF保留附件identity，不复制附件或密钥。
旧reader ID位于被保留的正文/sidecar时明确列出需重新绑定的分析，不声称跨机深链可直接使用。
Source/Field、provider、registry、根目录或任一文件在检查中变化时拒绝结果。

## 先准备的独立验证

输入：已有合成单篇注册fixture、合成分析三文件、独立Field/registry；不使用真实论文或文库。
新增断言：零写入和确定性；完整归属可由严格既有snapshot模型重建；没有root绑定/旧回执；
未知source、provider缺失/错根、缺文件、文件hash漂移、symlink、非conformant分析均拒绝；
API只读执行中并发变动拒绝；CLI中英文可读摘要与单列JSON输入。

预期：本轮定向pytest全部通过，源代码静态检查通过；结果另记。开发测试不代表已安装能力。
恢复入口将在下一切片复用这一输入，先补目标注册/CAS/不覆写/reader/source再验证边界，
两者完成后作为一个完整hotfix能力批次正常发布安装，才对现有单篇test做安装态验收。

## 恢复侧：目标归属恢复（开发切片）

公开 restore-plan/restore 接收导出的 JSON 输入和已登记的目标 Source。用户先通过现有
registration-plan/register 附着复制后的 fields.yml；恢复不会替用户选择目录、复制正文或
初始化第二份注册表。目标 provider 必须不存在；创建只写主机 provider 和独立恢复 journal，
不改 Markdown、Canvas、sidecar、便携 manifest，不导入旧主机回执。

计划绑定 package 字节、目标注册表/根身份、完整文件 read-set 和当前 Zotero Local API
论文/附件归属与 PDF hash。PDF/批注不复制；科学论证和摘录充分性仍需原有来源审阅。
保存的 ZotFlow reader ID 与目标打开位置分别核对，不能直接用旧 ID 宣称恢复后可点击。
reader 不匹配或本机能力尚未验收时列为待复现项，不自动改写成对分析或启动应用。

独立测试输入先于实现准备：合成单篇、相同便携 manifest、另一目录、另一 host registry、
独立 Local API 替身。检查零写入计划、精确恢复/幂等、已存在 provider 拒绝、文件/输入/注册表
变动、错误 Zotero 归属/PDF hash、symlink、journal 篡改、中断后续接及并发编辑不覆盖。
结果写入独立 results；本轮不操作真实 Vault、项目、服务或正式文库。
