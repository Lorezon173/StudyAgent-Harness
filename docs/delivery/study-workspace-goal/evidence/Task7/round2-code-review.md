# Task7完整独立代码审查（round1+round2）

Reviewer: task7_code_review。规格未完全compliant；质量Changes requested。仅读20冻结文件与证据，仅针对未覆盖边界小诊断，未重复352组合。

1. P1 teaching_context.py108–113：只接受user/assistant，Task6真实system历史会invalid_history。Task6 DTO role=str，分页支持其他role，已有真实写读fixture；违反旧历史恢复。
2. P1 assembly.py231–232/245–252/282：可信选点UUID但graph缺该node/None，静默清active_node_id导致candidate为null。小诊断原context/state为UUID、空图候选null；临时缺载不应清选择，须保留或明确失败且无评分。
3. P2 teaching_context.py289–292：用用户可控“【当前输入】”首次split，历史含标记加3900字另一条合法消息时AssertionError。2/3历史均复现。
4. P2 teaching_context.py204–210/247–253：候选room减最新两条和固定1024，renderer又给older一半容量。16条历史3500字摘要被接受并推进截止4，最终仅渲染2943字。须统一容量/接受和完整渲染。
5. P2 teaching_context.py127–130：legacy mode=[]、嵌套非法history在set membership抛TypeError，违合法类型才识别/非法兼容默认。

其余schema1/扩展、实际下游两轮/会话隔离、候选count、score/Curator、Policy/observed、离线/RAG及Task6交接有实现测试。7.1与7.3执行限制如实；真实生产摘要注入/HTTP-SSE/PG提交属SC-001移出范围Task8，不列缺陷。原20文件继续冻结，round3 plan独立审后原实现者修复。
