# 《西西弗斯神话》RAG Benchmark

## 目标

为《西西弗斯神话》构建一套可人工校验、可映射到现有 `RetrieverAgent.evaluate` 输入契约的书籍级 RAG benchmark。

本次更新把目录从“仅候选骨架”推进到“已锁定本地语料、已抽取正文语料、已完成首轮 20 题核验混合集”。

当前资产包含：

- `extract_epub.py`：只用 Python 标准库，从本地 EPUB 按 OPF spine 抽取正文 JSONL
- `corpus.local.jsonl`：本地生成、`.gitignore` 忽略的正文语料
- `source-manifest.yaml`：语料来源、校验信息、章节清单、输出位置说明
- `questions.v1.yaml`：20 道中文题，含首轮 verified / unverified 状态
- `annotation-guide.md`：针对当前 paragraph_id 语料的标注约束与下一步说明

## 已锁定语料版本

- 作品：阿尔贝·加缪《西西弗斯神话》
- 作者：加缪
- 译者：沈志明
- 出版社：上海译文出版社
- 版次信息：2013.8（据版权页）
- ISBN：978-7-5327-6183-8
- 外部本地源文件：`/Users/ywwl/Downloads/6006-西西弗神话/西西弗神话.epub`
- SHA-256：`341696af4d08a3f0dec622ac2311556495459d68517387bd912c5fcc8d545a7f`

注意：EPUB 内嵌 OPF metadata 的 `creator/publisher` 字段不可靠，因此本目录以用户已验证的版权页信息为准，并在 `source-manifest.yaml` 中显式记录。

## 当前正文范围与抽取边界

本次只抽取作者正文主干，不把以下内容当作 gold 证据来源：

- 目录
- CIP / 版权页
- 题词注释
- 译序
- 补编《弗兰茨·卡夫卡作品中的希望与荒诞》
- 附编《反抗者》节译

当前正文章节覆盖：

1. 荒诞推理 / 卷首语
2. 荒诞推理 / 荒诞与自杀
3. 荒诞推理 / 荒诞的藩篱
4. 荒诞推理 / 哲学的自杀
5. 荒诞推理 / 荒诞自由
6. 荒诞人 / 荒诞人
7. 荒诞人 / 唐璜主义
8. 荒诞人 / 戏剧
9. 荒诞人 / 征服
10. 荒诞创作 / 荒诞创作
11. 荒诞创作 / 哲学与小说
12. 荒诞创作 / 基里洛夫
13. 荒诞创作 / 没有前途的创作
14. 西西弗神话 / 西西弗神话

## 语料文件与定位方式

- 本地语料输出：`corpus.local.jsonl`
- 每行字段：
  - `paragraph_id`
  - `spine_index`
  - `source_file`
  - `chapter`
  - `section`
  - `text`
- 当前首选定位键：`paragraph_id`

`paragraph_id` 是稳定可复现的，格式类似：

- `sisyphus-spine-008-p-0002`

它由“正文在 OPF spine 中的位置 + 该文件中的段落序号”组成，因此在同一源 EPUB、同一抽取规则下可重复生成。

## EPUB 页码边界

本目录当前 **不提供稳定页码作为主定位**。

原因：

- 本地源是 EPUB，不是版式固定 PDF
- EPUB 重排后没有可靠、统一、可复现的页码系统
- 版权页元数据可核验版本，但正文定位更稳定的方式是 `paragraph_id + chapter/section + source_file`

因此：

- `source_locator.page` 当前统一为 `null`
- verified 题优先使用 `source_locator.paragraph` 填 `paragraph_id`
- 后续若补充同版 PDF，可再增加页码映射层；但不能反向编造 EPUB 页码

## 当前题集状态

`questions.v1.yaml` 现有 20 题，结构保持不变：

- Level 1：10 题
- Level 2：10 题

但状态已不再全部是候选：

- 一部分题目已能被当前正文 corpus 直接验证，填写为 `verified_v1`
- 其余题目仍保留未验证状态，并补充 `verification_note`

保留未验证的主要原因包括：

- 题面原本要求“章节 / 小节 / 页码”式定位，而 EPUB 只能稳定给出 paragraph 级定位
- 题目依赖更强的解释链，当前证据还不足以在不引入过度概括的前提下给出稳健标准答案
- 某些题面虽接近可答，但为了不编造或过度外推，暂缓标 verified

## 现有项目接入点与边界

### 已有接入点

- `app/agents/retriever.py:105` 的 `RetrieverAgent.evaluate(test_case)`
  - 当前接受字段：
    - `query: str`
    - `golden_chunks: list[str]`
    - `golden_answer: str`
    - `top_k: int`
- 其返回指标包含：
  - `recall_at_k`
  - `faithfulness`
  - `answer_relevancy`
  - `context_precision`
  - `latency_ms`
  - `redundancy`
  - 以及降级标记 `degraded` / `degraded_reason`

### 明确边界

- 本目录只改 benchmark 局部资产，不引入新的产品运行时代码
- 本目录不把受版权保护原文纳入 Git 跟踪；`corpus.local.jsonl` 为本地忽略文件
- 当前 gold 证据只使用作者正文，不使用译序与附编
- 由于暂无稳定页码层，评测主定位应基于 `paragraph_id`

## 首轮使用建议

### 适合立刻做的事

- 用 `extract_epub.py` 在本地重复生成 corpus
- 以 `verified_v1` 题目先做一轮 retrieval baseline
- 把 `gold_evidence` 中的 `excerpt + paragraph_id` 映射为 `golden_chunks`
- 用未验证题继续人工二次核验

### 暂不应做的事

- 不要把 `page` 当作必填主定位
- 不要把译序或附编摘录当作者正文 gold
- 不要把未验证题强行补成已验证题
- 不要为 EPUB 编造“固定页码”

## 验收标准

本次资产任务完成标准：

- [x] 读取并更新本目录三份既有 benchmark 文件
- [x] 新建 `extract_epub.py`
- [x] 使用标准库从 EPUB 按 OPF spine 抽取正文到 JSONL
- [x] 新建 `.gitignore` 忽略 `corpus.local.jsonl`
- [x] 本地生成 `corpus.local.jsonl`
- [x] 新建 `source-manifest.yaml`
- [x] `questions.v1.yaml` 保持 20 题，Level 1 / Level 2 各 10 题
- [x] verified 题仅填写真实可回查的 `paragraph_id` 与证据摘录
- [x] 未验证题保留未验证状态并说明原因
- [x] README 与 annotation guide 明确：EPUB 无稳定页码、`paragraph_id` 为主定位、当前标注状态与下一步

后续进入正式 benchmark 的额外标准：

- [ ] 将 verified 题完整映射为 `RetrieverAgent.evaluate` 输入并跑 baseline
- [ ] 对未验证题完成第二轮人工核验或必要修题
- [ ] 若需要页码维度，补充同版 PDF 或人工页码映射层
- [ ] 抽样复核 paragraph 级证据与实际检索 chunk 的一致性
