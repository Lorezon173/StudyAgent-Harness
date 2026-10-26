# Task8 round1计划初审

Reviewer: task8_plan_review。结论NEEDS REVISION。审阅依据为主会话成功Get-Content的冻结计划原文摘录、HEAD75be601源码/CLAUDE事实，通过两条资料消息提供；审阅者未直接打开raw/全库，对未核证处没有给PASS。

三项阻断：
1. orchestration ConversationService调用api._persist.commit_turn及API DirtyFlag违反单向依赖。事务核心应放编排层/更下层，API旧入口薄包装；flag实现置下层唯一owner并兼容reexport。
2. 新session_id是全局PK，除默认画像unique竞争外，首次同sid同rid/不同JWT抢sid也必须整体管理rollback后重新核owner/request/payload/base，仅一个acquired；sameowner同req重放，异主403，同主异req busy/version，不能500或认领。
3. 旧persist_turn仍可能state={}及整图save破坏已有workspace；须owner核验后在任何旧写之前识别profile绑定/schema工作区并拒绝/安全None，验证原state/messages/graph不变；legacy int/None/403/父flush/一次commit/rollback保持。

需统一未完成reply为空/persistedfalse真实status，SSE failed只error/completed存储final；PG连通已验证/业务未验收一致。

主会话据此交原规划者修v1.1，明确turn_commit.py与infra dirty_flag.py owner、首次创建竞争、旧包装硬拒绝及断连/commit按session行锁序的可实现线性点；原产品未改，修订后独立复审。
