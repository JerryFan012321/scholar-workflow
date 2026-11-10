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
