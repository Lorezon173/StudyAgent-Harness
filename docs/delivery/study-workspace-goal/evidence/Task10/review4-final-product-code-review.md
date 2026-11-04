# Task10 第四轮独立代码审查

结论：**Needs changes**。已审查第四轮冻结代码及原计划相关路径；以下过期操作保护与计划不一致。没有进行真实功能验收。

## Important：旧 continue 桥接失败仍可能在较新活动观察后发布请求错误

位置：`web/src/store/workspaceController.ts:872-891`，`web/src/store/workspace.ts:240-243,274-278`。

未关联请求的 continue 在读取桥接页时暂停；同一账号、会话、请求 ID/sequence/attempt 和 load sequence 均未变化，但较新的活动状态重查已发起或完成，活动 epoch 或观察序号已变化；随后旧桥接页失败。内层 catch 将原 `historyTicket` 传给 `applySnapshot`，后者只拒绝过期 load sequence，对活动过期仅使 `activityCurrent=false`，仍返回 true 并写历史错误；随后 continue 只核请求 ID 和 sequence，仍写入旧请求错误。较新活动锁本身会保留，但旧失败提示会在较新活动观察之后发布。第四轮计划任务 2 明确要求过期失败校验活动 epoch/观察序号，避免替换较新请求错误。现有 `review4-continue-green.log` 包含较新 **load**、账号及 attempt 等用例，不能证明该同一 load 下的较新活动观察交错。上述是静态代码路径推导，尚未在本审查运行该业务测试；需要延迟桥接页和真实活动重查的测试确认，并避免修复时吞掉仍有效的失败。

## 待核验：跨画像身份不兼容的快照

位置：`web/src/store/workspace.ts:240-247`、`web/src/store/workspaceController.ts:823-829`。

正常活动观察路径会核验新 snapshot 的 session 与 profile 彼此一致及归属当前用户，但直接采用新 session 时没有比较已有 session 的 profile ID；如果同一 session 的异常响应指向当前用户的另一画像，教学域可能接纳新 session，而画像 revision 比较仍以旧画像为基准。第四轮计划明确要求不兼容画像保留旧组并保守处理。现有后端 `SessionService` 没有公开会话改绑画像接口，故本项不能当作正常用户操作已发生的故障；需确认契约防御要求并用实际响应测试或明确证明该数据不可能到达。此项未在本审查实测。

## 已核查证据和边界

- 第三轮审查所列旧 continue 错误在较新 load 后覆盖、教学版本分组脱节，已有对应 RED 与 GREEN；检查新版成功和失败路径，活动过期时教学 session 字段已分组更新而保留较新活动字段。第四轮也增加同版本教学冲突及重查保护；`review4-combined-matrix.log` 和相应定向日志有通过结果。上述第一项说明活动观察变化的另一交错仍需补证。
- 复核原 Task10 及前三轮计划涉及的最近会话路由、账号 generation、存储副本来源、同 ID 多 writer 门禁、消息关联与历史分页主要入口；第四轮对其他 writer 的可见入口及重查矩阵已有测试，不能将模拟 Storage 视为跨浏览器事务或真实持久化验收。发现上述阻断后，本报告不宣称全范围所有组合及后端事务契约均已证明。
- 独立重算 `review4-v2-source-after.json` 的 46 项当前哈希，差异为 0；核对 `review4-v2-final-suite.log` 为 11 文件、319 项通过、退出 0，`review4-v2-final-build.log` 退出 0。此前两次 318/319 与登录测试修改均记录在实施报告；本审查未重新运行全量测试。
- 未进行真实浏览器、真实模型问答、持久化消息读取、PostgreSQL 重启及跨账号验收。必须在最终完整独立代码审查通过后另行开展。
