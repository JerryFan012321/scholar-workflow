# VS Code 项目文档与树图连线调研

日期：2026-10-10。范围限项目文档阅读环境和新增连线要求，不安装扩展、改编辑器设置、
执行代码或实验、更新真实项目/论文包、发布安装新版本。现有0.43.1不变。

## 结论

PROJECT、项目计划和实验报告应当在VS Code里完成阅读、图表展示和项目文件导航，
不能因为Obsidian显示正常就说通过。当前不是“装一个Markdown插件”就能解释的问题：
本机已具备主要渲染能力，还需实际核实所用预览器、窗口profile、图的尺寸和表格排版。

推荐最小组合是**内置Markdown预览 + 已有Markdown All in One**。如果要在VS Code中
手工精调项目模块图，再选择Draw.io Integration；不默认添加第二套预览器。

## 本机只读观察

VS Code CLI报告1.140.0、arm64；当前PATH未找到code命令，使用已知应用内CLI查询。
安装包含内置Markdown预览、Mermaid Markdown Features和支持SVG的media-preview。
用户扩展清单有Markdown All in One 3.6.3、Markdown PDF 2.2.0；没有独立Mermaid或
Draw.io扩展。**这些是安装清单，不证明当前窗口启用/激活、实际显示或链接可达。**

只读查看test既有单项目PROJECT和实验复核：它们使用普通Markdown、相对链接与SVG；
没有Obsidian wikilink、callout或块锚点语法。PROJECT有一张LR方向的六节点/五边Mermaid，
源文件导航在图下表格，不依赖图内click；指标核对SVG存在。长中文表格和横向图可能
影响窄窗阅读，这是排版推断，未用GUI验证，不能当作已定位的唯一原因。
四个论文入口使用obsidian协议，是外部阅读器动作，不是在VS Code内嵌显示论文。

## 扩展选择与依据

| 项目 | 建议 | 支持范围与限制 |
|---|---|---|
| VS Code内置Markdown/Mermaid/SVG | 默认主阅读引擎，无需另装 | 官方从1.121起内置Mermaid并支持平移/缩放；本机版本已满足，仍需查实际启用状态 |
| `yzhang.markdown-all-in-one` | 保留已有安装 | 编辑目录、列表、表格的辅助，不是另一套阅读引擎 |
| `hediet.vscode-drawio` | 精确编辑项目模块图时可选 | `.drawio.svg`兼有可编辑图数据和SVG，可直接嵌入Markdown；默认离线，不保证自动无交叉 |
| `bierner.markdown-mermaid` | 当前不新增 | 作者已标deprecated，功能并入内置预览 |
| `shd101wyy.markdown-preview-enhanced` | 本任务不默认新增 | 是独立预览/导出等方案；若以后确有需要再明确选用，不能把两套预览效果混为一谈 |

依据：[VS Code 1.121更新](https://code.visualstudio.com/updates/v1_121)、
[官方Markdown文档](https://code.visualstudio.com/docs/languages/markdown)、
[Markdown All in One作者页](https://marketplace.visualstudio.com/items?itemName=yzhang.markdown-all-in-one)、
[Draw.io作者文档](https://github.com/hediet/vscode-drawio)、
[Draw.io扩展页](https://marketplace.visualstudio.com/items?itemName=hediet.vscode-drawio)、
[旧Mermaid扩展页](https://marketplace.visualstudio.com/items?itemName=bierner.markdown-mermaid)、
[MPE作者页](https://marketplace.visualstudio.com/items?itemName=shd101wyy.markdown-preview-enhanced)。

## 文档本身还需满足什么

- 项目本地内容采用标准Markdown、普通相对链接与图片；标题和图下文件入口可独立使用。
  项目正文、计划、报告不依赖Obsidian才能读。论文单元的原格式/编辑器不因此迁移或复制。
- Markdown文档间跳转优先标题锚点，代码可用已核的行定位。不能把`.md#L44`与代码行
  链接等同；官方处理器支持行片段，但Markdown预览路由已有未关闭问题报告：
  [处理器](https://github.com/microsoft/vscode/blob/main/extensions/markdown-language-features/src/util/openDocumentLink.ts)、
  [问题304481](https://github.com/microsoft/vscode/issues/304481)。本机真实点击仍未验。
- 模块图在实际预览宽度中要能读，不把宽图缩成小字；拆分视图也不能丢边或删掉必要内容。
  原图控制不足时可另选可编辑项目图，不用截图替代论文的JSON Canvas。
- 美观首先通过一致排版、表格宽度、图尺寸和必要的本地CSS解决。官方支持
  `markdown.styles`工作区样式；本轮只记录能力，不新建CSS或改settings。
- 保持预览Strict，不为了图表放开任意脚本、HTTP内容或代码块执行。外部阅读器动作
  明确标为外部，不用一个可点击URI冒充VS Code内嵌功能。

## 树图连线要求

完整内容/层级、可编辑性、证据入口、对齐、无交叉/遮挡、字号及点击留白仍是前置硬约束。
在满足这些要求的布局之间，选择更短的实际折线路径、较少的无意义折返，压缩多余的
父子间隙；格式允许时使用兄弟共享主干。不能用删内容、缩字或长线绕过所有节点来冒充
合格布局，也不宣称证明了数学全局最短。更新时继续保护已认可的安全布局。
要求唯一放在运行期human-presentation；本轮没有修改renderer或生成新的短连线样张。

## 本轮独立检查与后续原生验收

本轮检查输入为受影响运行期文档、两份新增pending outcome和现有schema测试；检查
文档引用存在、输出契约不丢原论文框架/安全边界、双语说明一致、JSON合法及diff无空白
错误。预期只改变规范/调研，不改变代码、现有test样张、安装包或业务记录。检查结果
记在下节，不把静态检查当实际VS Code验收，也不运行完整业务/论文/实验。

下一次原生验收只用test已有model-project-0330的PROJECT、实验复核和指标核对SVG：
在VS Code打开其文件夹，运行“Markdown: Open Preview to the Side”；检查模块图是否
真正渲染、图表字号/表头清楚、正文现状/计划/结果优先，再点代码、指标、报告/日志及
标题导航。仅确认已声明计划状态，不编造计划；四个论文动作单独检查外部工具转交。
用户需确认美观、阅读和点击便利性；未见真实窗口前保持待验。不得重跑实验或重分析。

## 本轮检查结果

- `git diff --check`通过；八个选定运行期/规划引用目标存在。
- 两个相关skill的`quick_validate.py`通过；没有修改description或路由策略。
- `tests/unit/test_evals_schema.py`十项通过（0.02秒）。首次`uv run --no-sync`
  因项目环境缺pytest退出1；改用已有离线缓存的`uv run --offline --with pytest`
  成功，未改lock或产品安装。此测试只证明eval结构，不证明阅读体验或新布局已实现。
- 独立只读复核本轮十三个文件，没有发现职责/格式冲突或虚假的完成声明；两个新增
  outcome继续pending。论文框架、Canvas、图片、正文及test候选均没有改动。

调研和规范修订完成；VS Code原生显示、人工评鉴、短连线实际实现及新版本发布均未完成。
