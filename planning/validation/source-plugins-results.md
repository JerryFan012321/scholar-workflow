# 推荐源插件：开发验证结果

2026-11-10，codex/hotfix-source-plugins，0.54.0开发候选，基于已安装0.53.0。

## 已实现

声明式来源包持有版本、非秘密接口、宿主连接提示、操作输入输出与读写性质；
统一import/export/enable/disable/guide支持自定义源，builtin以当前pool的override启停。
已有source_id、要求、context和历史继续同源管理；停用不删除旧推荐。
通用设置支持添加/JSON导入预览/编辑/取消/启停/导出，以及agent说明的复制下载；
不为新平台增加专属页面或核心枚举。旧legacy aggregator保留兼容，不是插件执行器。

Skill→来源目录→来源插件规范逐层引用；使用所选源先读guide，实际MCP工具和schema由宿主发现，
tool_name仅提示。guide含明确profile及对应schema/submit命令，不能把test投向personal。
定义完整、enabled、已授权、连接成功分别表达。当前没有新增工具执行器、账号代理或调度器。

## 结果与范围

独立contract输入先准备：原test对象_work/source-plugins/INPUT.json及EXPECTED.md；
虚构example.org来源，read/write仅描述，不访问网站或账号，不调用其工具。
首轮93通过。整合495检查中493通过，两个旧断言分别需匹配新标签及显式profile命令；
更新后2项复验通过，另补9个凭据/操作说明安全用例。
最终504项定向检查全部通过，20.69秒；Ruff F/E9/I、JS语法、Skill校验和35个本地文档目标通过。
原始focused/regression/recheck/final XML保留在原test对象，没有抹掉中间失败记录。

测试覆盖导入导出往返、第二pool复用、CAS、启停/历史守恒、完整说明与停用分离、
HTTP认证/同源、typed字段和敏感值拒绝、通用UI离线事件旅程。禁止外网和进程创建的合成stub通过。
JSON对象形式的操作说明仍服从既有严格非秘密字段限制；实际MCP schema继续归宿主。
不重复整库业务，不改日常推荐、Zotero、论文包或Canvas。

## 尚未完成

本轮未发布安装或切换服务。当前日常/test页面仍是0.53.0，不能据源码检查称新版界面已交付。
需要下一步正常安装0.54.0，在同一个test对象导入INPUT.json，检查设置里添加、取消、启停、
导出和agent使用说明的易用性；这些外观/使用效果待人工评鉴。
原生MCP账号接入与实际来源调用是独立事实，本轮无此证明；不把声明完整写成已连接。
main未合并，真实推荐和既有个人偏好未迁移。
