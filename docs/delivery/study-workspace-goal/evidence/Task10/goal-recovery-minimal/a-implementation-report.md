# Task10 方案 A 局部实施记录

日期：2026-11-03。此记录不代表独立代码审查或 Task10 真实验收通过。

第七轮 `review7-source-after.json` 所列 46 项实施前逐项重算一致。工作区已有大量更改，保留现有内容；相对该清单仅 `web/src/store/workspaceController.ts` 和 `web/src/pages/Chat.test.tsx` 变化。最终全量测试与构建前后 46 项 SHA256 见 `a-final-source-before.json`、`a-final-source-after.json`，差异 0。README 只追加当前状态；未提交、推送或改动后端。

## 复现与修改

`a-existing-conflict-red.log`：使用实际 App、AuthProvider、store 和页面按钮，第一次发送经受控响应进入 inconsistent；两个“重新查询”均从该状态启动，较早 A 消息页挂起，较新 B 返回同一请求的可信矛盾，A 返回正确消息后实际变为 matched，预期仍为 inconsistent。测试 1 failed，退出码 1；这是 jsdom/RTL 受控网络业务复现，不是真实浏览器或线上事故的证据。

controller 在相同账号代次及完整请求事实、响应和基线的在途域中记录启动次序、活动数和真正发布的可信冲突次序；较旧成功不能覆盖较新可信冲突，也不执行该次清理；域实例自身结束后回收。未新增存储格式、API、调度器或分页框架。同步状态合并内消息 ID 冲突和异常中的可信矛盾均记录冲突，普通异常不记录。既有来源、当前身份和 UI 资格检查保留。

`a-existing-conflict-writer.log`：已有冲突下较新可信冲突、503、游标回环三项通过；冲突后保留警告、发送门禁、本人和另一 writer 副本，不重复 POST；后续主动一致重查可恢复。503/游标失败后旧有效成功可恢复。已有页面测试另覆盖来源变化警告与冲突不发布、独立请求、账号代次/UI sequence 与其他 writer，但这些既有场景并非本次新增字段所有身份组合的穷举。

## 回归与分页

`a-final-suite.log`：11 文件、365 项通过，退出码 0；`a-final-build.log`：TypeScript/Vite 构建通过，退出码 0。中间测试和最初业务 RED 日志保留。后端 `session_service.py` 的分页先检查所有权，按 turn/role/id 向旧记录分页并反转页内顺序；原计划允许取齐、越过目标或 cursor 耗尽停止。此次未更改原分页行为；原计划“历史记录缺失”条目与精确查找段的措辞歧义仍待实际触及时确认。

## 尚未完成

- 本次未在真实浏览器完成受控交错。最小设施需独立本地前端与测试专用受控响应服务，按请求和 cursor 显式释放页面响应，并记录按钮操作、请求时序和截图；不能使用真实模型伪造可信矛盾。
- 尚未单独完成已有 inconsistent 起点下来源失效、完整身份变化与 UI sequence 的组合矩阵；已有相邻覆盖不能冒充该矩阵。应在独立审查中核对缺口，并按计划决定必要补测。
- 尚未完成全范围独立 OCR 审查及真实浏览器、真实模型、正常退出、慢生成切换、失败/冲突/断网恢复、PostgreSQL 重启与跨账号拒绝验收。受控测试和静态构建不能替代这些结果。
- IndexedDB、FIFO、全历史扫描等 B 方案未实施，继续按 TODO 的 DEC-SESSION-001 待独立决策。
