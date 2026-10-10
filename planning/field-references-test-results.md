# Field 引用兼容与只读解析结果

日期：2026-10-09。状态：开发树通过；未提交、发布、安装或人工导航验收。
分支：`codex/hotfix-knowledge-ownership`。正常安装保持 0.42.0；本轮未改变版本号。

## 实际交付

`fields.yml` 显式 schema 2 的 Field 引用包含引用 ID、稳定 Source/object 目标和用途。
既有 schema 1 输入/序列化不添加空字段、不自动升级；原 navigation 及本地文档授权不变。
两个 Field 可引用同一论文包，引用不进入 owner placement。源归属/路径仍由 provider 持有。

`knowledge list` 显示用途而不读取 provider；可选 `--resolve-references` 组合既有声明，
分别报告归属、文件可用性及未验证阅读器。来源限定不掩盖全局重复 owner；失联或目标不匹配
保留引用并显示 incomplete，未知对象 not_found，文件缺失不伪装成身份丢失。
中英文可读输出不重复机器 ID/hash/绝对路径，不生成不能点击的相对 Markdown 假链接。
默认 list 仍保留已有本地导航文档的有界 owner-header 检查，不能说它完全不接触正文头部；
引用 resolver 本身只读取声明与文件 metadata，不读取论文/分析正文。

复现包保留 schema 2 引用结构和 `fields.yml` 实际 hash；不导出外部被引用正文/PDF。
历史论文/Field迁移重建时保留版本与引用，旧 override 缺省引用则继承，显式改变则拒绝。
直接 FieldService 追加也保留原 Field 和引用。没有新增 owner 或 field-context 台账。

## 独立预期与执行记录

输入/预期先于产品修改：`field-references-test-plan.md`、
`tests/fixtures/field-references/EXPECTED.md`，以及三个新增 contract 文件。
全程使用 pytest 临时 Source/provider/registry 和合成论文包，没有真实业务执行。

1. 旧入口初测 7 失败（0.50 秒）；候选入口名、缺 `.obsidian` 的 Vault 夹具分别纠正，
   第二次 7 失败（0.27 秒）仍有一个候选输入错误，不把它算作产品缺陷。
   修正后 schema/旧入口合跑 63 项为 15 失败、48 通过（0.35 秒），明确暴露新版本
   未支持、布尔 schema 被接受和公共映射缺口。
2. 解析初测 15 失败（0.52 秒）：12 项因 schema2 未实现、1 项缺函数；另外两项是
   合成空 provider 未清旧 catalog revision 的夹具错误，保留独立预期，只修输入。
3. 模型/解析实现后 78 项为 76 通过、2 夹具失败（0.45 秒）；纠正 revision 后，新增
   CLI/直接追加合跑 35 项为 24 通过、11 失败（0.82 秒）。其中 5 项暴露缺可选 flag，
   6 项是观察器误把既有本地导航 header 安全检查当正文读取。观察器只为 CLI 明确的
   home 文件开放累计不超过 64 KiB 的 `os.read`；其他完整 stream/pread/readv、论文正文、
   网络、执行和写入继续拒绝，原 ownership 测试默认白名单保持空。
4. 新增动态 schema 独立用例后，117 项为 113 通过、4 失败（0.56 秒）：动态 schema
   漏表达 schema1 禁止 refs，随后补条件分支。
5. 独立审阅再补 purpose 端点控制字符：135 项为 120 通过、15 失败（0.57 秒）。
   静态正则两端及动态 schema clean-text 约束不足，修正后 135 全通过（0.60 秒）。
6. Ruff 首次 19 项为导入排序、字符串括号及 fixture 注入声明等静态问题，最小修正后通过；
   没有改业务预期或去掉断言来适配实现。
7. 同一 clean-text 映射复核新增16项末尾换行案例；schema专项116项为104通过、12失败
   （0.33秒），Python模型原已拒绝，静态/动态JSON schema 的 `$` 仍在末尾换行前匹配。
   补显式控制字符拒绝后，全范围681项通过（19.27秒）；不降低Python既有校验。

## 定向联合回归

151 新项，加既有归属、登记、Source 初始化/竞争、复现/恢复/资产、重绑定、Canvas登记、
历史 Field/论文迁移、锁次序、模块责任及 eval schema：
首次联合 **665 passed，19.41 秒**；补充上述16项后最终联合
**681 passed，19.27 秒，5 个既有 PyMuPDF/SWIG 弃用警告。**
这不是全发布回归、安装态或人工评鉴，也不是再分析论文/运行实验。

新增文件：

- `tests/contract/test_field_reference_contract.py`：116项，含静态/动态 schema、旧形状、
  引用边界、复现 metadata 和文件授权。
- `tests/contract/test_field_reference_legacy_preservation.py`：9项，历史与直接追加版本/引用保持。
- `tests/contract/test_field_reference_resolution.py`：26项，唯一/冲突/失联/缺失及双语 CLI。

## 尚未完成

安全增删引用的零写入预览、摘要绑定、CAS/恢复事务尚未实现。
本开发切片尚未正常 hotfix 发布安装或在 test Vault 验收；当前人工没有新任务。
PROJECT/literature 候选仍各自待评鉴，论文五分支/Canvas/图片/折叠的既有认可不重开。
正式资料、Zotero、原项目、服务及 main 均未改；G17 完整目标仍未完成。

## 可见清单

使用同一合成 fixture，调用真实开发 CLI 回调输出中文清单，退出0；
精确读写 guard 前后文件保持。可读结果见 `field-reference-demo.md`，
不是已安装入口、真实论文科学结论或人工导航验收。
