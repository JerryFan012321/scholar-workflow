# 0.37.0 Source 与原生阅读器分离

## 变更范围

子目录 Source 仍负责文件范围，包含它的唯一 Obsidian Vault 只负责阅读器打开位置。
旧精确 Vault resolver 保持兼容；新 reader resolver 拒绝缺失/重复/嵌套映射，bounded/no-follow/
nonblocking 读取 host registry，不读 ZotFlow 秘密配置。analysis commit 从 adapters 取得
身份，不再反向依赖 Hub 的 reader resolver；历史 ZotFlow Source 入口识别包含它的 Vault，
仍执行已审计插件、本机 storage 和 Local API 附件门禁。

新增公开 `knowledge reader/open`，原生打开已登记目录内 Markdown/Canvas。仅需 read 能力，
拒绝越界、隐藏目录、symlink、缺失和其他类型；无 shell、Hub、workspace 或写入。
OS 接受请求与真实界面/人工认可分开记录，不冒充论文正式 provider 归档。

## 独立验证

输入与预期见 `source-reader-test-plan.md`。首次命令引用了不存在的 contract 文件，0项执行；
纠正为真实 `test_analysis_cli.py`，不是忽略失败。首轮88通过，新增子目录ZotFlow原生路由
与read权限负例后98通过；另增一次真实 resolver 的合成 paired commit 跨根验证。
新增/变动模块及tests Ruff、skill frontmatter和diff检查通过。
完整 unit/contract 1535 passed、11既有警告，78.37秒；其后新eval schema再次10通过。
三个eval按真实权限/末端结果审阅，trigger不变，新原生打开outcome保持pending。
没有重新分析论文或重复真实库/实验业务测试。安装态结果待补。

## 安装态边界

正常发布安装确定 SHA 的0.37.0 hotfix，不合并main，不切换任何服务。
回退0.36.0 runtime e73bf2618b7f94673c84eb92f810cad56ed48764。
只在已登记test样例执行reader/native open；原V-JEPA2三文件、registry和manifest保持原字节。
可见使用说明放test，而非tmp。完整论文归属、科学支持与实际GUI/人工评鉴未完成，G17继续。

## 首次正常安装与真实路由发现

source65d58b67、runtime16254cbe已正常发布并安装，CLI/module/dist/Codex cache均0.37.0，
direct_url固定上述runtime SHA。安装版reader正确识别窄Source与父test Vault；registry、manifest
和V-JEPA2三文件hash前后相同。OS-open返回open-requested，但Obsidian frontend仍停在旧文件，
因此不记为真实目标打开通过。原生URI中的空格为form-style `+`；官方Obsidian URI明确要求%20，
补丁改为percent encoding并增加独立含空格输入的断言，准备正常安装0.37.1后复验同一对象。
官方来源：https://help.obsidian.md/Extending+Obsidian/Obsidian+URI 。

test新“原生阅读验收-0.37.0/开始使用.md”是可读使用入口，四条native links已由实际metadataCache
解析为真实完整正文/Canvas和已登记两文档；经Obsidian CLI已打开，但这不替代public open实机验收。
没有改原论文或伪造provider。主分支与服务均不变。

0.37.1补丁定向26通过，完整1535通过/11既有警告/79.06秒；Ruff与diff通过。
首次版本替换误命中同号referencing依赖，uv立即拒绝解析，0项测试；按package name修复lock，
依赖版本不变，后续全部回归成功。不是跳过wheel检查或修改依赖来绕过失败。
