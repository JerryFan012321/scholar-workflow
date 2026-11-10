# 后台独立与普通URL修正

日期2026-11-10，候选0.52.1，分支codex/hotfix-recommendation-local-access。
原CLI与detached HTTP本来不依赖页面，缺口是各新窗口没有Bearer，导致普通URL不能读取内容。
本批只补同源POST/api/session握手、普通open输出和后台Skill契约，不自建管家执行器。
精确Host/Origin、非简单自定义header、JSON空体、拒绝跨站fetch及CORS；API继续Bearer/Origin/CAS。
凭据仅页面内存；静态HTML/health/URL不含凭据；旧fragment兼容后清除。

输入：合成HTTP/Node、两个producer同一候选、管家context、独立test profile。
检查：新窗口无既存凭据仍加载；两个独立客户端；缺Origin/header、错Host/Origin、跨站/preflight拒绝；
无HTTP/浏览器时提交与管家读写、同一对象合并；open输出普通URL；旧鉴权/CAS/审阅/入库回归。
383项通过，15.55秒；Ruff、JS语法、diff与skill-creator校验通过。前轮16项mock未识别sessionPOST、
随后2项测试注入锚点变化失败，均修正测试夹具后通过；保留XML，未用真实业务替代测试。

安装后只在既有test对象打开两个无tokenURL，读同一4候选与设置入口；不点击真实Zotero写入。
个人13条已有内容不修改；发布/安装身份与窗口结果后续追加。端口动态，status返回当前地址；
127.0.0.1仅本机，不开放局域网。管家调度仍需外部harness，不由保存context推导在运行。


## 实际安装与窗口回执

源码28451c81deca1468c83934a96587740980e1c0b7，runtime01f2858098629266b801d14bdb719642aee1b4f1。
hotfix/release已正常推送，main未合并；pipx固定runtime SHA、Codex/Claude marketplace正常更新，
关键Skill/reference/代码匹配。个人50240/test50247，build5ff474aec0ab8c76，均来自安装包Python。
两个独立标签页直接进入test普通URL（无fragment/query/预先凭据），均显示原4候选；日常普通URL
显示原13条，CLI逐条对照内容/审阅/决定/revision/推荐/热度不变。无真实数据写入。
截图local-access-window.png与local-access-installed.json位于同一test对象_work；旧失败XML保留。
这证明本机浏览器实例行为，不代表所有第三方WebView或远程设备都做过实机验证。
未创建/启动实际管家调度；外部agent按运行契约接入，不把保存上下文当作其存活证明。
