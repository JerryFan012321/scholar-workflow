# 完整五分支：下一轮安装态单对象验收

## 已获授权（2026-10-22）

用户已明确授权0.47.2提交、正式发布、正常安装及同一test对象的新隔离批次回放。
下方“待授权”是准备时点的历史记录，不再阻塞本轮；未扩大到新对话、真实重新分析、
正式归属迁移、Zotero/服务器/服务或main。安装态与人工结果仍须实际执行后记录。

## 当前结论与权限

拟以0.47.2 patch承载当前可见文字测量及v5比例提醒修正；版本号、source提交与runtime
提交尚未固定，不能写成已发布。开发分支为`codex/hotfix-dense-analysis-layout`，
HEAD仍为`d0a56b2`，main仍为`2e3c61f`。3271项单元/契约回归通过，11项既有警告；
Ruff、skill格式和diff检查通过。它们不证明已安装能力、论文完整交付或人工通过。

2026-10-22只读核对：正常PATH CLI仍0.47.1；原输入hash未变，原回放DB仍为
failed/repair_count=1/stage_path=null。新比例策略的源码和skill已完成，但尚未
发布安装。以前0.47.1的发布/安装/回放授权已执行完，不覆盖本计划。

**待明确授权：提交、正式发布并正常安装新的hotfix，以及在同一test对象中创建一个
独立新验证批次回放保存输入。** 不修改或清零旧DB，不把新批次伪装成旧失败重试。
本文件仅准备输入、预期、影响与停止条件；本轮没有执行其中的发布或业务写入。

## 离线打包预检结果（2026-10-22，非发布/安装）

当前运行源码没有再变。按make-release.sh的实际RUNTIME_PATHS和tracked文件列表，
将当前未提交字节复制到独立临时目录，离线构建wheel；没有运行会切分支/提交的
release脚本，没有安装预检包或运行真实论文。版本元数据仍是源码中的0.47.1，
不是拟议的0.47.2发行包，后续升级版本并固定源码后须重新正式构建和核对。

| 检查 | 实际结果 |
|---|---|
| runtime集合 | 293文件与当前源码字节/权限一致；无遗漏的未跟踪runtime输入 |
| 发布边界 | 不含planning、tests、evals、dev-guide、根AGENT/CLAUDE或Git库；构建器临时元数据不在发布清单 |
| wheel | 126包文件的路径/字节与源码一致；Python AST可解析、console entry匹配pyproject |
| skill与明确根引用 | 17个skill、93处明确带扩展名PLUGIN_ROOT文件引用均存在；不声称已验证所有动态引用或宿主路由 |
| 版本 | pyproject、wheel、两个plugin manifest均0.47.1，未冒称已发布0.47.2 |
| 限定隐私扫描 | 个人home路径、个人代理端口和独立key前缀形状未命中；不是全面秘密审计 |

运行集合摘要为按路径排序的`path/mode/sha256`记录的规范紧凑JSON SHA-256：
`c2d6f0b5addd445b7a2fce6ed0862fd296d987f2c085c03d41e8dd949dab38d8`。
临时wheel SHA-256为
`236029422ef8f9996a858149a8d7346543b40f29b5d4f762752b4cc401d855d6`。
这些只绑定本次预检字节，不是固定source/runtime提交或可安装发行身份。

首个限定key探针在CHANGELOG的普通`ask-before-...`措辞内部误认`sk-`；未输出匹配
值、没有修改产品或删文字。为探针明确token边界后，先用6个独立合成正反例核对
key/端口与普通单词/hash的区别，再重查293文件通过。此为检查器修正，不计入
3271项产品回归，也不升级扫描证明范围。临时构建内容在取证后清理，不提供安装。

## 唯一对象与冻结输入

test Vault内仍只使用`Scholar Workflow 实验/单篇生成验收`；不新增另一个论文副本。
现有`V-JEPA 2/`仅有11张选定图表和候选状态说明，主分析三文件尚未出现。
本计划通过后在该位置交付，不另建版本命名论文文件夹。

保存输入位于该对象的`_工作/vjepa2-oneshot-0470/input/`：

| 文件 | 当前SHA-256 | 本轮用途 |
|---|---|---|
| batch-request.json | 894b93894a07444a7fe0f1645e96a0f887f49813a60a540907ce22cb3026f32c | 只回放其原分析IR，不重新分析论文 |
| repair-request.json | 3eaa18b781649a218b8911b07d9d859ea14c840ea3826eb5fc732d337ca6eef9 | 仅保护，不提交修复、不消费第二次repair |

原输入的item_id为`vjepa2-t3ry3hua`，note_stem为`V-JEPA 2分析`，
artifact_id为`analysis:candidate-vjepa2-oneshot-20261021`。
声明whole/reference_tree_v5、完整五角色、41 claims（含11结构容器）、97 points；
折叠摘录、正文源图、Canvas来源去重和明确正文反链路径均已启用。
本次11图是冻结输入的实际选定资产，不是其他论文应照搬的图数配额。

原request保持原字节。新验证请求只显式另取batch_id（建议
`vjepa2-aspect-advisory-0472`），其他字段与原文档对象完整相同，保存差异证明。
新DB/stage仅放在原工作目录下一个新的受控验证位置；路径若已存在即停止，不覆盖、
清理未知内容或默默换名字。这个新批次需要上述明确业务授权，不由测试原则自动推出。

## 重要限制：旧输入不是ZotFlow阅读器投影

原输入实际声明`reader.kind: zotero_native`，不是ZotFlow。其正文反链明确指向
`Scholar Workflow 实验/单篇生成验收/V-JEPA 2/V-JEPA 2分析.md`。

此次若严格回放原输入，应保持这个阅读器声明，不手改Canvas或暗改IR。链接正确
只能证明相应Zotero原生入口，不能冒称满足用户期望的Obsidian内ZotFlow入口。
ZotFlow入口仍是独立未关闭项：后续须在实际安装与本机PDF模式正向核实后，显式
采用相应完整输入/格式操作并真实点击，不能把旧原生入口当作替代验收。
此处不重新打开用户早已通过的旧ZotFlow链接评鉴，也不宣称新候选链接已点击。

## 安装态操作与独立预期

1. 固定干净source提交，从已有release历史按现行runtime白名单构建并审核：版本、
   mode/blob、skill闭包和个人信息边界；正常发布hotfix/release，不推main、不force。
   pipx与Codex marketplace走普通更新入口，不用源码直跑、临时venv或手改缓存代替。
   安装后核CLI/distribution/direct_url/双manifest及包、缓存和runtime的一致性。
   回退入口为现用0.47.1 runtime `5037fcf1426d268b59bdbea3aed774c351b4f3d8`；
   不宣称完整Codex降级已演练。正常安装器可能替换旧缓存，不能错误承诺全部旧缓存保留。
2. 安装后另立当轮保护指纹：原输入/失败DB/回执、既有论文包和所选图像；不覆盖旧
   825/879保护清单。只验证当前输入与已有来源证据的身份/字节连续性，不重复整库
   扫描、全文分析、裁图或科学实验，不把原169跨度的页级/字面证据升级成语义认证。
3. 经批准后在上述新隔离批次中运行正常安装的`analysis batch-run`，不带
   `--repair-request`。预期completed/validated、repair_count=0，交付stage三文件。
   若整体仍超过2:1，必须报告warning/repairable=false，不可因此失败或自动修复；
   若布局本身已满足比例，不人为要求生成一条警告。任何硬错误仍须失败。
4. 按冻结IR逐项核全部claim/point、五主分支、具名子槽、父子关系、证据/源入口/
   对应正文反链与11图保留；无正文机器claim注释，无独立Evidence树，不删内容、
   缩字、合并点、拆图或添空白大框。检查420px、文字点击区、同层对齐、无交叉/
   穿框/遮挡和图片可读尺寸。sidecar必须持有实际原IR，不使用旧摘要修复作为新答案。
5. 相同新请求再调用一次，应返回完全相同的保存结果，不再渲染、不花repair。
   原failed记录/预算1/输入hash不变；通过只证明新版本新验证批次，不反写旧历史。
6. 确认原候选目录的三个目标仍不存在后，按现有非canonical review-copy契约以
   正确文件名、拒绝覆盖的方式展示stage内容，复用现有相对图像，不重裁或复制一套图。
   公开`analysis check-bundle`以真实名称检查三文件及显式图片，预期conformant、
   原始warnings可见、文件hash明确。该步骤不登记正式owner，不伪造commit/provider回执。
7. 用原生Obsidian展示同一候选，给出正文与Canvas的明确入口。用户只需评鉴受影响
   的完整图布局与新正文：五分支是否齐、文字/图表能否读清、对齐、线不交叉、链接
   可点且回到确切正文块。说明旧输入会打开Zotero原生阅读器，不称ZotFlow通过。
   在用户明确确认前，新候选的人工评鉴保持待确认。

计划预期的可见三文件为现有`V-JEPA 2/`下的`V-JEPA 2分析.md`、
`V-JEPA 2解析树.canvas`与`analysis.baseline.json`；名称及baseline stem须一致。
工作/验收回执留在原对象的`_工作/`和`_验收/`，按现有Git管理，不散落到临时Vault。

## 失败停止与不包含的工作

输入/hash/归属变化、版本身份不一致、目标已存在或硬格式错误均停止，保留诊断。
不重置任何DB、不修改SQL、不追加第二次repair、不手改成品来掩盖失败；先回到
合成开发检查。整图比例warning不能掩盖硬错或算成人工视觉通过。

不含新建/续发对话、正式Vault/Zotero写入、服务器、服务切换、main合并、重新分析、
批量迁移或备份。此轮是保存IR的安装态回放，**不是新对话one-shot生成证明**。
新宿主独立生成、完整知识归属采用、模范项目/实验与外部工具各项证据仍按G17分别
闭合，不能因这份单对象计划或比例修复缩小原目标。
