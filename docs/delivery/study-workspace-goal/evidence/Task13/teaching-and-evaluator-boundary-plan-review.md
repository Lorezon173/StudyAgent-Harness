# Task13 教学与评价边界修订计划独立复核

**结论　PASS（实施计划），无阻断项。** 送审 SHA256 `1EBE5FB2B1E7FC18B579251A75356E00A9173D1FEFB502374852EF5806389D80` 与文件一致。已对照[整分支发现](branch-ocr-review.md#medium)、[pytest 归因和单项诊断](pytest-environment-diagnosis.md)、原设计及实际调用源码。

- **非法等级与协作环。** `CriticAgent._assess_user_message` 在正式上下文、有效当前节点、有待答题且分数有效时，将 JSON 值直接用于集合成员检查，数组和对象会抛 TypeError，阻断之后的 confusion、contradiction 等事件。计划在正式上下文的等级检查中加字符串条件，保留合法枚举和无上下文兼容入口。受控用例要求同一非法等级响应中的合法观察仍出现、实际协作环仍返回回复、无评分事件或 delta、练习评分不推进，正对照再核有效等级和正确节点/题目关联。符合原设计以真实答题证据评分的边界。
- **历史引用。** `build_teaching_context` 仅在状态为 awaiting_response 且最近助手消息正文匹配时确定 question_message_id，`_history_layout` 现按文本取保留历史第一项，正式提交却核最近助手消息。计划在实际保留历史中以已核 ID、角色和正文三项匹配，未保留或不匹配时保留既有旧题文本及裁剪上限。重复同文保留两项的 RED 能区分旧行为和修订；最新助手为另一题的场景能锁定回退。原历史预算、状态及评分存证接口不变。
- **评价测试和可用性。** 归因档案已记录 Fake、隔离 SQLite、空密钥的单项无 judge 实验，原数值测试因 context_precision 为 None 抛 TypeError。真实 `RetrieverAgent.evaluate` 的动态导入点可通过测试作用域 monkeypatch 提供 judge 的 llm/embeddings 和三项 RAGAS/Dataset 替身，与 `test_rag_d.py` 已有模式一致。计划从真实评价入口执行检索和机械指标，保留原召回、三项数值区间、冗余和延迟断言，并核实际检索上下文、judge 参数和三个可区分的有限值。现有不可用时返回 None 的独立测试与产品合同保持。实施时替身返回的分值可用生产归一化实际读取的列表形状，并在替身外核调用及参数，避免生产捕获评估异常时掩盖断言。
- **范围与证据。** 白名单为 Critic、TeachingContext、上下文测试、旧 Retriever 集成测试共四个文件。路由、生产 RAG/评价逻辑及超长输入 Low 均独立。默认 pytest 全量通过进程环境明确 Fake、RAG disabled、独立 SQLite 和隔离模型凭据，真实模型、PG 和浏览器仍单独运行。按独立计划、冻结后的增量审查与正式功能门槛收口。

本次未修改源码或执行任何测试、模型或正式验收。
