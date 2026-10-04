# 0.35.0：已有论文包的公开只读检查

日期2026-10-05。独立 `codex/hotfix-project-context`；main不合并，G17未完成。

## 实现与独立验证

新增public `analysis check-bundle`，只读取一个显式目录下三个显式文件。
复用正式conformance与baseline；不生成新IR、不修复正文/图、不写registry、不启动Hub。
Markdown文件名也校验，避免仅内容正确而实际Canvas反链无法解析；可以明确要求IR5。
人类输出中英文可选，machine JSON分离文件hash和finding。

独立方案见 `analysis-package-check-test-plan.md`。固定synthetic scalar reader38条输入，
定向90通过（1.33秒）。扩充原始hash/相对目录/额外Canvas字段后完整1481通过、1失败
（78.27秒）：门禁已拒绝，但测试误用legacy诊断名称。只改断言为现有v5代码，门禁不变。
最终完整1482通过、11既有警告（77.07秒）。新module/test Ruff、skill frontmatter和diff通过。
旧cli.py四项I001仍位于1607/1635/1722/1816，未改其导入或业务行为。
uv.lock的旧包版本0.32.0仅同步为当前0.35.0，不升级依赖。

SKILL description/路由未变；三份eval审阅，新增只读非批准的safety和installed outcome pending。
skill-creator使入口细节归入已有reproduction reference，不新增通用思考流程或另造格式。
json-canvas保持既有五分支、编辑性、对齐/无交叉标准，不重画V-JEPA2。

## 安装态计划与边界

通过正常runtime-only发布与pipx/marketplace安装，再仅检查0.32.3现有V-JEPA2资料包。
检查前Markdown hash f2f1c0df1eafc915ab2d2433bc70bab501d9a0c2a41e571ba94c4978ac2c7559，
Canvas ae474839336040886b8b92e223d440c206627365eb24264de1046fcdd2fff4f1，
sidecar 377a12871bd11a5b4c9b060012f17bb93d2485945f8424060faec46d4293e662，
registry 51dad852da65215021a6fed146486e226571b051313195b083eb01d1ad994b5f。
旧安装0.34.0 runtime7afea994bcb90e58a07240a2d934c2022fc85e89为回退点。

新可见报告只放test新“论文包检查-0.35.0”文件夹，与原正文/Canvas链接；原件不搬迁。
Source/Field独立登记/v5联合事务、完整科学支持、外部reader当前状态和人工评鉴仍未完成。
不能用只读绿灯替代上述验收或把旧v4迁移接口当新版登记能力。

安装与实际结果待下节记录；不关闭服务、worker，不写正式Vault/Zotero，不合并main。

## 正常发布安装与单篇实际结果

- source `4c630effe7ffd497d5971a1f9ff48800fa707a42`已推hotfix。
  make-release从干净临时克隆生成runtime `d83cd40c68c8e9083bfaf138f55bff01bc62b4cf`，
  runtime根边界正确，无开发层/测试/个人路径/明显密钥，已推release。
- pipx按runtime SHA正常更新，Codex marketplace upgrade/add正常安装cache0.35.0；
  CLI、模块、distribution、plugin manifest均0.35.0，direct_url的commit/requested_revision吻合。
  不手改缓存，不切换服务，不合并main；0.34.0原runtime为回退点。
- 安装版public check-bundle以实际三个文件名和require-ir5执行，JSON/中文报告均exit0。
  实际68条独立内容、105个节点、104条连线，五分支，findings为空；只是格式/基线通过。
  三份原件及registry的前后SHA完全相同（值见上节），未写manifest或provider。
- 公开输出保存到test `Scholar Workflow 实验/论文包检查-0.35.0/自动检查.md/.json`；
  本轮成果说明提供实际正文、Canvas、报告与阅读说明四条原生链接，均解析到存在文件。
  首次打开索引尚未更新，重新核对后CLI成功选中正确文件；逻辑Canvas view也可加载并fit viewport。
- **GUI未通过**：截图仍显示旧0.34页面。cua确认Mac锁屏，不能把activeFile/旧截图当新窗口效果。
  两张本轮错误截图已从test明确路径移除；未删用户文件。Codex打开两份报告返回queued，
  不冒称已显示。正文和报告实际文件可直接访问；解锁后人工评鉴，不重跑自动/整库测试。

本版skill能力是现存包只读检查，不是新增科学分析、正式登记或新图。人类可读输出遵守
obsidian-markdown；Obsidian CLI只做原生打开/链接解析，未读取外部秘密配置或改app设置。

## 下一实质缺口（不重复本轮检查）

v5普通canonical commit已支持，但首次Source/Field/provider enrollment还只接旧平铺搬迁模型。
现有候选已经foldered，不能为复用旧流程拆散再迁回。应先确定独立、完整审议的首次登记入口，
保留原CAS/journal/recovery；不能裸调FieldService.confirm绕过旧分析审议，也不能伪造provider。
选test子目录Source时，旧resolve_obsidian_vault_id仅匹配整个已打开Vault根，仍须正确区分
Source注册根与阅读器Vault身份；不得改权限或拿父Vault身份冒充子目录已登记。
以上是后续明确缺口，本轮未实现、未调用真实联合事务。G17继续未完成。
