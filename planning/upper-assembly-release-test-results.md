# 0.43.0 hotfix发布与安装结果

2026-10-10，用户明确批准；先行计划为upper-assembly-release-test-plan.md。

## 发布前实际检查

| 检查 | 实际结果 |
| --- | --- |
| 完整unit/contract合成回归 | 2486 passed，107.38秒，11条既有SWIG/fork弃用警告；无失败或跳过 |
| 改动Python Ruff | 全通过；不扩大修复历史lint债 |
| 16个runtime skill基础校验 | 全通过；不冒称实际宿主路由/人工评鉴 |
| 四版本与lock本包 | 全为0.43.0；uv.lock仅本包版本一行变化，24依赖离线检查通过 |
| 开发公开CLI | --version为0.43.0，knowledge list帮助含新选项 |
| runtime边界独立检查 | 262文件；无开发层、symlink/缓存/.review或高置信度私人路径/密钥 |
| 原论文呈现契约 | 原模板、analysis SKILL及renderer无diff；新外框候选不进runtime |
| diff | 通过 |

只用了开发合成fixture和临时目录，没有Vault/Zotero/业务实验或服务写入。
README六处临时尾注随后统一为0.43.0说明，不改功能代码或先行预期。

## 发行与安装

| 对象 | 实际身份与结果 |
| --- | --- |
| 已提交source | 6dfb9d4eb8335084ca0d04984e79204a85c683fb；201个明确审查文件，干净hotfix |
| 已发布runtime | 3275a80a50dcb031c1bf0a3d785a28df3069f1fc；既有make-release.sh在独立dist clone生成 |
| 推送 | hotfix及release正常fast-forward成功，无force/main合并/PR |
| 远程main | 保持ccb60b793d9fd5db6032499bf2ca2c8dda3f1183 |
| runtime archive | 262文件，与固定source runtime文件集合及每文件字节一致 |
| wheel/sdist | 108个Python模块及3个静态文件与runtime全字节相等，无遗漏/意外文件 |
| 正常pipx | 固定runtime SHA安装成功，Python3.14.5，实际包/公开CLI均0.43.0 |
| pipx direct_url | commit_id和requested_revision均为上述固定runtime SHA |
| 正常Codex插件 | marketplace upgrade及plugin add成功，实际0.43.0缓存中16skill齐全 |
| 安装字节核对 | cache262文件与runtime全等；pipx111个包文件全等，无遗漏/额外包文件 |
| 双manifest | 实际安装缓存两份均0.43.0；不手改缓存 |

构建目录为忽略的dist/0.43.0-release.gtSBNw；生成release未切换用户工作区分支。
两份tar整体hash因各提交PAX comment/mtime不同而不同，已独立核对全部实际文件字节相等。
发行包无planning/dev-guide/tests/evals/AGENT/CLAUDE、symlink或有限扫描中的私人根/常见密钥。
没有切换或声称更新运行中的Hub/worker，也没有真实Vault迁移、Zotero写入或实验运行。

| 本地产物 | SHA-256 |
| --- | --- |
| runtime.tar | 924e64ea3774cc5b7a7ed42b62effb32597ae10802bd9218dd286f9d526945fe |
| wheel | 1dfa7556d1c3e04ef4052f8baddae418456043f9fbd5da6cae5f3a22b6616b48 |
| sdist | d6ce1b71142a573069acd78d1768e54f9623df7848d5cbb875714ab3863f2a43 |

正常安装命令：

```text
rtk proxy pipx install --force git+https://github.com/JerryFan012321/scholar-workflow.git@3275a80a50dcb031c1bf0a3d785a28df3069f1fc
rtk proxy codex plugin marketplace upgrade jerry-plugins --json
rtk proxy codex plugin add scholar-workflow@jerry-plugins --json
```

0.42.0回退runtime为67a221680b92822558502f36924b2e862f1ae8d5，pipx可用同一正常VCS
安装命令替换SHA重装；旧Codex0.42缓存保留，但不声称直接改目录即可切换活动插件，
其回退须经正常版本固定入口，不能用仍指向最新release的add命令假装已回退。
安装不使本会话旧skill目录快照自动变化；本轮明确读取0.43安装文件执行，不声称自动路由已验证。
原生/人工评鉴、默认解析树采用、main合并、正式迁移与完整G17仍分别未完成。

## 安装后的最小单对象检查

实际读取0.43.0安装包两新skill及必读refs，隔离执行者与独立评审预期。只从test既有模范
项目33冻结文件（原30+3历史Target）生成PROJECT、实验复核和一SVG；未执行脚本/实验。
独立检查六/五节、8项资料/4外部URI、90链接/36不同本地目标及33输入可发现，事实和
图表零基线/分面尺度正确。133保护文件逐字节保持，原论文65文件集合不变，真实项目
PROJECT/SCHEDULE仍不存在。正常安装CLI validate-context确认8项声明有效。
唯一实际产物与结果留test上层组合审阅目录；业务文档不复制进开发Git。
原生/人工仍待确认，Codex面板打开请求只返回queued，不能记为显示或编辑成功。
收尾只提交开发回执，不重新构建runtime，固定已发布source/runtime身份保持。
