# 0.37.0 Source 与原生阅读器分离

## 变更范围

子目录 Source 仍负责文件范围，包含它的唯一 Obsidian Vault 只负责阅读器打开位置。
旧精确 Vault resolver 保持兼容；新 reader resolver 拒绝缺失/重复/嵌套映射，bounded/no-follow/
nonblocking 读取 host registry，不读 ZotFlow 秘密配置。analysis commit 从 adapters 取得
身份，不再反向依赖 Hub 的 reader resolver；历史 ZotFlow Source 入口识别包含它的 Vault，
仍执行已审计插件、本机 storage 和 Local API 附件门禁。

新增公开 `knowledge reader/open`，原生打开已登记目录内 Markdown/Canvas。仅需 read 能力，
拒绝越界、隐藏目录、symlink、缺失和其他类型；无 shell、Hub、workspace 或写入。
OS 接受请求与真实界面/人工认可分开记录，不冒充论文正式 provider 归档。

## 独立验证

输入与预期见 `source-reader-test-plan.md`。首次命令引用了不存在的 contract 文件，0项执行；
纠正为真实 `test_analysis_cli.py`，不是忽略失败。首轮88通过，新增子目录ZotFlow原生路由
与read权限负例后98通过；另增一次真实 resolver 的合成 paired commit 跨根验证。
新增/变动模块及tests Ruff、skill frontmatter和diff检查通过。
完整 unit/contract 1535 passed、11既有警告，78.37秒；其后新eval schema再次10通过。
三个eval按真实权限/末端结果审阅，trigger不变，新原生打开outcome保持pending。
没有重新分析论文或重复真实库/实验业务测试。安装态结果待补。

## 安装态边界

正常发布安装确定 SHA 的0.37.0 hotfix，不合并main，不切换任何服务。
回退0.36.0 runtime e73bf2618b7f94673c84eb92f810cad56ed48764。
只在已登记test样例执行reader/native open；原V-JEPA2三文件、registry和manifest保持原字节。
可见使用说明放test，而非tmp。完整论文归属、科学支持与实际GUI/人工评鉴未完成，G17继续。
