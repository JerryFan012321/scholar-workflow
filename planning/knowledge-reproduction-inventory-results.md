# 归属复现输入：开发结果

## 已实现

开发树新增公开只读`knowledge reproduction-plan --source-id UUID`，默认中英文人类摘要，
JSON模式分列完整版本化复现输入。输入只含明确Source/Field、provider归属和相对文件/hash，
不包含主机根绑定、旧provider回执、运行诊断、PDF文件、密钥或正文副本。
既有正文/sidecar中的阅读器投影不被偷偷改写；须重新绑定的分析另列，目的地恢复仍是独立步骤。
已登记分析必须有同owner、同folder的完整三文件且格式/基线通过，不能导出半包冒称完成。

新公开schema复用已有provider/manifest/change-set契约，并收窄host绑定/历史回执。
只读执行末尾复核完整读集，包括原先不存在的artifacts.yml；并发变化不给出过期成功输入。

## 独立测试实际结果

输入：合成单篇Source、已注册合成分析，fixture在隔离pytest目录，不使用真实资料。

- 实现前：新增测试在收集阶段报未实现模块，退出2；不记为业务测试通过。
- 初版15项通过；补并发、只读能力、禁用Source等后，22项及旧登记回归72项通过。
- 最终26项新增及既有登记/评估schema定向组合：86 passed，1.64秒。
- Ruff指定三个变更Python文件通过，diff空白检查通过。
- 增加公开JSON schema核验时发现旧Hub schema采用相对$id，独立本地schema registry需登记
  同一资源的规范绝对alias。首次组合85通过/1失败，修正测试resolver后通过；未修改旧schema或业务逻辑。

## 尚未完成

没有提交、发布、安装此新切片；当前安装仍0.38.3。没有用开发树对真实test Source执行导出。
以上为导出阶段历史边界；下方恢复开发结果覆盖“恢复入口尚未实现”，不覆盖安装/真实重建未完成。
两侧完成后作为一个完整hotfix批次发布安装，再进行单对象安装态复现；G17仍active。
既有项目context的覆盖授权仍未收到，不覆盖它，也不重做已认可的论文格式或已提交摘录。

## 恢复开发切片：已实现，未安装

公开`restore-plan/restore`接受导出JSON或其中的原始package、明确已附着的Source及审阅摘要。
预览零写入；恢复只创建缺失的本机provider及独立持久journal，所有复制内容字节不变，稳定
Source/Field/resource/artifact ID保留，provider绑定新目录且不导入旧回执。现有provider拒绝。
完整输入/注册表/根身份/文件hash与Local API论文、附件、PDF绑定；同一摘要可中断续接，
人类修改、并发provider和journal篡改不覆盖。ZotFlow reader变化列为待绑定，不伪称已打开。
默认中英文人类摘要与JSON机器记录分开。共享运行契约及论文复现指针已补齐，不改输出模板。

合成输入是一个已有单篇fixture，复制到另一目录、另一host registry，原源/状态保持不变。

- 实现前测试收集报缺少restore接口，退出2；该状态是预期缺能力证据。
- 首次实现后26导出通过/12恢复夹具错误：existing-source漏传field_root=None，恢复未执行。
- 修正后11恢复通过/1反例构造失败：篡改root后snapshot_revision未重算，尚未触达portable门禁；
  重构反例为严格模型合法但携带host binding，业务门禁如期拒绝。
- 26恢复（含CLI、并发、journal）+26导出+既有登记/schema组合112 passed，2.51秒。
- 后增reader与PDF反例首次28通过/2夹具错误：新的artifact hash未同步其catalog revision。
  修正完整合法投影后30恢复全部通过，1.27秒；不修改业务检查或放宽格式。
- 四个变更Python文件Ruff通过，diff空白通过。完整unit/contract：1676 passed、11既有
  DeprecationWarning，84.43秒；无失败。

这不是实机/安装态验收；没有调用真实Source导出/恢复，没有打开应用或写Zotero。
当前安装仍0.38.3。尚需同批发布安装、单篇目的地真实重建、外部工具/reader与人工确认；
科学支持不由hash与归属校验认证，G17仍未完成。

## 0.39.0 安装态结果补充

上述未安装/未执行是开发阶段边界，现由hotfix-0.39.0-results.md的实际证据更新：正常release及
pipx/Codex安装已完成；installed public导出、明确复制、existing-source attach、restore和重放
在同一test Vault新目录执行，使用隔离host registry模拟新主机，而非宣称另一台物理机器已实测。
原8文件与稳定身份守恒、provider主机绑定重建、回执幂等、目的地导出摘要吻合、原保护hash不变。
新Markdown和Canvas被Obsidian backend载入，结构检查零问题；Mac锁屏下截图已排除，GUI未验收。
科学、真实reader点击与新摘录人工阅读
保持独立pending；不扩大到正式Vault、项目context或整库迁移，也不重复已认可的图。
