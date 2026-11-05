# Task13 同运行 PG 重新接入与账号隔离结果

本记录续接[第二轮主链阶段记录](real-browser-second-run-summary.md)，保留原 PG 阶段的 HTTP 500 与动态端口变化证据。它仅覆盖本文件所述真实链路，不替代 Task13 其他回归、故障注入和整分支审查门槛。

- 按[重连计划及独审](pg-reconnect-plan-review.md)，核验同一容器 ID、独立卷、数据库、迁移 head、postmaster 时间与宿主机当前 63149 端口，以及旧观察应用 PID 20992、启动时间、进程树和监听。只重启该应用并让私有连接指向当前端口，未重启数据库、重新迁移或更改原数据。新观察应用 PID 34044，健康检查及原 A/B 的真实登录均为 HTTP 200，账号 ID 与主清单一致。
- [PG 重启后重新接入读回](real-pg-reconnected-round2.log) exit 0、1 passed / 1 skipped；跳过的是只在 isolation 阶段执行的用例。成功 checkpoint 从原运行的清单、baseline 和应用单独重启 checkpoint 继续生成，核相同业务状态、迁移 head、同卷与真实模型见证。baseline→应用重启→重新接入三个阶段 run、库、容器、卷一致；应用单独重启时应用身份变化、PG postmaster 不变；PG 重启后 postmaster 变化。此次结果表述为 **PG 重启后经应用重新接入成功读回**，不证明端口变化期间应用无感自动恢复。
- [跨账号 isolation](real-isolation-round2.log) exit 0、1 passed / 1 skipped（非该阶段的读回用例跳过）；使用同一 run 和主清单，包含 B 合法资源正对照、受控 HTTP 断连形成 interrupted 请求及真实重试、session/profile/node/library/request 五类 ID 的替换与拒绝、A 的状态和数据无副作用核对。
- [双标签 v3](real-two-tab-round3.log) exit 0，固定成功标记。脚本 SHA-256 `B1C7AA221666618A78386276FE9A654528ABA6814F3454301FE31345BF32453B` 与[独审](two-tab-probe-code-review-v3.md)一致，另用新合成账号，同浏览器上下文两页。按该脚本全部断言，A 页受控断网的草稿 PATCH 失败且无成功 ACK，独立在线 snapshot 未保存该值；B 真实登录后 A 的知识库搜索 GET 和创建 POST 未发出、提示明确且输入保留；A 经真实备份退出后读取到本机恢复记录，B 共享身份保留并经真实 HTTP 读写。仅草稿断网为受控故障，其余使用真实应用。旧失败日志及输入留在 ignored 私有备份，临时 Vite 前端已核实身份并停止。
- 实际候选指纹清单覆盖的 189 个文件在本轮结束复核无变化；三个应用阶段 stderr 捕获文件均存在，均未检出 `TASK13_WITNESS_WRITE_FAILED`。原始运行清单、见证、阶段 JSON、凭据及完整应用日志仅留在 ignored 运行目录，归档日志只含测试结果或固定标记。当前观察后端保留运行；未触碰共享数据库或模型代理进程，未更改源码、暂存或提交。
