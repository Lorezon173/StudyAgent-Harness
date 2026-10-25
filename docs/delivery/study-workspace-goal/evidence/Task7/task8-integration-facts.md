# Task8 接线事实核查（仅准备，不提前实现）

基于HEAD3224379只读核查：

- app/api/chat.py与chat_stream.py目前分别加载SQLAlchemyMasteryStore，调用run_online_agent_session不传context，再调用persist_turn。Task7新增可选context不能自行证明HTTP/SSE连续上下文已接线。
- app/api/_persist.py现persist_turn按len(existing)//2推turn_index，session_store.save(state={})，并整图graph.save；Task8必须改为请求claim/当前next_turn_index、候选教学快照及assessment_deltas单原子提交，不能保留该旧路径用于workspace回合而清空schema1。
- 原persist_turn返回int/None仍需兼容包装；父flush、失败全回滚、结果persisted与真实消息读取保留；不能因新内部入口而删旧断言。
- Task6 retry委托app.state.conversation_service，Task8必须真实装配且短事务原子重验；Task7仅候选结果和受控prompt验证不足以关闭retry待验收。

本文件只是下游事实与原计划要求映射；Task8产品与计划尚未开始，全部接线验收仍PENDING。
