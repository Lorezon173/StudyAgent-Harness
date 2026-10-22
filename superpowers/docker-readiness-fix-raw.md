# Docker HTTP readiness 修复原始规划

用户已在 2026-10-22 明确要求按前述方案直接开始下一步；本文件将已确认的边界展开为三层实施说明，不扩大到业务、模型、缓存或服务器部署。

## 第一层：模块总览

目标：解决 Windows RemoteDisconnected 与远端 Linux ConnectionResetError 逃出就绪等待的问题，保留严格正式门禁。Python 标准库实现，不新增依赖，不改 Dockerfile、迁移、工作流或业务API。现有独立工作区 codex/docker-deployment-fix 从远端 main b2270d6 继续。

## 第二层：子模块概述

1. HTTP readiness：仅针对本机隔离容器 /health 的启动窗口重试；总期限120秒，单次探测最长5秒且不超过剩余预算，轮询间隔0.5秒且不超过剩余预算。不使用sleep，采用条件等待/事件等待实现节奏。成功需在期限内。健康探测只验证HTTP状态并关闭响应，不下载响应体。普通业务http()仍按原先行为直接传播错误。
2. 失败诊断：在api验收发生失败/超时且容器清理前，采集应用与PG的最近100行带时间戳日志，以及状态/退出码/OOM/重启次数等白名单字段；禁止完整inspect、环境变量、数据库URL及密钥输出。仍复用现有sanitize。诊断失败不能覆盖原始错误，之后照常清理本次拥有的资源。
3. 回归与交付：用真实控制流、仅模拟网络/Docker边界。先记录旧代码失败，再最小实现。全套Ruff和默认回归通过后审查、明确文件提交、推送修复分支并非强制快进main，真实观察Linux技术门禁及归档。模型未配置时继续blocked/skipped，禁止绕过发布门禁。

## 第三层：函数、字段与数据结构

- wait_http(base)：保留现有调用契约；内部使用monotonic deadline、remaining、attempts、last_error，返回None表示就绪；持续连接失败到期抛VerificationError(blocked)，错误说明保留类型而不含敏感URL。重试仅在此函数作用域，覆盖RemoteDisconnected、ConnectionResetError及原有瞬态网络异常。
- 新增最小私有health探测函数或等价局部操作：输入base与当前timeout；GET /health并在上下文中关闭response，只校验状态，不读取正文。HTTP状态异常按既有readiness语义在期限内等待；不能修改普通业务请求的错误行为。
- Sandbox最小诊断方法/等价逻辑：输入本次owned container名与runner；只使用白名单inspect模板与docker logs --tail 100 --timestamps；通过runner.note/command脱敏保存到verification.log；诊断失败写类型/简短说明，不取代原始异常。只在异常路径采集，成功路径不额外泄漏数据。
- 单测用受控时钟及假网络记录timeout、探测次数和事件顺序；不真实等待120秒。包含先断连后200、持续断连期限、请求/间隔剩余预算、成功晚于deadline拒绝、HTTP业务错误不重试、诊断早于删除、敏感字段脱敏、诊断失败仍清理并保留原异常。
- 不新增manifest发布豁免字段。原始失败、诊断对照与本次正式通过分别保留。
