# Knowledge preview 独立测试

对象：新增无 Hub 的只读 CLI，不修改 FieldService 写入流程。输入预期先行固定。

## 合成输入与预期

- 子目录 README + 两篇文档：一个候选 Field，全部导航保留；根目录/正文/registry 无字节或文件增删。
- 空目录：无候选，明确原因；不创建任何状态目录。
- 外部 ZotFlow 来源笔记：独立列出 writer，不混入 Scholar 导航。
- 同路径已注册 Source：复用身份；已有 manifest 未登记时显示仅主机登记候选，不写 manifest。
- 重叠 Source：显示冲突，不冒称可直接登记。
- 坏 manifest、根 symlink、相对根、未知 format/language：明确拒绝或输入错误，无 traceback、无写入。
- Markdown 显示的用户标签转义，不把 HTML 或链接语法变成执行/导航入口。
- 不输出进程内一次性 candidate token；输出是预览，不是确认凭证。新候选身份为临时身份。

## 执行

定向执行 `tests/contract/test_knowledge_preview_cli.py` 和既有 Field registration 契约、版本契约；
必要完整 unit/contract 回归。均使用合成临时目录，无真实业务写入。

安装后使用 0.34.0 的公开 `knowledge preview` 只读检查 test 内既有 V-JEPA2 候选子目录；
只在独立成果目录保存 CLI 输出和中文说明，不能把输出登记为已完成 Source/Field。
对照前后现有论文和主机 registry 校验值。人工评鉴：导航说明是否清楚，文件是否完整可找到。
不重新分析、生成 Canvas、改正式库、操作 Zotero、开启服务或注册 Field。
