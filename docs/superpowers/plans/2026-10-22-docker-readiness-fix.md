# Docker readiness 修复实施计划

> **For agentic workers:** Use superpowers:subagent-driven-development. 逐项执行，不重新询问用户是否继续。

**Goal:** 修复启动期HTTP断连/重置重试、期限与失败前脱敏证据。
**Architecture:** 保持verify_docker_image.py现有门禁结构，仅收敛readiness和Sandbox异常清理前诊断。
**Tech Stack:** Python标准库、pytest、固定Ruff0.17.1、GitHub Actions。
**Spec:** superpowers/docker-readiness-fix-raw.md（已批准方案的三层详细展开）

## Constraints
- 不修改业务API、镜像内容、迁移、依赖、模型配置、工作流发布门禁。
- 不使用sleep；readiness有界主动轮询，普通业务错误不隐式重试。
- 不完整inspect或dump环境；诊断脱敏、限量、不得覆盖原失败。
- 不amend；只明确git add文件。主会话负责提交、推送和main快进。

## Review focus
- 两种启动网络错误恢复后均可通过；持续错误必须到期。
- 单次请求/间隔不超剩余预算，晚到成功不被接受；不读取健康正文。
- 业务HTTP错误仍失败；异常类型不被过宽捕获吞掉。
- 诊断在清理前，诊断报错也清理且保留原失败；日志不出现密钥或完整配置。
- 远端候选pack/load的源码/镜像/归档身份链不能因修复放宽。

### Task 1: readiness与诊断的最小补丁
Files: scripts/verify_docker_image.py, tests/test_verify_docker_image.py, README.md。
- [ ] 先增加可复现的失败测试并保存red输出。
- [ ] 实现最小补丁，运行定向测试并保存green输出。
- [ ] README记述就绪等待及失败日志行为，避免声称尚未取得的远端成功。
- [ ] 独立代理审查，修复实际发现。

### Task 2: 收口与真实远端复验
- [ ] 全仓固定Ruff和默认pytest验证；git diff --check。
- [ ] 主会话明确文件提交，远端main未变化才普通快进，不force。
- [ ] 每30秒跟踪CI/Release；下载正式验收及候选身份资料，记录真实性。
- [ ] 更新执行报告、README及HTML最新状态，不以跳过教学代表可发布。
