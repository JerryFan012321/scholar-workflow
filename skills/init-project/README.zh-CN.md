# init-project

用标准的研究型目录骨架和宿主中立的项目规则，初始化一个由 Git 管理的项目。

## 会创建什么

- `assets/`、`configs/`、`dataset/`、`dataset_toolkits/`、`docs/`、`env/`、
  `experiments/` 和 `src/` 下的固定项目结构。
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
```

## 结构约定

- 本地标准命名是权威形式：使用 `docs/plan` 和 `docs/report`，不重复创建
  `docs/plans` 或 `docs/reports`。
- `dataset/metadata` 与 `dataset/raw` 分开保存元数据和下载数据。
- 每个 `experiments/<id>/` 自己保存完整复现实验所需的材料；registry 只能作为索引。
- 原始数据和实验输出是否忽略，需要结合具体项目交互确认，不由骨架猜测。

本实现参考本地标准骨架，并对
[sjh-skills/init-project](https://github.com/jiahao-shao1/sjh-skills/tree/main/skills/init-project)
的流程思想进行了独立改写。
