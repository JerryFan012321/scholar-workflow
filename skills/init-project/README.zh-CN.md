# init-project

用标准的研究型目录骨架和宿主中立的项目规则，初始化一个由 Git 管理的项目。

## 会创建什么

- `assets/`、`configs/`、`env/`、`src/`、`tools/` 和 `tests/` 下的共同源码结构。
- 本地优先的 `dataset/`、`docs/` 和 `experiments/`。
- 含稳定项目 UUID 和版本化 profile 选择的 `project-layout.json`。
- 作为规则真源的 `AGENTS.md`。
- 作为兼容入口的精简 `CLAUDE.md` 与 `AGENT.md`。
- 最小化 `.gitignore`，以及用于保留空目录的 `.gitkeep`。
- 当目标尚未处于 Git 管理下时，初始化 Git 仓库。

它**不会**创建 Claude Code Agent、Codex Agent 或 Hook。

## 使用

对 Claude Code 或 Codex 说：

```text
初始化这个项目
在 ./my-project 创建标准项目骨架
```

Skill 会先运行只读计划。已有文件一律保留；项目规则发生冲突时，先展示具体迁移方案并取得
确认。应用计划只补齐缺失路径，绝不执行 `git add`、`git commit` 或 `git push`。

也可以直接运行确定性脚本：

```bash
python3 skills/init-project/scripts/init_project.py plan /path/to/project
python3 skills/init-project/scripts/init_project.py apply /path/to/project
python3 skills/init-project/scripts/init_project.py profiles
python3 skills/init-project/scripts/init_project.py apply /path/to/project \
  --source-profile multi-stage-3d --package my_project --addon native-kernels
```

## 结构约定

- 本地标准命名是权威形式：使用 `docs/plan` 和 `docs/report`，不重复创建
  `docs/plans` 或 `docs/reports`。
- 数据按 `dataset/<dataset-id>/` 聚合，数据准备源码进入 `src/utils/dataset_toolkit/`。
- 六种显式 source profile 和六种正交 addon 可以扩展共同结构；普通 `apply` 不会改变已有选择。
- 每个 `experiments/<run-id>/` 保存机器无关的 Run recipe；实际重试属于 Attempt，执行位置属于显式 Target。
- `scholar-workflow experiment` 只负责建档、校验、索引和成果晋升；受信备份介质契约落地前，
  不会写入 backup verified，也不启动训练。
- 新项目默认不把数据、文档和实验档案纳入源码 Git；旧项目的 tracked 状态只诊断、不自动改变。

本实现参考本地标准骨架，并对
[sjh-skills/init-project](https://github.com/jiahao-shao1/sjh-skills/tree/main/skills/init-project)
的流程思想进行了独立改写。
