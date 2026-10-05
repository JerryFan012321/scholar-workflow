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

明确需要便携的项目/实验样例时，在已安装 skill 目录运行
`scripts/example_project.py plan /chosen/new-project` 和 `apply /chosen/new-project`。
它创建一个全新独立的四数计算示例，包含冻结输入、独立预期、可读说明和公开 CLI 重放入口，
不提交、不执行。已有目录、符号链接或祖先 Git 树会拒绝；按生成的 README 分开进行本地提交和
执行，再从相同源码新克隆重建。详见[复现契约](references/reproducibility.md)。不需要 Hub，
不打包个人路径或外部论文；自动校验不代替人类可读性评鉴。

已初始化的项目可另有 `project-context.json`，明确关联代码、论文、笔记、实验报告和成果。
`scholar-workflow project context-template --project-root /path/to/project --language zh`
只输出空模板，`project overview` 输出可读总览；两者不写文件、不要求 Hub。
初始化本身不会猜测资料或复制外部知识，详见[项目资料契约](../../references/project-context.md)。

明确需要更新资料清单时，先另存项目根的候选，例如 `project-context-candidate.json`，保留已有文件。
运行 `scholar-workflow project overview --project-root /path/to/project --context-file project-context-candidate.json`
可零写入预览；`validate-context` 支持相同选项。候选须匹配当前项目身份，输出明确标为未应用，
不会替换生效清单或核实外部来源；文件名与安全边界见上述共享契约。覆盖批准是另一个步骤。

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
