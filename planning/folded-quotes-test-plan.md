# 正文摘录折叠：独立开发测试计划

日期：2026-10-08；hotfix：codex/hotfix-canvas-images-release。当前正式安装0.41.7，
新增量尚未部署。只改渲染和末端格式，不改变阅读/推理顺序、科学内容、外部权限或Canvas。

## 输入与独立预期

使用已有合成论文IR4/IR5和analysis-quote-emphasis/SOURCE.md三个完整合成句子；
独立手写EXPECTED.md在analysis-folded-quotes fixture内。不是从产品输出反推预期。
作者陈述和推断均覆盖，中文/英文、claim/point、PDF/已注册Markdown、多个source span。
采用显式profile.markdown_folded_quotes=true；只有已开启markdown_quotes的v4/v5可使用。
旧输入省略或false保持既有字节/序列化。新参数不改原quote或quote_emphasis。

## 步骤与通过标准

1. 实现前跑手写预期正例，旧接口应拒绝新参数（RED）。
2. 模型/schema拒绝错误类型、未开启摘录及legacy框架；合法输入可往返。
3. 正文全部已提供摘录均使用`> [!quote]-`，默认折叠；每块题注和同一来源链接保持，
   展开后完整原句及精确粗体不变。论点旁原文入口及claim/point锚点仍位于折叠块外。
4. v4子项下callout缩进保留；v5独立子槽位保持。多段摘录独立折叠，不合并来源。
   原文含类似callout、Markdown/HTML语法及多行时仍字面展示，不注入新块。
5. 将折叠符号改为展开/删除、改来源或将块挪到别的论点，conformance必须拒绝。
6. 全文显式采用可生成保留完整Canvas的成对提案；局部不能更改格式，采用后局部更新
   保留格式，不能静默关闭。人类正文冲突仍停止，原件保持。
7. 新测试+既有摘录/强调/图片/成对更新回归；完成后一次完整unit/contract（不重做业务）。

影响：仓库合成fixture和pytest临时目录；无真实Vault/Zotero/项目写入、无PDF下载、
无服务/worker/安装/发布变动。结果单独记folded-quotes-test-results.md，不把合成通过
当成Obsidian实际折叠体验通过。以后须正常hotfix安装，只用V-JEPA2一个样本评鉴：
标题与来源可见、能展开/收起、完整上下文/粗体清楚、Canvas不变；用户明确确认前pending。

## 0.41.8本地包准备

功能实现和2035完整回归不变，只更新package/module、两host manifest和本包lock版本。
补跑版本/manifest、49折叠及eval结构回归，预期64项通过；lock检查、diff及Ruff通过。
提交后只在独立干净clone中运行既有release脚本，构建runtime tar、wheel和sdist。
逐项比较发布manifest与源码Git字节，检查wheel/sdist版本和CLI入口/Python源码，拒绝
开发目录、个人绝对路径、真实token等泄漏。发布脚本及依赖pin不变。
输出留在忽略的dist本地构建目录；不推送、安装缓存、切换服务、合并main或写真实Vault。
显式pipx入口核验当前实际版本，不能让uv的开发PATH冒充已安装0.41.8。
