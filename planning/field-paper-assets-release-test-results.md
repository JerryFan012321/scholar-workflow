# 0.43.1 附件清单 hotfix：发行与安装结果

2026-10-10，用户明确授权提交、发布和正常安装。先行范围与预期见
field-paper-assets-release-test-plan.md；不合并main、不切换服务、不改论文正文/Canvas。

## 发布前实际证据

| 检查 | 结果 |
| --- | --- |
| 当前功能代码完整unit/contract | 上一轮2525 passed / 11既有warnings，107.65秒；含39资产用例，功能代码未再改 |
| 版本后必要回归 | runtime版本、双manifest、eval schema、附件和论文清单共95 passed，3.00秒 |
| 版本一致 | 两manifest、包版本、模块版本及lock本包均0.43.1，依赖未变 |
| 16个skill基础校验 | 全部通过；未改description/触发方式，不冒称宿主或人工验收 |
| 五个修改Python Ruff | 离线检查全通过 |
| diff | 通过 |
| 独立运行期审查 | 8个相关runtime文件无阻断项；未见开发层/私人路径/密钥泄漏或扫描、内容读取、写入权限扩大 |

本轮不重复全量功能测试或任何业务分析/实验。独立审查不代替测试、安装或GUI。
上一完整回归的红测、边界修正及失败观察保留在field-paper-assets-test-results.md。

## 发行、安装与单对象复验

| 对象 | 实际身份与结果 |
| --- | --- |
| 功能source | bed3bddc4c87cc0e9a9093194ebe9380efe33416，23个明确文件，提交后干净 |
| runtime | 8c4832b0e6ad8e44224460af6dc51a1d4cbec61f；直接父3275a80，既有make-release生成 |
| 推送 | hotfix与release正常原子fast-forward；main保持ccb60b793d9fd5db6032499bf2ca2c8dda3f1183 |
| runtime边界 | 16项allowlist、262文件、3,246,515 bytes，path/mode/blob全等；无dev层/symlink或高置信私人路径/密钥 |
| 论文保护 | 35个analysis模块、paper skill/schema及Canvas文件与上一runtime全等 |
| wheel/sdist | 111个包文件与runtime全等 |
| 正常pipx | 固定runtime SHA安装0.43.1，Python3.14.5；direct_url的requested_revision与commit_id均正确，111包文件全等 |
| 正常Codex插件 | marketplace upgrade/plugin add成功，0.43.1；16skill、双manifest正确，262运行文件全等，cache HEAD为固定runtime |
| 单Field实际查询 | 安装CLI两公开查询exit0，1论文/10文件，其中6资产与执行前原声明对应；4安全URI静态对应，issues为空、status complete |
| 样张与原件 | 2673字节stdout全等；77保护文件集合/大小/hash不变 |

构建目录为忽略的dist/0.43.1-release.MbNcGB，不切换用户工作区分支。
初clone取到陈旧本地release852f983，生成0624459未发布候选；保留该候选branch后fetch
远端3275a80，并由原脚本重建最终8c4832。两树相同，未force或覆盖远端历史。
初cache核对把安装器30项.git元数据计入而失败；未删除或手改cache，只按已声明runtime
边界排除该元数据后核对262文件全等，并验证Git HEAD。不是产品文件不一致或功能失败。

| 产物 | SHA-256 |
| --- | --- |
| runtime.tar | c8167ff3feadc0984b9568a39cb257464d15a4d3a9665907e8daf4557e47958b |
| wheel | 07b87a1a08ccfa60422b50463a1773604039785e3aa13955874302d15ca87085 |
| sdist | 0ea1270a3fc69e96539a7b54e593a7582c05d87ff357ce037db5705388a6ed37 |

正常安装命令：

```text
rtk proxy pipx install --force git+https://github.com/JerryFan012321/scholar-workflow.git@8c4832b0e6ad8e44224460af6dc51a1d4cbec61f
rtk proxy codex plugin marketplace upgrade jerry-plugins --json
rtk proxy codex plugin add scholar-workflow@jerry-plugins --json
```

0.43.0回退runtime为3275a80a50dcb031c1bf0a3d785a28df3069f1fc；pipx同命令换固定SHA
可重装。旧Codex缓存保留，回退须正常版本固定入口，不手改缓存或假称latest add能降级。
当前会话原skill目录快照不自动变化；本轮明确完整读取实际0.43.1 skill及必读refs执行。
可见清单、独立命令/机器记录及结果唯一留test上层组合审阅目录，旧0.43.0失败不覆盖。
独立只读复核确认权威声明与输出一论文/十文件、六资产的ID/path/owner/role及四URI静态
路径完全对应，6资产size与声明一致、样张stdout全等；保护记录77项及当前70/5文件集合
一致。复核未重跑CLI、读取正文/图片或重hash，不把元数据size当附件内容hash验证。
查询无网络、应用打开、正文读取或业务写入；保护检查仅对先行选定77文件取hash。
PROJECT/实验报告、清单原生点击及人类阅读体验仍待评鉴，原论文体验不重审。
无main合并、服务切换、Zotero写入、实验执行或正式资料迁移，G17整体未完成。
回填安装与复验证据后，10项eval schema再次通过（0.02秒），diff检查通过。
面板打开新清单只返回queued，不算原生阅读或人工通过。收尾仅提交开发回执，
不重新生成runtime；安装始终绑定上述bed3bdd/8c4832的功能source与发行。
