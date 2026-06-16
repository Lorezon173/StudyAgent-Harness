# 多会话并发开发 — Git 协作踩坑

> 最后更新：2026-06-03

## 目录

- [Q1: 多个 Claude 会话共享同一工作树并发开发，提交时如何避免互相污染？](#q1-多个-claude-会话共享同一工作树并发开发提交时如何避免互相污染)

---

## Q1: 多个 Claude 会话共享同一工作树并发开发，提交时如何避免互相污染？

**日期**：2026-06-03

**问题**：
`feat/multi-agent-redesign` 分支由多个会话（Plan C/D/E + `app/agent`→`app_old` 迁移）**共享同一工作树和同一 HEAD** 并发开发。期间发生两起 git 污染事故，导致 commit 内容/归属错乱。

**回答**：

两起事故（两种失败模式）：

1. **`git add -A` 裹挟他人暂存改动**
   Plan E 一个子 Agent 跑 `git commit` 时，把另一会话已 `git mv` 暂存的 94 个迁移文件一起提交（commit `d075279`），盖错了 commit message。

2. **`git commit --amend` 撞上并发推进的 HEAD**
   Plan D Task 4 一个子 Agent 想 `--amend` 修订自己刚才的提交，但那一刻 HEAD 已被并发的 Plan E 会话推进到 `376da3d`（ComponentBench）。amend 改到了**别人的 commit** 上，把 Plan D 的 assembly 改动混进 message 为 `feat(plan-e)` 的提交，因后续提交已叠加而无法安全 un-bundle。

**根因**：
- 共享工作树 → git index 里常驻其他会话在途（未提交/已暂存）改动；
- 共享 HEAD → HEAD 随时被其他会话的新提交推进，`amend`/`reset` 等改写操作会作用到错误的目标。

**规避规则**：
- 只 `git add <自己明确的文件/目录>`；**严禁** `git add -A` / `git add .` / `git commit -a`。
- **严禁 `git commit --amend`**（HEAD 可能已被他人推进）；要修订就追加一个新的普通 commit。
- 每次提交后立即 `git show --stat HEAD` 自验**只含自己的文件**，发现混入立即停手、勿继续叠加。
- 全量 `pytest` 会受其他会话在途改动影响；自测优先 scope 到自己的测试目录，全量回归只用于确认"未新增失败"。
- 根治方向：多会话应各用 `git worktree` 隔离独立工作树，而非共享同一工作树。
