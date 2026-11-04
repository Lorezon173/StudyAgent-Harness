# Task10 localRecovery 实施报告

仅修改 web/src/store/localRecovery.ts 与 localRecovery.test.ts。未 stage/commit，README由主会话维护。

实现：保持原全部API兼容；新增 listResult 与 RecoveryListResult/RecoveryIssue，返回 ok/candidates/issues 固定错误码，保留其他有效候选。兼容 list 只返回数组，调用端需接线 listResult 错误提示（已通知主实施者）。
校验 schema、owner/session/key、writer/write/item、时间、字段白名单；拒绝额外凭据字段。ID最多256字符，草稿/准备原文/请求正文最多4000字符；锚点正数消息ID、0至1偏移；序号/版本为安全非负整数，未知草稿/workspace基础版本允许null。
请求payload绑定session/request，可信基线按计划snake_case完整绑定owner/session/request/profile/base；active_node_id允许null，来源仅before_submit/observed_running_snapshot。null原样保存，legacy数字原样保留但不能作为可信基线，controller负责不升级可信。
单文档singleton writer，每次写入唯一writeId，返回脱离输入的内容快照；仅同writer且完整候选JSON与当前存储相等才删除，删除后读回确认。读写删异常可识别。不删损坏、其他账号/标签/新编辑副本。准备操作独立itemId，与草稿互不覆盖。
检索仓库未发现旧单键实现，依计划不制造无依据迁移。

验证：
- npm.cmd --prefix web test -- localRecovery：RED 4失败/4通过（真实字段/身份错误行为以及新增读取结果接口）；最终GREEN 12通过，退出码0。
- web/node_modules/.bin/tsc.cmd --noEmit -p web/tsconfig.json：最终退出码0。
- 原始日志 docs/delivery/study-workspace-goal/evidence/Task10/local-recovery-red.log、local-recovery-green.log、local-recovery-types.log。
- 尚未开展真实功能验收，等待整体独立代码审查。

冻结SHA256：
- web/src/store/localRecovery.ts FEE4A9FC1EED73A71EA92E0CDA86108D9ECF3D36C8D27259A6D3E84DA2733143
- web/src/store/localRecovery.test.ts 0C4CF9B4ACB2B9153A569ADED5AEFEF15F90D857B14FEDFF5DF06CD69973F9B6
