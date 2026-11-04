# Task10 隔离验收辅助实施报告

实施范围：仅 acceptance_harness.py、acceptance_harness_test.py 及 harness 日志/报告；未修改 app/web/README/依赖/账本，未 stage/commit。依据已PASS计划93ccf6b46347650d99f79029668d967c803283202d117ceee484e48f9910b51e。已载入 Karpathy。
未启动真实服务、未调用模型、未读取授权模型env、未跑浏览器或真实功能验收、未碰用户数据库。

## 实现与接口

create_fault_app(real_app, control_token) 返回ASGI包装；控制token要求64位hex，控制API严格loopback客户端+常数时间校验，不进入产品app或日志。GET列出计数，POST严格校验JSON未知/重复字段、整数类型、上下界、1024字节限制。精确PATCH注入503不调业务；其他方法/嵌套路径透传。
POST /api/chat仅在内层完整成功返回、状态2xx且completed/persisted=true时原子消费计数并替换503；其他响应不消费。仅目标chat缓冲，缓存先判2MiB上限，超限先回放已有分段再流式透传，保留真实完整响应；映射按发送时快照保存以兼容内层复用事件。内层异常照抛，receive/disconnect/lifespan透传。
load_runtime_configuration仅调用时读指定env三个模型字段；host.docker.internal/gateway.docker.internal映射127.0.0.1，其他公网域名保留。强制独立SQLite/RAG关闭，真实app导入前配置，SQLite connect启foreign_keys；入口加项目根sys.path。只有main启动127.0.0.1，默认8001。
DB/control路径resolve且限制专用runtime；拒绝穿越、同路径、study_agent.db和外跳；已有DB不删除。控制文件有效schema/64hex才复用，无效文件拒绝不覆盖，新建独占写入。不包含模型密钥或真实草稿。

## 环境故障与原测试

原2076为透传骨架+第1测试的RED；2403为扩展后的全测试。2076尚未终态时编辑并启动2403是执行失误，因此其RED不可证明稳定源码业务行为。
二者默认沙箱长期无输出。普通沙箱Get-Process看不到对应进程不能证明退出；主会话原生诊断确认活PID17096/20568及父进程仍在、CPU一分钟不增长。主会话另以有界最小asyncio立即返回协程诊断：默认沙箱8秒超时，原生执行exit0；原生pytest --version也exit0。静态标准库显示Windows事件循环创建socketpair自管道。结论是有受限执行环境asyncio阻塞证据，未把观察超时作为测试失败。
按主会话明确授权仅原生终止这两个子PID，随后原2076/2403均terminal：shell exit0但打印pytest exit=-1。-1是人为中止，绝非通过；原harness-red.log及原绿色空日志状况已如实记录，原红空日志保留。最终harness-green.log记录的是后续独立原生验证。

## 真实 RED → GREEN

新增复用ASGI body事件映射的测试：修复前缓存保留可变mapping引用，两段都变成最后一段，httpx检测重复完成而AssertionError。原生harness-native-red.log：1 failed/8 deselected，pytest exit1，这是有意义业务RED。
随后最小修改事件快照，修正缓存越限前判断/透传及入口sys.path，再原生一次运行完整pytest及py_compile：9 passed in 0.24s，pytest exit0，compile exit0。harness-verification.log列出退出码。
修复前未当时采集源码hash，不能补称同期已冻结。harness-red-source-report.md按已记录最小patch从GREEN反向精确重建RED源码并标明重建来源；重建SHA256为36BAEA690D65DB2B257CA9903627B6B0FB65A35A35E60D1A61F8EE720782E972，仅用于回溯，不等于同期测量。

9项测试：
1. 鉴权、schema类型、有限消费、精确路由、业务不调用及恢复。
2. 远程拒绝、未知/重复字段、上限、超长body、错误不改变状态。
3. 真实dummy完成后丢回包503、后续GET读回保存事实、workspace消费恢复。
4. 500/failed/nonpersisted/非JSON不消费，多分段超过2MiB完整透传。
5. 并发4完成仅1个503，避免重复消费。
6. 真实ASGI lifespan启动透传、receive对象/断线透传、内层异常不消费。
7. 外部DB/穿越/旧库名/同文件拒绝，无效凭据不覆盖，合法复用不改DB。
8. 模型配置不完整拒绝且不创建runtime，不导入真实app。
9. 内层复用ASGI事件映射的缓存完整性回归。

## 最终冻结 SHA256

acceptance_harness.py CC26A0CF479D34D8C91C877F6C0922867279EC41BD3D138305EEC40FA7083DF7
acceptance_harness_test.py DB3F5914A38CB9B57BE1C34E461D5EF5FC0D6C170D0B80A120E253F10F303151

## 交付限制

当前仅dummy ASGI技术验证，真实模型、SQLite持久化、浏览器用户实际收到响应及后续PostgreSQL重启都未验收。主会话需独立辅助代码审查与产品整体审查PASS后才使用本辅助；实际验收报告应分别记录人工503、真实生成、持久化读回和用户接收。路径测试没有创建Windows外跳符号链接（逻辑resolve边界仍检查）；未测试真实模型配置成功导入/数据库pragma，留给独立审查和后续隔离验收。报告不含控制token或模型配置内容。冻结后不再更改两源码文件。
