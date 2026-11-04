# Task10 隔离功能验收辅助服务计划

来源：已PASS的Task10 v1.3（SHA0d7d3199），其中功能验收明确要求真实浏览器、独立账号/数据库和安全可控故障。此子计划只让测试环境能模拟保存失败与真实回复回包失败，不改变产品契约；本计划须独立子代理PASS后编码，辅助代码再独立审查，整个Task10产品代码独立审查PASS后才运行真实功能验收。

## 第一层：目标、边界与依赖

正向路径调用当前分支真实FastAPI应用、真实SQLAlchemy持久化及用户授权的Docker模型配置。辅助服务仅在127.0.0.1监听独立端口8001，前端独立5174；不使用或修改已有服务/数据库。仅允许新增 docs/delivery/study-workspace-goal/evidence/Task10/acceptance_harness.py 和 acceptance_harness_test.py，以及该辅助的日志/报告。依赖项目现有FastAPI/Starlette/httpx/pytest/uvicorn/dotenv，不安装包，不改app/web/依赖/README/账本，不提交凭据/DB。

独立持久库及控制凭据文件必须在解析后的项目 .superpowers/runtime/task10-acceptance/ 内；拒绝外部路径与旧study_agent.db，不删除或覆盖已有数据库/凭据。进程读取指定env文件时只消费OPENAI_API_KEY/OPENAI_BASE_URL/OPENAI_MODEL（不打印），容器主机名在本机进程适配127.0.0.1，强制RAG_ENABLED=false和独立SQLite URL。SQLite连接启用foreign_keys=ON，仅对验收进程生效。正向业务仍由真实后端执行，不伪造模型或消息数据。

## 第二层：职责、接口与状态

1. create_fault_app(real_app, control_token) 返回ASGI包装，导入该模块不启动服务。真实应用lifespan与请求接收/鉴权/保存保持原样。控制路由 /__acceptance__/faults 只接受带 X-Acceptance-Control 的本地请求，使用constant-time比较随机控制token；无/错token返回401且不改状态。控制token不少于32随机字节等价强度，启动时仅在本地新文件内存放，不打印或写日志、不传给浏览器。
2. 故障状态仅为有限计数 view_failures(0–10)、workspace_failures(0–10)、drop_chat_responses(0–3)，GET返回计数、POST设置并严格拒绝未知字段/类型/过大值和超过1024字节body。仅适配精确路径和方法：PATCH /api/sessions/{单一编码路径段}/view-state、PATCH /api/workspace-state、POST /api/chat；不得影响GET、retry、auth、profile或其他路径。
3. view/workspace保存故障只在相应计数>0时原子消费一次，直接503结构化错误，真实数据库不写；恢复计数归零后照常转发。模型回复丢失模式先让真实 /api/chat 执行并完成响应，再替换为503，使客户端走结果待确认并查询真实request；仅在内层成功状态码且body确认为completed/persisted=true时消费计数并替换，否则照实返回失败，不伪称成功。丢失模式需缓冲这一条响应的start/body，其他响应流式透传，不改变receive/disconnect行为；限响应缓存最多2MiB，超限关闭该次模拟并保留真实完整响应（已缓冲分段+后续透传），不得截断或卡住。发生内层异常照常上抛，不制造成功。
4. 任意控制API错误都不记录请求正文、原文、token或模型密钥。故障处理不是产品功能，报告必须标注哪些为人工注入，不能把503后的模型成功当作用户已收到答复；最终持久化与消息读取仍单独检查。

## 第三层：详细实施与验收

- 参数解析仅负责 port(默认8001且仅loopback)、env-file、database-path、control-file；路径先resolve并严格校验在专用runtime内，拒绝穿越及已有凭据覆盖；控制文件已存在则只在有效schema/随机token格式下复用，不打印内容；数据库存在则复用持久内容，不重置。未提供模型配置或密钥时明确启动错误，不写假模型响应。创建目录前检查其祖先解析路径及非符号链接外跳，不修改全局环境配置。
- load_runtime_configuration负责进程内白名单env加载和独立数据库设置，之后才导入真实app/database，注册SQLite connect pragma，返回ASGI app和Uvicorn配置；只有main入口运行服务器。控制endpoint由包装独立处理，不向真实API暴露控制token。
- FaultMiddleware仅持计数状态、token及真实app引用。单事件循环下计数消费同步且不跨await，POST控制更新整个校验后的值；每请求捕获该次故障模式，别的并发请求不得误消费同一次。路径匹配不得误命中嵌套/相似path或GET。POST chat回包替换必须保留request已真实完成事实；不改变idempotency/request_id/attempt/业务事务。
- 先写有意义RED测试，再实现GREEN：真实ASGI dummy内层+httpx测试控制鉴权、schema/长度拒绝、有限计数消费、只影响精确PATCH、原业务未被调用、恢复后透传；chat模式先证明内层执行并完成，再503，随后普通GET读回其实际保存结果；failed/nonpersisted响应不消费或伪造；超2MiB缓冲安全退化透传、内层异常、lifespan及receive透传。路径配置校验测试拒绝外部DB、穿越、凭据覆盖且不产生对应文件，合法复用不删数据。测试不启动真实模型/浏览器。
- 定向pytest保存原始RED/GREEN日志与退出码；模块编译检查；完整两文件SHA冻结及实现报告。不要执行辅助服务或真实功能验收，等待独立代码审查和主产品代码审查均PASS。
- 真正功能验收时主会话先启动隔离服务/前端、创建专用账号并实际操作浏览器；故障控制只在此专用服务上启用。分别记录正向、注入503、恢复后的读回，结束仅停止自己启动的进程，保留证据和DB供审计，不碰既有用户数据或其他窗口。
