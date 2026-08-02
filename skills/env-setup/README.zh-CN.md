# env-setup

搭建并维护一个个人 **env-records** 目录,记录 API key 与 SSH 服务器,内容完全留在
插件仓库之外。

- **初始化** —— `scholar-workflow env-init` 在 `env_records_root`(取自配置)下铺出
  统一骨架:进 git 的模板(`*.example.yaml`)、被 gitignore 挡住的真实记录
  (`servers.yaml` / `apis.yaml`)、`setup/` 脚本目录、README 与 `.gitignore`,再做一次
  本地 `git init`(绝不 push)。
- **服务器** —— 每台三块:连接(host/user/port/key/jump/password)、环境台账(conda
  环境列表 + python/cuda/关键包/兼容性,宿主机 cuda_driver,代理)、元信息。大块重建
  配方放外置脚本 `setup/<别名>/<环境>.sh`。
- **API** —— 每个 key 一条:name / env_var / value / owner / scope。

插件不存任何私有数据 —— 唯一输入是目录地址。模板进 git,真实记录 gitignore 留本地。
新增服务器走"先征询再记录"。幂等:`env-init` 绝不覆盖已存在文件。

完整流程与约束见 [SKILL.md](./SKILL.md)。
