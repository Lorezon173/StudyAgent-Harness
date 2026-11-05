# Task13 已提交分支独立 OCR 审阅

**已提交范围审阅完毕，发现 High，最终候选仍须复核。** 目标提交为 `3c9fae413309731b181e72475cf71c980531e7e4`，基线及实际 merge base 为 `d0584d993b8293a2333acc35f3f5753a08068230`。工作树中的 Task13 验收代码和产品修订由独立增量审阅及主会话最终指纹映射补齐。

## 范围和证据

- OCR v1.13.3，`ocr delegate preview --format json --from d0584d993b8293a2333acc35f3f5753a08068230 --to 3c9fae413309731b181e72475cf71c980531e7e4 --exclude 'docs/delivery/study-workspace-goal/evidence/**'` 返回 range 和 1,492 路径。其中默认可审 81，排除 1,411（`user_exclude` 1,221、`binary` 74、`default_path` 45、`unsupported_ext` 71）。
- 显式纳入所有非历史证据的测试、前端锁文件、运行提示词及配对规范、README 与示例环境，总候选 136。按路径分 6 批执行 `ocr delegate rule --format json`，全部成功。每条候选路径均对应规则组、不可变提交 blob 与实际 Git diff。全路径集合与 Git 分支范围对账。原始 preview 给出 586 条文件读取警告，其中 81 条涉及复核候选，由逐路径 Git 读取补证。警告不计作人工审阅。
- 覆盖核对为 `total_files=1492`、`reviewed_files=136`、`skipped_files=1356`、`coverage_rate=9.12%`（全部路径分母）。136 个正式候选的独立静态审阅覆盖率为 **100%**。其余路径逐条注明历史验收证据、设计计划、过程记录或待办等跳过理由。初始默认排除后补入 55 项，最终跳过数已扣除这些纳入项。
- 产品按数据库迁移与模型、归属 API 与短事务、教学状态和 Agent 提示词、React 身份/草稿/恢复/展示分批审阅。测试按真实 PostgreSQL、SQLite、受控模型、DOM 和浏览器验收逐文件读相关断言，长文件分段补读并对精确重复的夹具行折叠。锁文件结构检查确认新增 75 个包条目均为开发依赖且包含 npm 注册表与完整性字段，无现有非根包条目变更。未执行联网依赖安全审计。
- [逐路径清单](branch-ocr-checklist.json) · [OCR 范围输出](branch-ocr-preview.json)（仅移除本机目录前缀） · [OCR 范围警告](branch-ocr-preview.stderr.txt) · [规则路径](branch-ocr-rule-paths.txt)。

## Critical

已审候选未发现 Critical。

## High

- **旧标签会使用另一标签的新账号凭据。** 以 A 打开知识库，再在同一浏览器另一标签登录 B，旧标签搜索得到 B 的私有条目，且创建未关联主题的卡片会写入 B。旧标签经“退出并保留本机草稿”也会无条件清除共享存储中的 B 凭据。服务端仍按所收 JWT 正确划定账号。详见[早期账号隔离报告](branch-account-finding.md)。主会话已将该发现列为 Task13 的账号隔离验收项，修订及双标签浏览器证据待独立验证。

## Medium

- **模型返回不可哈希的掌握等级会中止正式续答。** `app/agents/critic.py:54–56` 在已有待答题、当前节点有效、`mastery_score` 合法时，用模型 JSON 的 `mastery_level` 直接查字符串集合。数组或对象会触发 `TypeError`。真实 `LLMService.invoke_json` 仅解析 JSON（`app/infrastructure/llm.py:168–178`），协作环不会捕获此类型错误（`app/orchestration/collab_loop.py:67`），请求由共享服务标为失败（`app/orchestration/conversation_service.py:416–437`）。有效评分应附合法等级，非法等级可不发评估事件。建议在该入口先验证等级是字符串，再按既有集合检查，并用受控 JSON 覆盖续答。该发现针对模型输出边界，当前无真实模型返回这类字段的运行记录。
- **重复题干时，模型上下文可能引用旧回合。** `app/harness/teaching_context.py:228–229` 用最新助手消息认定真实待答题，`:280–282` 却在已保留的升序历史中找第一条同文本助手消息。相同题干在不同回合重复且两条消息仍在历史预算内时，Tutor/Critic 得到旧消息引用，提交评分按最近助手消息校验并留证（`app/orchestration/turn_commit.py:204–214`）。若同题干曾用于不同节点或不同解释，提示词的引用会误导上下文定位。建议优先按已验证的 `question_message_id` 引用，引用缺失时回退到原有文本输出。

## Low

- **超长问题在正式输入框中没有发送反馈。** `web/src/components/workspace/ChatComposer.tsx:10–12` 允许粘贴超过 4000 的文本且保持发送按钮可用。点击后 `web/src/store/workspaceController.ts:712` 在生成请求或状态前直接返回。用户继续看到原文，无法判断为何未发送。本机草稿格式同样限制长度（`web/src/store/localRecovery.ts:27`），而服务端草稿写入可接收这段文本。建议显示明确的长度和错误状态并保持输入，使用与后端一致的字符计量。该问题不影响现有短答恢复主用例。
- **README 的现况与私有知识库鉴权合同冲突。** `README.md:407` 仍称 knowledge 端点无账号绑定且无需认证，Task4 段及 `app/api/knowledge.py:13–72` 要求 JWT 并按账号读写。沿旧说明调用将收到 401。建议更正现况条目，历史阶段记录可保留。

本阶段为静态审阅。实际数据库锁等待、模型回复、重启读回和浏览器 UI 以 Task13 的运行证据另行确认。历史任务证据用于交叉定位，未充作本次独立人工覆盖。
