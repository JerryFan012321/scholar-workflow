# 0.32.0 hotfix 发布与安装结果

2026-10-04。用户已明确批准提交、发布和正常安装。不合并main，不操作Vault或现存服务。

| 项目 | 实际证据 | 状态 |
|---|---|---|
| 完整发布前回归 | 1408 passed、11 warnings、72.97秒，退出0 | 通过 |
| 定向/静态 | v5 53通过；指定五文件Ruff、skill frontmatter及diff空白通过 | 通过 |
| 版本 | 两个plugin manifest、pyproject、包__version__、uv.lock为0.32.0 | 通过 |
| source | `425a8c7`，hotfix分支已推送 | 完成 |
| runtime release | `be0085be05ba5e16bf19ac3cf8ea1b1992aa67d4`，独立clone运行make-release.sh后正常推送 | 完成 |
| runtime边界 | 根目录仅runtime白名单，不包含planning/tests/AGENT；私人路径和明显密钥模式扫描无匹配 | 通过（所列模式范围，非穷尽秘密检测） |
| Codex | marketplace upgrade无错误；plugin add返回0.32.0及正常缓存路径；生成器和模板hash与source相同 | 安装完成 |
| pipx CLI | 固定新runtime SHA正常force安装成功；--version为0.32.0；direct_url确认同一commit | 安装完成 |
| Python加载 | 仓库外pipx Python -I加载0.32.0的实际site-packages | 身份核对通过 |
| main/真实资料 | 未合并main，未修改Vault、PDF、批注或外部应用配置 | 保持原样 |
| 新v5单对象产物及人工评鉴 | 尚未执行；不得用本表安装成功替代科学来源或Canvas评鉴 | 待执行 |

实际安装命令：`codex plugin marketplace upgrade jerry-plugins --json`、`codex plugin add scholar-workflow@jerry-plugins --json`、`pipx install --force git+ssh://git@github.com/JerryFan012321/scholar-workflow.git@be0085be05ba5e16bf19ac3cf8ea1b1992aa67d4`（执行时均经rtk）。未手改缓存，未安装开发目录或临时venv。

CLI回退基线：0.31.1 runtime `adfb0f273437a20714b740c56a4ba5d18540fda9`，安装前direct_url确认。需要回退时可正常安装该固定提交；未执行回退。Codex旧版缓存的存在不等于已切回旧版，须用正常渠道并核对实际版本。

当前聊天可能仍持有启动时的旧skill目录；新会话加载0.32.0后再执行人工评审，不能从安装成功推断已运行新skill。下一步按 `analysis-v5-human-review-plan.md` 冻结V-JEPA 2真实输入，批准新目录及单对象展示后执行，不重复整库操作。公共提交链与科学来源尚未验收。
