# Task6 round1 独立代码审查

Reviewer: task6_code_review。规格：主体符合，但无参旧消息行为不符合。质量：Changes requested，1项P2，无P0/P1。

P2：app/orchestration/session_service.py:151–153无cursor/limit分支按turn_index/role/id排序；基线MessageStore.list_by_session按id ASC。合法历史先写assistant(turn0,id1)后写user(turn0,id2)时，响应顺序由assistant,user变user,assistant，违反无参旧行为保留。现有数组类型与有序fixture不能覆盖。要求恢复无参id ASC，显式分页继续新键并补非单调历史断言。

其余JWT隔离、空会话、schema/legacy、双游标、快照锁序、view只读、CAS/rollback、retry先预检再503或释放事务委托未见阻断。日志22APIpass；服务组合15pass1PG环境error，恢复单项1pass；真实PG Lock/blocker、SQLite driver事务及物理连接成立。Task7连续上下文及Task8真实重试/HTTP-SSE原子闭环尚未由本轮证明，保留PENDING。

处置：round2计划独立审查后交原实现者，不直接改产品。范围复审关闭前Task6不得DONE。
