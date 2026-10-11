# Prepared Canvas node Markdown

These exact Markdown fragments are input data, not expected output layout. They contain only synthetic fixture claims.

## literature.json

### literature-alpha

````markdown
[[领域库结构验收/长文检索/resources/papers/alpha/Paper|样本甲 · 2001 ↗]]

定义从长文查找证据段落的任务，保留原文位置。

没有真实实验数字。

[[领域库结构验收/长文检索/fixture#^alpha-task|来源片段]] · [[领域库结构验收/长文检索/resources/papers/alpha/阅读记录|说明]]
````

### literature-beta

````markdown
[[领域库结构验收/长文检索/resources/papers/beta/Paper|样本乙 · 2002 ↗]]

把检索分成快速召回和详细核对。

第一阶段漏掉的证据不能凭空恢复。

[[领域库结构验收/长文检索/fixture#^beta-method|来源片段]] · [[领域库结构验收/长文检索/resources/papers/beta/阅读记录|说明]]
````

### literature-gamma

````markdown
[[领域库结构验收/长文检索/resources/papers/gamma/Paper|样本丙 · 2003 ↗]]

并行关键词与语义检索，再合并去重。

这是替代路线，不表示直接继承样本乙。

[[领域库结构验收/长文检索/fixture#^gamma-method|来源片段]] · [[领域库结构验收/长文检索/resources/papers/gamma/阅读记录|说明]]
````

### literature-epsilon

````markdown
[[领域库结构验收/长文检索/resources/papers/epsilon/Paper|样本戊 · 2005 ↗]]

只有模块改进的资料记录；具体做法未知。

这里是展示分组，不表示直接继承样本丙。

[[领域库结构验收/长文检索/fixture#^epsilon-record|来源片段]] · [[领域库结构验收/长文检索/resources/papers/epsilon/阅读记录|说明]]
````

## technical.json

### technical-root

````markdown
# 长文检索
## 技术路线树

按解决办法找资料。

5 篇虚构论文；只验收结构，不作科学结论。

[[领域库结构验收/长文检索/01-论文列表|论文列表]]
````

### route-two-stage

````markdown
## 按段定位和核对

先找到相关段落，并保留原文位置；两阶段方法再检查候选是否支持问题。

[[领域库结构验收/长文检索/fixture#^beta-method|来源片段]]
````

### technical-alpha

````markdown
## [[领域库结构验收/长文检索/resources/papers/alpha/Paper|样本甲]]

定义从长文查找证据段落的任务，保留原文位置。

资料状态：已有完整合成片段；非真实全文。

[[领域库结构验收/长文检索/resources/papers/alpha/阅读记录|阅读记录]] · [[领域库结构验收/长文检索/fixture#^alpha-task|来源片段]]
````

### technical-beta

````markdown
## [[领域库结构验收/长文检索/resources/papers/beta/Paper|样本乙]]

快速召回候选，再核对是否支持问题；不能恢复召回阶段漏掉的证据。

资料状态：已有完整合成片段；非真实全文。

[[领域库结构验收/长文检索/resources/papers/beta/阅读记录|阅读记录]] · [[领域库结构验收/长文检索/fixture#^beta-method|来源片段]]
````

### route-parallel

````markdown
## 并行检索后合并

关键词与语义检索并行执行，再合并去重。

[[领域库结构验收/长文检索/fixture#^gamma-method|来源片段]]
````

### technical-gamma

````markdown
## [[领域库结构验收/长文检索/resources/papers/gamma/Paper|样本丙]]

并行关键词和语义检索，再用统一段落身份合并去重。

资料状态：已有完整合成片段；非真实全文。

[[领域库结构验收/长文检索/resources/papers/gamma/阅读记录|阅读记录]] · [[领域库结构验收/长文检索/fixture#^gamma-method|来源片段]]
````

### route-filter

````markdown
## 筛选候选段落

模块位置已知；只有摘要或资料记录，细节未提供。

[[领域库结构验收/长文检索/fixture#^delta-unknown|缺失内容]]
````

### technical-delta

````markdown
## [[领域库结构验收/长文检索/resources/papers/delta/Paper|样本丁]]

摘要只说明增加可学习段落筛选模块，方法与实验未知。

资料状态：仅合成摘要；无 PDF。

[[领域库结构验收/长文检索/resources/papers/delta/阅读记录|阅读记录]] · [[领域库结构验收/长文检索/fixture#^delta-abstract|来源片段]]
````

### technical-epsilon

````markdown
## [[领域库结构验收/长文检索/resources/papers/epsilon/Paper|样本戊]]

只有模块改进的资料记录，缺少原文，具体做法和效果未知。

资料状态：内容覆盖未知；原文与 PDF 缺失。

[[领域库结构验收/长文检索/resources/papers/epsilon/阅读记录|阅读记录]] · [[领域库结构验收/长文检索/fixture#^epsilon-record|来源片段]]
````

## challenge.json

### challenge-root

````markdown
# 长文检索
## 挑战洞见树

从问题找到解决思路和对应资料。

5 篇虚构论文；同篇可以出现在多个问题下，但仍只拥有一个论文包。

[[领域库结构验收/长文检索/01-论文列表|论文列表]]
````

### problem-location

````markdown
## 问题 · 怎样找到回答所需的证据

相关词相似不等于段落真正支持问题；还需保留可回看的原文位置。

[[领域库结构验收/长文检索/fixture#^alpha-task|任务片段]]
````

### solution-location

````markdown
## 解决思路

保留段落位置；扩展检索来源，或在召回后核对支持关系。

需要什么：稳定的段落身份和候选记录。

还要注意：这些虚构片段没有提供实测比较。
````

### challenge-location-alpha

````markdown
## [[领域库结构验收/长文检索/resources/papers/alpha/Paper|样本甲]]

定义从长文查找证据段落的任务，保留原文位置。

资料状态：已有完整合成片段；非真实全文。

[[领域库结构验收/长文检索/resources/papers/alpha/阅读记录|阅读记录]] · [[领域库结构验收/长文检索/fixture#^alpha-task|来源片段]]
````

### challenge-location-beta

````markdown
## [[领域库结构验收/长文检索/resources/papers/beta/Paper|样本乙]]

快速召回候选，再核对是否支持问题；不能恢复召回阶段漏掉的证据。

资料状态：已有完整合成片段；非真实全文。

[[领域库结构验收/长文检索/resources/papers/beta/阅读记录|阅读记录]] · [[领域库结构验收/长文检索/fixture#^beta-method|来源片段]]
````

### challenge-location-gamma

````markdown
## [[领域库结构验收/长文检索/resources/papers/gamma/Paper|样本丙]]

并行关键词和语义检索，再用统一段落身份合并去重。

资料状态：已有完整合成片段；非真实全文。

[[领域库结构验收/长文检索/resources/papers/gamma/阅读记录|阅读记录]] · [[领域库结构验收/长文检索/fixture#^gamma-method|来源片段]]
````

### problem-overload

````markdown
## 问题 · 候选太多怎样处理

详细核对所有段落会增加工作量；筛选也可能漏掉需要的证据。

[[领域库结构验收/长文检索/fixture#^beta-boundary|资料边界]]
````

### solution-overload

````markdown
## 解决思路

先缩小候选，再详细核对；筛选模块可以放在核对之前。

需要什么：可追踪的候选记录。

还要注意：样本丁仅有摘要，样本戊方法未知，不能补写速度或准确率收益。
````

### challenge-overload-beta

````markdown
## [[领域库结构验收/长文检索/resources/papers/beta/Paper|样本乙]]

快速召回候选，再核对是否支持问题；不能恢复召回阶段漏掉的证据。

资料状态：已有完整合成片段；非真实全文。

[[领域库结构验收/长文检索/resources/papers/beta/阅读记录|阅读记录]] · [[领域库结构验收/长文检索/fixture#^beta-method|来源片段]]
````

### challenge-overload-delta

````markdown
## [[领域库结构验收/长文检索/resources/papers/delta/Paper|样本丁]]

摘要只说明增加可学习段落筛选模块，方法与实验未知。

资料状态：仅合成摘要；无 PDF。

[[领域库结构验收/长文检索/resources/papers/delta/阅读记录|阅读记录]] · [[领域库结构验收/长文检索/fixture#^delta-abstract|来源片段]]
````

### challenge-overload-epsilon

````markdown
## [[领域库结构验收/长文检索/resources/papers/epsilon/Paper|样本戊]]

只有模块改进的资料记录，缺少原文，具体做法和效果未知。

资料状态：内容覆盖未知；原文与 PDF 缺失。

[[领域库结构验收/长文检索/resources/papers/epsilon/阅读记录|阅读记录]] · [[领域库结构验收/长文检索/fixture#^epsilon-record|来源片段]]
````
