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
