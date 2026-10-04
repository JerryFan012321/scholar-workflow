# 0.33.0：项目／实验复现能力结果

日期：2026-10-05。独立 hotfix，main 未合并；整阶段未完成。

## 开发验证

- 独立输入与范围：`project-reproducibility-test-plan.md`。
- 首轮定向 34 passed（4.02s），发现系统 Python 缺 pydantic，三个剩余 lint 项未通过。
- 最小修正：通过已安装 CLI console entry 选择产品 Python，只给初始化器用；helper 本身标准库。
  unsupported launcher 在创建目标前拒绝，未自动装依赖。代码计算在 src，tools 只做薄入口。
- 修正后定向 37 passed（4.58s），包括两个 launcher/系统 Python 边界；全量 1441 passed、
  11 个现有依赖/多线程 fork 警告，77.10s。
- 七个 Python 文件 Ruff、init-project skill validator、diff 空白检查通过。
- 触发 description 不改；原 init-project routing 不变。新增 safety 用公开脚本负例守护，
  reproduction outcome 继续 pending，自动 schema 不能冒称人类评鉴通过。
- 新模板未找到个人路径、真实 Zotero library/attachment ID、固定 23128 或密钥字段。

## 交付边界

可移植模板、新脚本、按需 reference 和双语说明已实现。准备不提交/执行；实际 replay 另行进行。
安装、单对象 canary、source/runtime SHA、真实 CLI/cache 身份及人类展示结果随后补充。
回退：0.32.3 / runtime `c0fa2000a7b8d56a841bc753be12d5f3898e7114`。

新版本不重新生成论文分析、迁移正式 Vault、扫描业务项目、改变服务或构建内置 Codex 控制面。
人类便利性、完整模范 Source/Field、论文新候选科学支持与原生工具评鉴仍未全项通过。
