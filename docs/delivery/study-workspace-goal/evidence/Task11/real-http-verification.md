# Task11 独立服务与真实 HTTP 验收（2026-11-04）

在已通过产品 OCR 后使用专用容器 `studyagent-goal-test-pg` 创建 `task11_acceptance_6bc03745f5b24d30b2b82798b154a48c`，未操作原 Task10 库。正式 Alembic 迁移使用 psycopg、应用使用 asyncpg；库名/用户、vector 和版本 `20261023_private_library` 已核对。后端仅本机 50530，Vite 仅本机 50531；后端、首页和代理健康均 HTTP 200。首次启动初期代理超时，随后复查通过。模型配置仅在进程内，RAG关闭、JWT随机，本次没有调用模型。

实际请求及脱敏业务响应记录在 `real-http-responses.json`，不包含认证响应或认证字段。两账号为独立测试账号：A user_id 1、B user_id 2；所有操作仅发生于本次新库。

- A 创建主题、第二节点和两个绑定同主题的会话；detail 和 summary 的 profile_revision 一致，两个 session snapshot 绑定同一真实 profile。该主题两节点均未评估，summary mastery_score=null、assessed_count=0、edges=[]、recent_evidence=[]。
- 经公开 API 创建第二画像并归档唯一节点，summary total_count=0、mastery_score=null、assessment_coverage=null、edges=[]。
- A 创建带唯一标记的私有文本并关联主题，核 owner、profile、source_type 和正文；按关键词和主题搜索、详情读取后，B 的 GET/PATCH/DELETE 该资源和 GET A 画像均返回 404，B 自己列表不含 A 资源，A 再读取原记录不变。A 修改正文、清空描述、解除主题关联后，新请求读回逐字段一致；A 删除成功，再 GET 404。空白名称返回实际接口验证状态 422。
- 为后续页面验收保留单独的 A 私有文本 ID 2；只读数据库复核仅该资源存在，两个会话属于 A 且绑定同画像；该画像2个活动节点、0个edge，空画像0个活动节点。

真实浏览器验收、非空关系、已评分节点及来源跳转尚未验证。现有公开主题接口未提供直接创建边/评分/证据写入，未直接修改数据库伪造评分；若后续真实教学或已授权受控夹具提供来源，须单独标明其证据类型。此次 HTTP 通过不等于 Task11 完成，也不代替 Task13 的数据库重启验收。
