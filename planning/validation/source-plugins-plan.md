# 推荐源插件定向验证

输入先准备为不联网的Synthetic Lab来源包：公共example.org接口、稳定source_id、版本、宿主提示、
只读与写入操作描述；无真实账号或密钥。同一隔离pool保留原requirements/context/history。

验证步骤：导入→列出/导出→另一个pool导入→guide→编辑→启停→旧revision冲突。
验证通用UI的源码交互与HTTP接口；确认任意新source不需修改核心路由/枚举/Skill。
负例：未知字段、秘密/私有路径、builtin覆盖、planned启用、非法操作/版本、CAS冲突。
HTTP继续要求已认证同源请求，不执行描述中的URL/文本；stub禁止外网与进程创建。
通过标准：声明字节/语义可往返，身份和关联不变，导入不执行；guide包含源要求、上下文与原生工具发现说明，
停用不丢失旧推荐或历史，builtin包定义不能被局部编辑覆盖；原推荐回归通过。
输出：定向XML及精简结果置原test对象_work/source-plugins/；开发阶段不作真实宿主已连通或人工外观通过宣称。
实际安装/服务切换留待另一步，当前0.53.0页面不变。
