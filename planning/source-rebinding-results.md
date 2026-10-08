# 同目录设备号恢复：独立验证结果

对象与影响见 [测试方案](source-rebinding-plan.md)。仅同路径/inode设备号恢复，
既有正文、Canvas结构与来源证据不改，不扩展到目录搬迁或缺失provider初始化。

## 开发态实际结果（2026-10-08）

- 先新增合成契约测试，实际 RED 为新模块/入口缺失导致 collection error；未把未运行当通过。
- 实现后初始受影响组合76 passed；再补10项边界，新恢复测试共26 passed，相关组合86 passed。
- 覆盖零写入、binding-only/幂等、不改变catalog/归属/历史回执；完整分析/资产/导航读集、
  缺失/禁用/只读Source、路径/inode不同、符号链接、目录替换、检查期间改动、摘要过期、
  prepared/provider-rebound中断恢复与journal篡改。原commit/export安全检查保持。
- Ruff首次指出新文件两处import排列，机械格式修正后通过；git diff --check通过。
- 完整 `tests/unit tests/contract`：1855 passed，11条既有PyMuPDF/SWIG与多线程fork弃用警告，
  89.85秒，无失败。输入仅隔离fixture，没有真实业务写入。

## 安装态独立验收

0.41.4已正常提交发布安装：source f659631 / runtime992ae22。PATH CLI、pipx固定Git
提交、cache两manifest及skill/复现契约/module字节一致。marketplace首次HTTPS连接拒绝；
仅本次installer改用同仓库已验证SSH通道，正常upgrade/add成功，没有手改cache或全局Git配置。

仅已获批test V-JEPA2 Source：公开预览15文件，digest确认恢复同目录设备号。独立比较证明
全部文件/manifest、catalog、归属、历史回执保持，仅binding与派生snapshot revision改变。
fresh CAS新操作batch复用既有IR，零修复validated；69内容、旧106节点105边/样式/布局保持，
仅图2/表2两卡与71准确正文反链新增。public paired commit/provider apply完成；正式包
conformant、完整15文件/6资产exportable。正文原字节未改，原PDF及12非trio文件保持。
观察器初始将未排序stage与排序canonical的Canvas/sidecar JSON做byte比较而误报；只修观察器，
实际完整对象及回执物理hash均通过，没有重新提交或弱化生产检查。

## 新根预览发现的窄修复（0.41.5）

当前新目录仅copy这15明确文件并public existing-source登记到隔离host state；生产registry/
provider/Source保持。恢复尚未执行，读者诊断漏了paper子目录。根因baseline tuple第一项
是resource ID，被误当sidecar path；目标显示路径应来自已验证的owned Markdown artifact。

独立测试输入为已有合成嵌套paper包，分别保存匹配/旧目录route。预期zero-write restore-plan
报告完整目标路径并正确区分binding-matched/rebinding-required；未知root/source/权限不变。
先实际得到2 failed（实际copied-source/Analysis.md，期望含resources/papers/synthetic/），
再修reader诊断调用。网络uv获取失败只影响开发工具；offline缓存运行实际RED成立。
本次只读目标定位，未修改真实论文，待定向和完整unit/contract通过后正常发布安装0.41.5，
复用同一新目录及包完成一次恢复/反链更新，不另造重复对象、不重分析/实验/裁剪或人工评鉴。

修复后相关组合88 passed。第一次完整回归1856 passed/1 failed（91.17秒）：旧unit用例仍
用两参数调用改为三参数的内部reader helper，未提供owned Markdown snapshot。只修该合成输入，
保留同Vault换目录必须重绑定断言；不回退到错误resource-ID路径或放宽生产检查。
调整fixture时曾误引用AnalysisDocument不存在的resource_id，定向1 failed/61 passed；改为
真实synthetic资源identity后62 passed（1.59秒）。完整复跑1857 passed/11既有弃用警告
（88.93秒）；Ruff和diff检查通过。

## 0.41.5 安装及同一新目录复现

source045085e/runtime65d0754正常发布并安装。244 runtime文件边界通过；首次路径扫描
将4个解释跨机漂移的`/Users/…`占位示例误报，逐项核读后精确排除该字面示例，其他个人
路径/密钥模式扫描通过，没有改产品文件或放过真实路径。SSH市场upgrade首次超时/early EOF，
正常HTTPS重试成功；公开plugin add安装0.41.5。pipx direct_url固定提交、3个已安装模块及
cache两manifest/skill/reference/两module共6项发布字节一致；未手改cache或全局Git配置。

只复用此前唯一新目录：公开新restore-plan准确报告完整paper子目录路径，fresh digest
4b395535dd0c098ce0dce7f9bb9524b031506fcb0db0ae44130dc188727dbd47获此前同范围批准执行。
public restore仅初始化隔离provider，15文件字节不变，再导出摘要与原包相同；之后whole
paired stage零修复validated，独立比较只有71正文反链的目录路由改变。public commit/apply
完成，13非Canvas/sidecar文件保持；正文、来源、图片、节点几何/样式/边全部守恒，108节点
107边，正式check conformant，当前15文件包可再次导出。最终摘要因合法反链更新而改变，
不能宣称更新后仍与原包完全同hash。原Source/生产registry/provider及PDF保持。

用户旧图片评鉴通过并持续有效。Mac锁屏，原生显示和两卡准确点击尚未复验；未使用旧截图
或静态解析冒充本次实机结果。可读结果、安装记录、独立比较及全部CLI回执保留在test既有
审阅目录“复现/正式采用-20261008/0.41.4”，名字保留创建时版本，实际恢复使用0.41.5。
不重分析/裁剪/实验，不合并main/切换服务/迁移其他集合；科学空缺和完整G17边界保持。
