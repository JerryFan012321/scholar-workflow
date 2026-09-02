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

- **查台账 / 用前先查** —— 直接问"查找服务器""有哪些 key",或问某台已登记主机的 CUDA/代理
  详情,它读台账回答你;纯只读——记录文件还不存在时它会说台账未初始化,不会自作主张去铺骨架。
  当任务涉及*你自己*已登记的主机或 key(登录、上传到你的服务器、需要你已登记凭据的 API 调用),
  它会先读台账、复用匹配的 host/key,而不是直接问你。
  上传到 Zotero / 托管服务、调用公开无鉴权 API、或枚举由其他系统暴露的清单(云账号、K8s 集群)不触发它——即便该账号或集群属于用户本人。

插件不存任何私有数据 —— 唯一输入是目录地址。模板进 git,真实记录 gitignore 留本地。
新增服务器走"先征询再记录"。幂等:`env-init` 绝不覆盖已存在文件。

完整流程与约束见 [SKILL.md](./SKILL.md)。
