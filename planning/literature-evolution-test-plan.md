# 文献演进上层组合：独立测试计划

## 边界与接口

仅验证零写入预览切片，不改旧 literature-tree schema 或既有论文输出，不登记 Source，
不读真实论文、不调用模型、不写 Vault、不发布或安装。七篇论文均为明确合成对象。
本计划与 `tests/fixtures/literature-evolution/EXPECTED.md` 先于 fixture 和测试代码落盘。

公开接口：

- `knowledge.literature_evolution.validate_evolution(doc) -> dict`：独立输入规范化与语义校验。
- `knowledge.literature_evolution.render_evolution(doc) -> str`：先校验，再按 en/zh 渲染无 H1 正文。
- `literature-preview --input FILE|- --format md|json`：零配置、零写入、零 registry 依赖。
- 独立新契约 `contracts/literature-evolution.schema.json`，整数 `schema_version: 1`；
  不借此修改旧技术树/挑战树的意义或输出载体。

## 输入、步骤与手写预期

1. 用手写七篇合成 fixture 验证四类贡献、同篇多贡献、显式主/支/局部位置及待定论文保留。
2. 分别改变一个字段，检查唯一身份、引用完整性、分类证据、五项技术取舍、parent 无环，
   以及不同 scientific relation 不被当成 parent。comparison/alternative 回向关系合法。
   pending 仅指位置待定，允许保留已知类别和证据，但 parent 必须为空；未分类只能 pending。
   Statement 的 unverified 与输入者明确断言的 not_reported 分开，缺证据不自动等于未报告。
3. 检查每层未知字段、危险路径、非法 ID、严格整数、PDF 身份和来源页号；
   schema 只负责可表达的结构约束，动态引用、按键去重和图语义由公开 validator 核验。
4. en/zh 正文检查完整含义、证据类别、未报告成本、合成/待定/未核验状态和相对资料路径；
   PDF URI 使用物理页 index+1，personal/group 路由正确，不生成 loopback 链接或模糊 wikilink。
5. 用恶意标题检查 Markdown/HTML/Mermaid 输出转义。图预览只画 parent 归属，
   scientific relation 在正文完整保留，不假称最终技术谱系图已经交付。
6. 在 Click 隔离文件系统中分别使用文件与 stdin、md 与 json，禁止配置、登记库、
   外部工具、网络和进程入口；比较前后文件字节与目录，确认无副作用。

所有预期来自独立文档及手写输入；不把新 renderer/validator 的输出当作自己的测试 oracle。
正文标签允许含义一致的同义表达，测试不把设计建议、具体词序或占位图外观定稿。

## 执行与产物

子代理仅准备，不执行；主代理在实现前执行新增测试记录 RED，再实施并做受影响回归。
预期产物包括测试结果和七篇合成对象的 Markdown 预览，明确“开发态/未安装/来源未核验”。
人工评鉴对象仍包括最终载体、紧凑布局、图片密度和真实研究内容；自动测试不能替代。
不新增全局登记库、维护门禁或 Hub，也不因此重跑已有论文分析。
