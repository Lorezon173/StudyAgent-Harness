# Task10 隔离验收辅助代码独立审查

结论：**不通过（存在阻断项）**。本结论仅针对隔离验收辅助代码，不代表产品代码或真实功能验收结论。修复前须按派审要求完成新一轮计划审查；本次未修改实现或测试。

## P1：硬链接绕过旧库保护

位置：`acceptance_harness.py:150-169`、`:207-216`。路径校验使用 `Path.resolve()` 和最终文件名，但硬链接的不同路径指向同一文件且不会由 resolve 归一为同一路径。因此 runtime 下名为 `acceptance.db` 的已有文件若是 runtime 外 `study_agent.db` 的硬链接，就会通过检查，后续 SQLite 连接可对旧库写入；路径字符串仍位于 runtime 内不能保证底层文件隔离。这违背计划要求的拒绝旧库、不得修改已有用户数据库。数据库和控制文件不同路径的同一文件别名也不会被当前相等比较识别。

隔离复现：在完全独立的 `.superpowers/sdd/hardlink-review-8b7d681af32444dfba5ca4f35e88cc02/` 新建空白 `study_agent.db` 和指向其的 `acceptance.db` 硬链接，模拟项目锚点和 runtime 后调用原校验函数；原生诊断输出 `hardlink_same_file: True`、`validation_accepted: True`。没有连接 SQLite，也没有读取或修改真实旧库。两个空样本留存以供审计；不得对真实数据库创建硬链接或用写入真实数据库验证。测试的 `test_path_validation_reuse_and_credentials_without_overwrite` 只覆盖路径名与一般复用，未覆盖同文件硬链接。

## P2：在途请求消耗重置后的新故障计数

位置：`acceptance_harness.py:78,100-101,124-140`。请求进入时只判断计数是否非零，完成后再读取全局当前值，未绑定本次计数配置。隔离 ASGI 诊断中，设置 `drop_chat_responses=1` 后启动并暂停真实内层模拟请求 A；通过认证控制 API 依次设置 0、1，再让 A 完成并返回 `completed/persisted=true`。结果 A 得到 503、新计数变为 0，即此前请求消耗了重置后面向后续请求的配置。该交错违背计划的“每请求捕获该次故障模式”；故障归因及预期下一个请求的验收结果会错位。现有并发测试只检查同一配置下四个同时完成请求不会多消耗，没有覆盖控制更新交错。

## 已核查与验证范围

- 审查了计划、独立计划审查、实现报告、两源码及原始 RED/GREEN/验证日志，并检查 `app/main.py`、`app/core/database.py`、`app/core/config.py` 的衔接。审前、审后 SHA256 均为：计划 `93ccf6b46347650d99f79029668d967c803283202d117ceee484e48f9910b51e`；实现 `cc26a0cf479d34d8c91c877f6c0922867279ec41bd3d138305eec40fa7083df7`；测试 `db3f5914a38cb9b57be1c34e461d5ef5fc0d6c170d0b80a120e253f10f303151`。
- 静态检查显示 token 格式、常数时间比较、局部控制范围、目标路由、成功且已持久化后才替换、非目标请求透传、超 2 MiB 分段回放和异常传播均有相应实现；现有测试覆盖其主要 dummy 场景。`engine` 导入后且 lifespan 首次连接前注册 SQLite connect pragma，配置在导入前设置；但未实测真实配置成功导入与 SQLite pragma。
- 原始日志报告 9 项通过；本次未重复 pytest。只运行上述两个隔离技术探针，未启动真实服务、浏览器或模型，未访问真实用户数据。ASGI 的 lifespan、receive 测试是模拟透传，不能替代真实服务验收。
- README 维护由 Task10 主会话按已审查计划处理；本审查按指定范围仅新增报告，不改产品、依赖或 README。
