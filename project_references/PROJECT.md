# 0.总体参考文档
- ~/documents/3-knowledge base/32-documents/01-工作流技术文档
# 1.总体原则
  该skill插件的对象是论文、技术文档及其相关数据
  该插件是一个claude code插件，但未来会涉及用codex exec等命令进行额外的调用
  每一个论文、书籍和技术文档都只能有一个主存储位置
  这个文件只是一个描述性文件，真正实现功能还要进行更详细的划分以及根据模型能力进行精简
  对于大型文件夹，管理时应当采用一种文档对该部分进行描述和索引，并且层层递进，而且要定期维护这些索引保证能够和该文件夹中的内容对得上。读取时通过索引和描述判断内容，判断是否值得读取后再拉取到临时存储区域读取
  能够同时适配claude code和codex,含有CLAUDE.md和AGENT.md,CLAUDE.md直接链接后者，并且其中的内容除了@RTK.md和@AGENT.md以外，还有一句：所有的修改都弄到AGENT.md中
  notion上只放知识大纲、索引、项目状态、任务清单以及一些简洁且重要的知识，大文件不上传
  项目痕迹管理：对于涉及到的项目，在本地维护一个该agent分发的项目知识表
  该项目要通过git维护版本
  该项目要进行功能评测
  拆分项目功能实现不同的skill,注意如果找到了更好的划分，没有必要按照我划取的边界执行


# 2.第一阶段任务分析
## 功能1:知识管理与分发
- 通过网络搜索、论文列表的给予以及本地查询等方式，AI agent获取论文等东西并根据文件存在情况提醒用户判断是否进行下载。注意：论文下载和传递源头只有arxiv，其他获取方式只能用来获取论文相关信息。
- 在用户的批准后，分别向zotero、notion和对应的3-knowledge base发送它们应该得到的东西
- 对于论文，向zotero的对应分类（你推荐zotero已有的分类，用户决定放置在哪个分类中或放置在新分类中）分发相应的论文，提炼出文件具体地址备用。分类按照文件夹名称确定。后面会指定分类的根目录。论文位置索引传给3-knowledge base中对应位置（你推荐，由用户决定最终选项）一份成表（如知识库中worldmodel文件夹中就应该有个worldmodel相关论文表）
- 对于技术文档、网站快照、draw.io等非论文的技术文件，在3-knowledge base中找到相应的分类进行和上面类似的分发，但不需要本地存储索引。这些索引要能够在获得知识库根目录后，按照相对位置索引出本地的位置，提供给cmux中的notion当作浏览器打开
- notion中的索引问题：首先构造数据库。一类按照分类存储论文元数据，每个粉来，元数据包括时间、会议、名称、mac本地相对链接、对应的网络项目链接、对应的arxiv链接。

# 3.工具问题
- notion MCP以及各式各样类似mcp的工具（如obsidian-local-rest-api）会消耗大量tokens,因此建议用命令行实现功能


# 4.zotero问题
由于当前版本的zotero的localapi无法对zotero执行写操作（但是可以读），我们选择自建 Zotero 本地桥接插件：
Zotero 插件运行在 Zotero 进程内部，可以访问完整的 JavaScript API。插件再利用 Zotero 自带的 HTTP Server 注册一个本地接口：

外部 Agent / Python
        │
        │ POST http://127.0.0.1:23119/agent/register-paper
        ▼
Zotero Bridge 插件
        │
        ├─ 创建论文条目
        ├─ 创建链接附件
        ├─ 加入集合、标签
        ├─ 调用 ZotMoov
        └─ 返回 item key
        ▼
      Zotero

Zotero 官方明确支持插件向内置 Connector HTTP Server 注册新端点，端点可以接收 GET 或 POST 数据。

插件内部则使用 Zotero JavaScript API：

const item = new Zotero.Item("journalArticle");
item.setField("title", data.title);
item.setField("DOI", data.doi);

const parentItemID = await item.saveTx();

const attachment = await Zotero.Attachments.linkFromFile({
    file: data.filePath,
    parentItemID
});

Zotero JavaScript API支持创建条目、修改字段并通过 saveTx() 写入 Zotero 数据层，而不是直接写 SQLite。

外部请求可以设计成：

{
  "title": "2D Gaussian Splatting",
  "doi": "10.xxxx/xxxx",
  "filePath": "D:/Papers/3DGS/2dgs.pdf",
  "collection": "Research/3DGS",
  "tags": ["3DGS", "surface"],
  "attachmentMode": "linked_file"
}

这是唯一能够同时稳定完成以下操作的方案：

立即写本地 Zotero；
链接任意本地 PDF；
调用 ZotMoov；
读取 Zotero 当前状态；
不经过云端；
让 Agent、CLI 或 MCP 驱动。
安全方面必须增加

官方文档指出，本地 HTTP Server 的部分 POST 类型可能被浏览器网页发出，因此不能暴露一个“执行任意 JavaScript”的接口。

至少应设置：

仅监听 127.0.0.1
随机访问令牌
允许访问的文件根目录白名单
固定动作列表
请求大小限制
路径规范化与越权检查
重复请求幂等控制

例如只允许：

register_paper
attach_file
update_metadata
move_attachment
get_item

不要允许：

eval_javascript
execute_sql
execute_shell

同时，重要的是尝试使用已经安装好的zotmoov插件