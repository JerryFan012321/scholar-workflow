# manage-assets

统一查询、登记和复用科研资产。先查本地已有记录，再处理任务，不让你反复提供已登记的
服务器名称、连接信息或知识库路径。

查看：`scholar-workflow assets list --language zh`。

登记自有服务器：把非秘密信息放入 `server.json`，执行
`scholar-workflow assets server register --spec server.json --language zh`。
服务器台账与知识库仍保存在各自原位置，不另建一份资产数据库。密码、token 不进入新增记录；
已有旧凭据不显示、不自动删除或迁移。登记不等于连接、上传或执行远程命令。

知识库先查已登记 Source/Field，必要时再查 Obsidian 已知 Vault；不能把“Obsidian 有这个
Vault”当成“插件已登记”或“论文有正式归属”。新登记仍先显示范围和预览，不静默登记整个 Vault。

本轮接通服务器与知识库；学者关注名单和论文资源来源后续接入，继续使用推荐系统原有配置。
具体命令和边界见[资产管理契约](../../references/asset-management.md)。
