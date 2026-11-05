# Task13 首次真实浏览器与双标签运行

本记录为阶段性失败证据，不代表正式教学、恢复、持久化重启或第一阶段完成。

- 运行前 Git HEAD `3c9fae413309731b181e72475cf71c980531e7e4`，Task13 受审源码仍为工作区候选；冻结 app、web、相关测试与配置 189 文件，私有指纹清单 SHA-256 `7c54a7f9a353cd1a949d796e9bfdbd5abfa0c80bb86ec52fde3ee9122e6a0a0e`，主浏览器运行后、双标签探针启动前核文件内容未变化；双标签探针结束后复核发现仅 `web/e2e/workspace-real.spec.ts` 已变化，当前 SHA-256 `1A4349B5CDD91FFD8FB81A81BC18D18BAA8D619E93165A140CF6DB9A5D88EA99`，因此不将双标签结果归于完全未漂移的整体候选。主浏览器运行时浏览器主脚本和双标签脚本分别与独审指纹一致。
- 模型代理原生检查 `127.0.0.1:8317` 监听；专用 PG 容器 `studyagent-task13-pg-efb44382858d`、独立卷 `studyagent-task13-pg-efb44382858d-data`、仅本机端口 65301，随机库迁移至 `20261023_private_library`、vector 0.8.7。未重启或修改共享数据库。
- 观察版应用以单进程正式入口启动，隔离后端 `127.0.0.1:50520` 健康检查 200，真实监听 PID 22908。模型三项从已授权配置仅注入进程，禁用 Langfuse 和 RAG；未归档配置值、凭据、原始提示或原始运行日志。后端当前仍保留运行供主会话处置。
- `npm --prefix web run e2e` 按正式配置实际运行 26 项，exit 1，**25 passed、1 failed**；[脱敏日志](real-browser-first-run.log)，原始日志和退出码在 ignored `.superpowers/runtime/task13/run-96a276ddab83/`。真实 Task13 组已经通过真实界面注册、建会话和创建知识点，但在 `web/e2e/workspace-real.spec.ts:147` 选点前断言失败：定位器实际解析到带节点 UUID 的 option，`toHaveValue` 报空值。该记录只反映现象，是否为测试断言或产品问题须诊断。未进入真实教学、评分、重登恢复；主场景清单与模型见证文件均不存在。不能将其他 25 项通过视作 Task13 主链通过。
- 按计划停止了依赖主清单的 Python baseline、应用重启、PG 重启和隔离矩阵；未跳过主链缺口自行补造数据。运行结束未检测到观察器固定写入故障信号，不能把未产生的见证算作通过。
- 双标签独立探针使用另两组合成账号、经独立审查 SHA-256 `23F7C357FF220B09AD2CB7F2DD6998C9D0002D4372A31F579F873C381E110CAA`，本轮临时 Vite 使用仅本机端口 63043，前端及代理健康检查 200。探针 exit 1，固定错误 `TASK13_TWO_TAB_FAILED stage=block-a`；私有日志位于 ignored `.superpowers/runtime/task13/two-tab-isolation/`。探针进入该阶段前已完成受控离线草稿 PATCH 失败与无成功 ACK、独立在线 snapshot 未保存、B 在线注册与共享身份核对、A 知识库初始化拒绝，以及 B 初始真实创建。固定错误输出无法定位该阶段具体失败断言，不能判为产品缺陷或探针通过；A 备份退出及 B 退出后真实读写未完成。
- 双标签临时 Vite 已核 PID、启动时间和命令后停止；首次清理比较因日期对象格式导致身份校验拒绝，核实正确身份后成功关闭。未自动重跑任一失败场景，未更改源码、暂存或提交。

