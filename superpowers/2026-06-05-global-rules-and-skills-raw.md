# 全局 CLAUDE.md 与全局 Skill 封装 —— 规划设计文档（raw）

> 日期：2026-06-05
> 类型：brainstorming 规划产出物（raw 材料，供后续 spec 追溯）
> 状态：已经用户逐节确认，进入实施

## 一、需求来源

用户原始诉求（两次消息）：

1. 在 **Claude 全局目录**（非本项目目录）创建 `CLAUDE.md`，写入一条新规则：
   > 探索的终点不是自洽，是穷举。每次都严格基于事实（如代码、文档内容）回答问题；遇到文档没说清楚或没有事实性信息时，主动说自己不清楚或者不会，请求或直接提问获取更多信息，而不是编一个自洽的逻辑；在探索和探讨方案时，要穷举所有可能性，而不是找到自洽的逻辑就停止。
2. 将本项目 `.claude/rules/` 文件夹下的规范文档**调整成全项目可用**，并**封装成全局 skill**。

## 二、探索发现（基于事实）

### 2.1 文件系统现状

- 根目录**不存在** `CLAUDE.md`，尽管 `dev-standards.md` 开头写「本规范从全局 CLAUDE.md 同步而来」——该全局源文件实际不存在。
- 全局 `~/.claude/` 下**无任何** `CLAUDE.md`（已核验 `~/CLAUDE.md`、`~/.claude.md`、`~/.claude/CLAUDE.md`、`~/.config/claude/CLAUDE.md`、`~/.claude/memories/CLAUDE.md` 全部不存在）。
- 全局 `~/.claude/skills/` **不存在**（全新创建）。个人级 skill 即放置于此。

### 2.2 `.claude/rules/` 三文件通用性分析

| 文件 | 内容 | 通用性 |
|------|------|--------|
| dev-standards.md | 中文回答、禁 sleep 改轮询、README 维护、三层模块规划、规划产出物归档 | 基本完全通用 |
| learning-docs.md | `Learned/` 文件夹 + QA 格式学习文档机制 | 完全通用 |
| agent-root.md | StudyAgent 四层架构、薄壳节点、safe_node、@with_spec、SpecLoader、specs 双文件同步 | 高度项目专属 |

### 2.3 机制事实

- **全局 CLAUDE.md**：每次会话都加载，常驻、占上下文，always-on。
- **skill**：按需触发加载，description 决定触发时机。
- superpowers `writing-skills` 铁律：无失败测试不写 skill（针对从零设计的纪律性 skill）。

## 三、用户确认的设计决策

通过 AskUserQuestion 收集：

1. **agent-root.md 处理** → 「抽取通用理念再泛化」：丢弃 StudyAgent 专有名词，提炼跨项目原则进 skill。
2. **常驻 vs 按需分层** → 「分层：强制类常驻，流程类按需」：always-on 硬约束进 CLAUDE.md，场景触发的流程进 skill。
3. **skill 粒度** → 「按主题拆多个 skill」：单一职责，描述精准、触发更准。

## 四、最终方案

### 4.1 产出结构

```
~/.claude/
├── CLAUDE.md                          【新建·常驻】
└── skills/                            【新建·按需】
    ├── module-planning/SKILL.md
    ├── learning-docs/SKILL.md
    ├── readme-maintenance/SKILL.md
    └── layered-architecture/SKILL.md

项目 .claude/rules/ —— 原样保留不动（项目级强约束，优先于全局默认层）
```

### 4.2 全局 CLAUDE.md（常驻，3 条硬约束）

1. **探索的终点是穷举而非自洽**（新规则）：严格基于事实（代码/文档）回答；无事实依据时主动声明「不清楚/不会」并提问或请求信息，禁止编造自洽逻辑；探索方案时穷举所有可能性，不因找到一个自洽解释就停止。
2. **语言要求**：始终用中文沟通。
3. **命令执行**：禁用 `sleep` 强制等待，改用轮询（每 30 秒主动检查进展）。

理由：三者均为与具体任务无关的 always-on 硬约束，适合常驻。

### 4.3 四个 skill

| skill | 触发条件 | 内容来源 |
|-------|---------|---------|
| module-planning | 编写任何模块/功能代码前 | dev-standards「三层规划」+「规划产出物管理」 |
| learning-docs | 对话出现知识点/排查/技巧/架构决策时 | learning-docs.md 全部（QA 格式） |
| readme-maintenance | 完成一个任务后 | dev-standards「README 维护」 |
| layered-architecture | 设计/编写分层架构、多组件协作代码时 | agent-root.md 泛化 |

### 4.4 agent-root.md 泛化（丢弃专有名词后的通用原则）

提炼 3 条 + 1 附则，丢弃 `safe_node`/`@with_spec`/`SpecLoader`/`intent_map`/四层具体命名/渐进式加载体系：

1. **分层单向依赖**：系统分层后依赖只能向下流动，严禁反向依赖。
2. **编排层薄壳化**：编排/节点层只做「读状态 → 委托专门组件 → 写回状态」，业务逻辑下沉。
3. **状态写入边界**：每个组件只写自己所属命名空间，严禁跨命名空间写入。
4. 附则 **成对文件同步**：配对维护的文件（如 规范 ↔ 运行时 Prompt）改一个必须同步改另一个。

> 「渐进式加载体系」（spec 三层）过于 StudyAgent 专属，泛化价值低，丢弃，不进 skill。

## 五、取舍点（用户已确认 "可以"）

1. **项目 `.claude/rules/` 原样保留**：项目级强约束（agent-root 必须留），项目版本更具体、优先于全局默认层。纯增量、零破坏。
2. **跳过 skill 的完整 TDD 压力测试**：本任务是搬运项目中已验证的规范，非从零设计纪律性 skill。改为写完后轻量验证（子代理读 skill 确认能否正确理解触发与执行）。

## 六、实施顺序

1. 归档本设计文档到 `superpowers/`（当前步骤）。
2. 创建 `~/.claude/CLAUDE.md`（3 条）。
3. 创建 4 个 skill 的 `SKILL.md`。
4. 轻量验证：子代理读 skill 校验触发与执行；确认 CLAUDE.md 可被加载。
