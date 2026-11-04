# Task10 第二轮修复计划独立审查 v2

> **更正（v3 复核）：** 下文“唯一 linked 无法通过 request 存储核验”的静态判断错误。`recoveryCandidateUnchanged` 对 `phase: linked` 的派生对象读取的是 prepared 列表，并对变换后的完整对象进行比对。不能据此断言 GET 必然失败；真正尚需证明的是唯一 linked → 消息匹配 → 旧 writer 知情继续的完整用户流程。详见 v3 审查。

结论：**Needs changes**。未修改产品代码；本轮静态检查计划及现有实现，未作真实功能验收。

独立计算 SHA256：raw `2e12264b7c2cd68f8d4057c725fe50ebff236d8e1f2e111f847fbe5757e76d64`；plan `c7a55da35fd2b7cbfae5ca9f6a49067dc864631f7b420baf58f8ea11ce514d13`。均与送审版本一致。

## 上一版三项阻断

1. **继续未关联请求覆盖分页：已补设计。** raw 2.3、3.3 和计划任务 3 增加共享桥接、活动/attempt 复核及继续失败保留，同时明确完成关联的孤立消息不可作为连续页证据，并列出多页、缺口和冲突测试。
2. **写入/读回失败后的已完成内存项：已补设计。** raw 3.2 区分完整读取且不存在、精确持久候选、读取不完整三类，明确匹配完成的内存项与未知持久副本分开处理，保留告警、主动继续及退出边界；计划加入各阶段故障矩阵和其他候选门禁测试。
3. **旧 writer 缺少处理出口：已补设计，但实现路径仍有下述阻断。** 方案提出仅当前代次、候选级知情确认，不删除其他 writer，重新发送前再次核验并说明跨页面非原子性，符合保守边界。

## 新阻断：唯一存活的 linked 副本无法按现有调用链查询

`web/src/store/workspaceController.ts:369-377` 的 `recheckLinkedPreparation` 从 linked 构造一个 request 形状的候选并交给 `recheckCandidate`；后者在第 388–390 行先要求 `recoveryCandidateUnchanged` 验证实际存在的 request 候选。若 linked 写成功但 request 副本写失败，浏览器重启后本地只有 linked，合成的 request 候选不能通过存储核验。这是现有代码调用链的静态发现；尚未运行测试验证完整 UI 表现。

修订方案要求原 ID 查询可从 linked 副本进入，但任务 2 的重启测试只说“保存 linked 后新 writer 重登”，未明确 request 副本必须缺失，也未说明应以实际 linked 副本而非伪造的 request 候选作为查询身份。若测试同时创建 request 副本，不能证明用户在允许的 request 写入失败场景中能继续。该缺口直接关系到原批准契约允许存储部分失败仍发送，以及本轮新增的旧 writer 继续出口。

**修订要求：** 明确当 request 副本不存在或不可作为可信持久项，而 linked 副本完整可读时，逐字段以实际 linked 的 owner/session/writer/prepareId/writeId/requestId/payload/baseline 校验并查询原请求；不要将合成对象冒充已持久化 request 候选。增加真实 Storage 与新 writer 重启测试：linked 是唯一存活副本，查询原 ID、精确匹配持久消息、风险知情确认后用户可主动继续；覆盖 linked 内容在查询中变化、其他 writer 冲突、404/failed/缺少可信 baseline 不误解锁。先对冻结实现记录业务 RED，修复后 GREEN。对于 request 列表读取异常但 linked 可读的情况，需说明是否及如何在告知风险和其他已知门禁保持的前提下可查询，不能将读失败等同不存在。

原有前端回归及这次补测均不能替代独立完整代码复审或真实后端、模型、持久化验收。修订后请再次独立审查。
