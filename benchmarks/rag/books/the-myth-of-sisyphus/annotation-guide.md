# 《西西弗斯神话》人工标注指南

## 目标与当前状态

本指南说明如何使用当前已锁定的 EPUB 正文 corpus，把 `questions.v1.yaml` 中的候选题补全为可用于检索评测的 gold benchmark，并映射到现有 `RetrieverAgent.evaluate(test_case)` 输入契约。

当前状态：

- 已锁定版本：加缪著、沈志明译、上海译文出版社、2013.8、ISBN 978-7-5327-6183-8
- 已有本地外部 EPUB，并记录 SHA-256
- 已生成 `corpus.local.jsonl`
- 已完成 20 题首轮核验；部分题为 `verified_v1`，其余题保留未验证并有 `verification_note`
- corpus 不进 Git，只保留抽取脚本、清单与可核验定位信息

## 一、当前语料契约

### 1. 生成方式

在本目录运行：

```bash
python3 extract_epub.py
```

也可以显式指定路径：

```bash
python3 extract_epub.py \
  --epub /Users/ywwl/Downloads/6006-西西弗神话/西西弗神话.epub \
  --output corpus.local.jsonl
```

脚本只使用 Python 标准库，并按 EPUB 的 OPF spine 顺序抽取。

### 2. JSONL 字段

每个正文段落一行：

- `paragraph_id`：稳定主键，当前 gold 主定位
- `spine_index`：该 HTML 文件在 OPF spine 中的 0-based 序号
- `source_file`：EPUB 内部文件路径
- `chapter`：本书一级章节
- `section`：当前小节
- `text`：规范化后的段落正文

### 3. paragraph_id 稳定性

当前格式：

```text
sisyphus-spine-008-p-0002
```

含义：

- `008`：OPF spine 序号
- `0002`：该 spine 文件内被抽取的第 2 个段落块

对同一 EPUB 字节、同一抽取脚本重复运行，ID 与输出应完全一致。

## 二、证据来源边界

### 可用作 gold 的范围

优先且默认只用作者正文：

- 荒诞推理
- 荒诞人
- 荒诞创作
- 西西弗神话

### 不可用作作者正文 gold 的范围

- 目录
- CIP / 版权页
- 译序
- 编者或出版者按语
- 题词注释
- 补编
- 附编

尤其注意：译序可以帮助理解，但不能拿来替代加缪正文证据。

## 三、EPUB 定位规则

### 1. paragraph_id 是主定位

当前证据回查顺序：

1. `paragraph_id`
2. `chapter` + `section`
3. `source_file`
4. `spine_index`
5. `excerpt` 子串核验

### 2. page 当前必须为 null

本地 EPUB 是可重排电子书，没有可靠固定页码。因此：

```yaml
source_locator:
  chapter: 荒诞推理
  section: 荒诞与自杀
  page: null
  paragraph: sisyphus-spine-008-p-0002
```

不能：

- 根据阅读器屏幕页数填写页码
- 根据其他版本猜页码
- 把 spine_index 当页码
- 为满足旧标注规范而虚构页码

如果后续取得同版 PDF，可建立“paragraph_id → PDF page”附加映射；但 paragraph_id 仍应保留。

## 四、逐题标注流程

### Step 1. 判断题面是否由正文直接支持

逐题确认：

1. 问题是否可由当前指定译本正文作答？
2. 是否只需作者正文，不依赖译序、附编或外部文学史知识？
3. 是否存在一组最小充分段落支持答案？
4. 是否需要最小题面改写来适配 EPUB 的 paragraph 级定位？

若不能稳定满足，保留 `candidate_unverified`，并填写具体 `verification_note`。

### Step 2. 选择最小充分证据

每条 `gold_evidence` 至少包含：

```yaml
- paragraph_id: sisyphus-spine-008-p-0002
  excerpt: 真正严肃的哲学问题只有一个，那便是自杀。
```

约束：

- `paragraph_id` 必须真实存在于 `corpus.local.jsonl`
- `excerpt` 必须是该段 `text` 的连续原样子串
- 不意译冒充摘录
- 不拼接远距离段落成为一个 excerpt
- 多段证据时，每段单独列出
- 尽量用最短但足够支持答案的 excerpt

### Step 3. 撰写 gold_answer

`gold_answer` 是基于证据的标准答案，不要求逐字摘抄；但必须满足：

- 只写证据能支持的内容
- 不加入二手解释
- 不混用其他译本用词
- 不把作者提出的问题误写成最终立场
- Level 1 建议 1–3 句；Level 2 建议 2–5 句

### Step 4. 填写 source_locator

当前字段约束：

- `chapter`：必须与 corpus 对应段一致
- `section`：必须与 corpus 对应段一致
- `page`：当前固定 `null`
- `paragraph`：单证据题填写主证据的 `paragraph_id`；多证据题可填写 paragraph_id 列表

### Step 5. 设置状态

只有同时满足以下条件才可设为 `verified_v1`：

- `gold_answer` 非空
- `gold_evidence` 非空
- 每个 evidence paragraph_id 均存在
- 每个 excerpt 均为对应 paragraph text 的子串
- 定位来自作者正文范围
- 答案没有超出证据
- `verification_note` 说明首轮核验结果及页码边界

否则保留 `candidate_unverified`。

## 五、跨译本与术语风险

常见风险词：

- 荒诞
- 清醒
- 反抗
- 自由
- 激情
- 哲学的自杀
- 荒诞的藩篱

处理原则：

- 问题保持概念导向，但 gold 使用当前沈志明译本实际用词
- 不从网络引语或其他译本搬句子
- 对流行引语必须回到 corpus 原段核验
- 必要时只做最小题面改写，保持原题型与难度

## 六、gold chunk 匹配策略

现有 `RetrieverAgent.evaluate` 需要 `golden_chunks: list[str]`。

### 当前推荐策略

在尚未接入正式 chunk pipeline 前：

1. 用 evidence 的 `paragraph_id` 找到 corpus 行
2. 优先将完整 paragraph `text` 作为 canonical gold chunk
3. `excerpt` 仅用于人工审计，不建议替代完整 canonical paragraph
4. 评测报告保留 paragraph_id，方便定位检索失败

### 不推荐策略

- 用人工总结句代替 chunk
- 把多个不连续段落拼成一个 chunk
- 使用其他译本近义句
- 只存章节名而不存 paragraph_id
- 用 EPUB 阅读器页码做匹配键

## 七、映射到 RetrieverAgent.evaluate

现有最小输入：

```python
{
  "query": str,
  "golden_chunks": list[str],
  "golden_answer": str,
  "top_k": int,
}
```

建议映射：

- `query` ← `question`
- `golden_chunks` ← 每条 `gold_evidence.paragraph_id` 对应的完整 corpus `text`
- `golden_answer` ← `gold_answer`
- `top_k` ← 实验协议指定，首轮可统一为 5

未验证题不得进入正式非降级 benchmark 分数。

## 八、自动自检要求

每次改完题集或抽取脚本，至少验证：

- 脚本连续运行两次输出 SHA-256 相同
- JSONL 每行可被 `json.loads` 解析
- `paragraph_id` 全局唯一
- `questions.v1.yaml` 可被 YAML 解析器解析
- 题数恰好 20
- Level 1 / Level 2 各 10
- 每个 `verified_v1` 的 evidence paragraph_id 真实存在
- 每个 evidence excerpt 是对应 paragraph text 的连续子串
- 未验证题有非空 `verification_note`
- `source_locator.page` 没有虚构值

## 九、当前下一步

1. 先用 `verified_v1` 子集映射成 `RetrieverAgent.evaluate` 输入
2. 运行首轮 retrieval baseline，记录 recall@k、context_precision、latency 与 degraded 状态
3. 对未验证题做第二轮人工阅读：补证据、最小修题或决定淘汰
4. 抽样复核完整 paragraph 作为 gold chunk 是否与正式检索切分策略兼容
5. 若业务确实需要页码，再引入同版 PDF 映射，不从 EPUB 推测页码
