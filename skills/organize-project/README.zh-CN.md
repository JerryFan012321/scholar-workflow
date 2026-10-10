# organize-project

从明确选定的项目资料编写或更新内部 PROJECT.md；对外展示仍使用 README.md。
不需要 Hub，也不另建资料账本。

## 使用

可以说：“根据这些代码模块、论文单元和实验档案，给这个项目整理一份内部
PROJECT.md 预览，详细计划继续放在 SCHEDULE.md。”

提供项目目录和选定资料，或已有 project-context 清单。同一 Run 有多个结果时，
明确选哪个 Attempt；没有外置计划时，详细计划只维护在 PROJECT 中。

文档按最新情况、唯一计划、实验结果与历史、代码关系、论文资料、归属与待决问题排列。
正文突出文件用途，完整核验记录放在附录，所选资料不丢失。
缺失证据、未验证的阅读器入口不会隐藏；模块图不把静态调用
冒充运行成功，重试不算独立实验。

PROJECT、计划和项目报告以 VS Code 为主要阅读环境，优先使用已有的内置
Markdown/Mermaid 预览。可选扩展及实际验收见[阅读器契约](../../references/vscode-project-docs.md)；
不能用 Obsidian 中显示良好代替 VS Code 验收。

默认只在会话给出预览。需要保存候选时明确目标位置，需要修改已有文档时明确范围；
保留人写正文和未解决的计划冲突。不运行代码、不初始化项目、不复制论文分析、
不改原始实验档案、不发布文件。

只比较实验使用 review-experiments；创建骨架使用 init-project。现有
project overview CLI 仍是清单视图，不是丰富 PROJECT 的渲染器。

详见[内部项目文档契约](../../references/project-entry.md)。本功能自0.43.0提供；
VS Code 原生阅读、导航评鉴与安装及契约检查分开。
