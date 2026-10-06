# Canvas 配对正文反链：最小修复与独立测试

## 已观察问题

安装版 0.41.2 的真实 V-JEPA 2 图卡能显示图 2、表 2，但正文反链实际进入旧同名候选。
独立的 A/B 同名笔记测试再次复现：短名称、`./` 名称、普通鼠标点击都进入 A；明确 Vault
相对路径准确进入 B 的指定块。静态解析提供来源路径时命中 B，不能代替实际点击。
具体第三方组件根因尚未证明，不修改 Obsidian/Advanced Canvas 或其设置。

## 修复边界

在现有 v5 profile 增加可选 `canvas_note_path`：安全的 Vault 相对 `.md` 路径，属于显示路由，
不是对象身份或文件授权。所有 claim/point/图卡的正文反链投影到该文件；basename 必须匹配
实际配对 Markdown。旧包未声明时序列化、节点内容及兼容行为不变。

已有包通过明确 whole 成对格式更新采用或重新绑定该路由，focused 更新保留它。正文、原文
摘录、source identity、节点 ID、几何、边与人工内容不应改变。正式提交额外从可信 Source
及非秘密 Obsidian registry 推导实际配对正文路径，拒绝伪造目标。迁移/复现只报告新位置
是否需要显式路由重绑定，不自动改内容或放宽 Source 权限。

保留五分支、对齐、无交叉、关键流程图/实验数据表限定。规范只写末端结果与真实调用边界，
不增加内部阅读或推理流程。候选演示、正式提交、人工美观和 main 合并分别判断。

## 测试输入、预期与影响

1. 固定已有 synthetic v5 fixture，手写期待的完整反链路径及块标识；有/无新字段的渲染、
   成对校验、序列化与 explicit whole / focused 更新。正文、图几何及边必须精确保持。
2. 合成图卡核对相同反链目标；短名不残留。JSON Schema 与 Pydantic 对绝对路径、URL、
   `..`、反斜杠、片段/管道/括号、空路径、非 Markdown、错误 basename、v4 使用均拒绝。
3. 临时合成 Source / Obsidian registry 检查正式提交的匹配/错目标/无法解析边界；错目标
   在任何 Vault journal 或覆盖之前失败。与既有 reader 无关的路径不授予外目录权限。
4. 复制 Source 的合成检查区分 matched、rebinding-required、reader-unresolved；同一个 Vault
   ID 但 Source 位置变化不能误报路由可用。该检查不打开工具或宣称 human/reproduction pass。
5. 修改后运行受影响 unit/contract；提交前运行完整 unit/contract 与版本/eval schema 检查。
   只影响仓库测试输入、代码和 pytest 临时对象，不做真实批量操作。
6. 必须正常发布安装的 hotfix 后才用 test Vault 单篇候选做产品实机验收；实际点击核对
   文件与块，保留旧候选作对照。旧分析或图卡不能通过手工改一个受管文件来验证。

可见产物：独立 A/B 诊断已在 test Vault；开发测试结果留本计划对应结果记录。尚未测试、
发布、安装或修改正式分析。完整阶段目标不缩小，外部工具/图片人工评鉴及项目覆盖授权仍待完成。

## 2026-10-06 发布前测试输入纠正

干净HEAD对照证明两个旧测试不是新代码回归。进一步独立输入复核：当前指定ruamel安全
解析器拒绝flow列表中的未加引号analysis:...值，明确加引号后保持同一字符串身份并成功
解析。旧PDF测试只创建storage目录，但真实路由早已从Local API解析locator，不再扫描
storage；缺少API fixture时必然依赖本机文库并返回404。

仅纠正这两个测试输入：flow列表明确字符串引号；PDF fixture注入受控Local API adapter，
对指定key返回现有合成PDF，未知key明确报错，解析调用留痕并核验。保留空目录/未知key/
非法key拒绝测试，不改生产解析器、服务、adapter接口或猜测storage路径。关闭合成server
端口以免测试资源残留。先运行受影响附件/兼容HTTP用例，预期保留坏hash与悬空owner分别
诊断、成功PDF确由fake API locator提供而不依赖真实Zotero。通过后完整unit/contract验证，
再正常打包发布并安装0.41.3，单篇实机验收依原计划；没有整库业务或服务切换。
