# Task12 最小验收补充 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 superpowers:subagent-driven-development，先由独立子代理审阅本计划，再编码；以复选框记录执行结果。此文仅补足原批准验收，不引入产品机制，不代表验收已经通过。

**Goal:** 补齐账号偏好真实重登、新尺寸恢复、B 写后再回 A、深链 reload，以及同账号切会话保留比例/草稿/阅读锚点的行为证据。

**Architecture:** 保留正式 React HTTP 页面与现有 Playwright 配置；真实账号闭环只使用现有认证、workspace、profile、session API，不拦截其响应。需要可滚动消息的双会话回归使用明确标注的受控 API fixture，验证浏览器行为与请求副作用，不声称真实消息持久化。

**Tech Stack:** 现有 React18、TypeScript、@playwright/test 1.64.1、系统 Chromium 浏览器、既有隔离 FastAPI 后端。

**Spec:** 原始设计 [Task12 raw](../../../../../superpowers/frontend-ui/2026-11-04-task12-round1-raw.md)，对应执行计划 [Task12 round1](../../../../superpowers/plans/2026-11-04-task12-round1.md)，实施状态 [handoff](round1-implementation-handoff.md)。本计划的需求均来自 raw 的“验收与交接”和 round1 Task D，不增写新 spec。

## Global Constraints

- 本文生成日期：2026-11-04；已读 AGENTS.md、CLAUDE.md、上述 raw/plan/handoff、完整 workspace-layout.spec.ts 和 playwright.config.ts，并核对 Chat.tsx 的锚点渲染/恢复合同。
- 主会话已准备隔离后端 `TASK12_ISOLATED_API=http://127.0.0.1:52161`，环境记录见 [isolated-environment-preparation.md](isolated-environment-preparation.md)；实际执行前核服务身份与健康，不把环境准备当行为验收。
- 当前仅有全量 423 项单元测试、build 通过及 21 项 Playwright 收集记录；没有据此宣称任何浏览器功能通过。原 19 项产品/测试/配置文件处于冻结审阅中，后续写测试前重新记录哈希，不能并发修改冻结文件。
- 实际产品入口为认证工作区 `/chat/:sessionId`、`/profile`、`/knowledge`。真实组不得伪造 localStorage 登录或 route.fulfill；受控组沿用现有标注，不跨越为真实持久化结论。
- 仅修改既有 `web/e2e/workspace-layout.spec.ts` 的验收和局部 fixture；配置默认不变。若必须改变配置，先说明确切阻塞及最小差异。无后端、迁移、模型调用、PG 重启、Task13、部署或全局设置变更。
- 保留旧断言；不把失败改成降级期待，不删除 403 检查，不通过直接调用产品 store/handler 代替用户交互。
- README、任务账本与最终证据汇总由主会话串行维护；本文编写者不改这些文件，不提交。本计划无代码片段；计划独立审阅通过前不编码。

## Review Focus

1. 服务端仍有 A 的 ratio，不等于重登后 DOM 使用该 ratio；补充新尺寸的可见位置断言。
2. B 默认不等于 B 写入不会污染 A；补充 B 保存、退出、再回 A 的闭环。
3. `goto` 深链不等于显式 reload 验收；补充每页 reload、GET 应用、无 PATCH 和 URL 稳定。
4. 单会话输入值不变不等于切换后草稿/锚点保留；补充双会话及可滚动历史。
5. 切会话合法的 snapshot GET 与浮卡交互额外 GET 必须分段计数，避免错误要求切换零请求或漏报交互副作用。

## 第一层：模块总览与完成条件

本次改变的是验收覆盖，不改变产品行为。当前已证实的缺口是“缺测试/未执行”，尚无足够证据认定产品功能失败。

完成条件：原有浏览器用例获得实际运行结果；以下三类补充行为有断言和证据，真实组不 skip 才能计为真实通过。若隔离后端不可用，记录阻塞并保留真实组未验；受控组通过不能替代。核心行为失败时先报告触发、实际状态及最小修复需求，不自动修改产品或扩大范围。

| 原用例范围 | 已写断言（尚待运行） | 本次必要补充 |
|---|---|---|
| 14 个宽高组合 | 收展两态 rect、输入可见、页面横溢、桌面栏宽/收起释放、移动抽屉等 | 先运行，不新增长内容/键盘/缩放的全部组合 |
| hover、指针/键盘、touch、resize | 连续 hover、Escape 再入、4px、capture、350ms、ArrowDown、请求数、触屏开关/拖动、resize 不写 ratio | 保留；合成 pointercancel 仅是注入事件验证，不标为真实 OS 取消；CDP touch 是浏览器输入模拟 |
| 短高 200%/reduced-motion/modal | 字号设置、边界、overflowY 为 auto、原生 dialog 为 modal | 不声称已证明内容实际滚完、所有操作可达或所有动效消失；先运行，实际失败再定位 |
| 真实 A/B 用例 | 注册/登录、A 拖动服务端读回、sidebar 收起读回、goto 两深链无 PATCH、A 重登后服务端 ratio 相等、B 默认 ratio、B 读 A snapshot 为 403 | 补 A 新尺寸 DOM 恢复、sidebar 重登恢复、B 写后回 A、显式 reload 的 GET/不导航合同 |
| 单会话 fixture | 一条消息、null anchor、草稿未变化 | 补双会话比例、非空 anchor、不同草稿、分段请求数 |

## 第二层：子场景合同、数据流与错误处理

### A. 真实 HTTP 账号偏好闭环（扩展现有真实用例）

输入为显式 `TASK12_ISOLATED_API` 本机隔离后端、唯一 A/B 账号、独立主题及会话。保持 UI 登录/退出，API 注册和准备主题/会话可沿用现有 helper；request fixture 经前端 4178 代理到配置后端，不能误把 baseURL 当后端直连。记录实际后端地址与本轮源码/构建身份，不写密码、token、Authorization。

数据流为 A UI 拖动/收栏 → workspace PATCH 成功 → 独立认证 GET 确认三偏好和 version → 切为 390×844 → 正式“打开会话导航”按钮打开移动抽屉 → 账号菜单正常退出 → 改为 1024×900 → A UI 重登 → 正式 Chat DOM 恢复 → B UI 登录检查默认 → B UI 改位置并保存不同值 → B 退出 → A 登录确认原值和 DOM。A 初始用 1440×900，选择非默认且远离端点的 ratio；B 选择与 A 明确可分辨的 ratio，不以“拖动了固定像素”推定成功。

断言服务端 `sidebar_pinned=false`、`sidebar_collapsed=true`、有限 `progress_y_ratio`。首次退出仅通过移动抽屉路径，打开抽屉只改变局部 mobileOpen；在抽屉已开、退出前和正常退出完成后，使用 A 的隔离认证 GET 确认三偏好仍等于保存基线。退出仍走正式保存等待，不强制点击隐藏按钮、不调用内部 store、不篡改认证。随后 1024×900 重登，先验证 collapsed=true 的收起 DOM 和 ratio 映射，再为观察菜单展开；桌面展开展示属于新的真实偏好写入，必须等待确认并将此时 A 确认值作为后续 A/B 隔离基线，不拿旧 collapsed=true 错判。B 默认三字段为 true/false/0.5，且主题/会话属于 B；B 保存后再 A 仍为 A 的最新确认三字段，B 不能读取 A snapshot 的 403 断言保留。

每次保存以响应/读回及 UI 状态为准；请求失败记录状态码与脱敏响应，不能仅等待 ratio 不等于 0.5。重登后用真实 rect 验证比例映射而非仅 GET；新尺寸不是要求旧绝对像素一致。

### B. 真实 HTTP 深链显式 reload（沿用 A 已保存偏好）

每个 `/profile`、`/knowledge` 从已确认的 A 收起/未固定/非默认 ratio 开始。先进入，再开启独立请求观察窗口并 `reload`；等待本次 workspace GET 完成和 sidebar 应用。URL 保持对应页，不跳 Chat、不主动选择最近会话；本窗口 workspace PATCH 为零。记录 GET 三偏好和浏览器收栏状态，再进入 A Chat，验证卡片位置符合缓存的 ratio；进入 Chat 的正常会话选择写入另设观察窗口，不混进深链无 PATCH 断言。

本场景证明真实后端 GET 的 UI 应用；Layout/Chat 初始化恰好一个同代并发 GET、晚响应门禁仍由已有受控单测证明，不把顺序 reload 冒称竞态复现。错误时保留 URL、GET/PATCH 清单和截图，先排查初始化请求是否完成；不得用固定 sleep 或短时间无请求就宣称零 PATCH。

### C. 受控双会话浏览器回归（新增一个独立测试）

扩展局部 fixture 为同账号 s1/s2，独立 snapshot、draft、reading_anchor、view version 和消息集合；两者 profile/session owner 和 revision 有效。s1 多条稳定 id、足够高度的消息，使中段锚点可恢复且远离首尾夹取；s2 不同草稿与消息。workspace prefs 仍是一份账号级 state，view-state 为按 sessionId 索引的 Map，不让 s2 保存覆盖 s1。

数据流：加载 s1 → 输入唯一草稿 → 真正滚动消息容器产生非空 anchor 并等 view-state 确认 → 记录 DOM 相对位置 → 浮卡 hover/收展、拖动、键盘操作 → 比较草稿与锚点 → 侧栏按钮切 s2 → 检查同账号 ratio、s2 自有草稿/消息 → 再切 s1 → 检查草稿和中段阅读位置恢复。切换通过正式导航按钮，允许其必要 snapshot/messages GET；交互窗口中不允许这些 GET 增量。不要调用内部 store 构造“已恢复”。

fixture 仅响应现有支持的 API，未知路径仍 404；每个 view PATCH 校验 expected_version 并回写独立会话状态。fixture 故障与产品失败分开记录，不能通过恒返回最新草稿伪造持久化。此项结论仅为受控 HTTP 浏览器会话切换回归，不代表真实教学消息、数据库重启或真实后端草稿持久化验收。

## 第三层：函数、字段及断言的文字实施计划

### 任务 1：局部观测与真实账号用例补强

**文件：** 仅 `web/e2e/workspace-layout.spec.ts`；重用现有 trigger/handle/rect/checkBounds 和 createAccount/login，helper 保持文件局部，不建公共测试框架。

- [ ] `observeWorkspaceWindow(page)`：输入 Page；输出仅记录 workspace GET/PATCH 的观察器及停止函数。字段包含 method、pathname、status、三偏好、version、phase；监听在动作前安装，在确定相关 GET/保存完成且 UI 稳定后停止并解除监听。请求失败也保留，凭证不入日志。
- [ ] `readWorkspace(request, identity)`：输入现有 request fixture 和已注册身份的认证头；输出经状态码、布尔字段、有限 0–1 ratio、整数 version 检查的 workspace 值。用于 expect.poll 观察真实提交完成，失败输出脱敏错误，不能把非 2xx JSON 当状态。
- [ ] `assertFloatingRatio(page, expectedRatio)`：输入 Page 和 GET 确认比例；输出卡片/host/topbar/composer rect 及断言结果。先使卡片处于明确的收缩状态、鼠标离开且焦点在卡外；根据真实外高计算安全顶部=max(host.top, topbar.bottom)+8、安全底部=min(host.bottom, composer.top)-8、travel=max(0,安全底部-安全顶部-card.height)，断言 card.top≈安全顶部+ratio×travel，容差 2px，且原 checkBounds 通过。travel 必须大于零才可证明非默认比例恢复，零 travel 只说明夹取，不算恢复证据。仅浏览器测量，不导入产品 ratioToTop 作为测试预言。
- [ ] 扩展原 `A 保存并重登、B 隔离和深链恢复`：输入 A/B 隔离身份和两套 session；输出上述 A→A 新尺寸→B 默认→B 保存→A 的真实闭环。A 保存 collapsed=true 后固定三偏好快照，改 390×844 并用正式移动抽屉打开账号正常退出；抽屉打开后、退出前及退出后 GET 三字段均等于快照，再以 1024×900 重登检查收起 DOM 与 ratio。之后任何桌面菜单展开导致 collapsed=false 时，等待保存并更新确认基线；B 后 A 比对最新确认快照。保留原 403，加入账号/主题归属可见断言和 DOM ratio 断言。
- [ ] 将原深链循环补为明确 reload 场景：各页监听本次 GET、零 workspace PATCH、URL 稳定、收起状态，再回 Chat 检查 ratio。若菜单操作展开了 sidebar，先重新 UI 收起并等确认，再建立深链基线。
- [ ] 将 `preferences-before/after`、几何、视口、路由、请求 phase、截图附到 testInfo；不得记录 identity 的完整对象。无需为此新增自定义 reporter。

### 任务 2：最小双会话 fixture 与回归用例

**文件：** 同上，保留现有单会话用例输出；可增加可选局部 fixture 参数或独立小 helper，不能把全部 14 组矩阵改成多会话。

- [ ] `controlledSessions(page, seeds)`：输入同账号两会话 seed；输出 calls、getWorkspace、getViewState(sessionId)。seed 字段为 session/profile/summary/messages、draft、reading_anchor、version；消息 id 在会话内稳定，初始 next_cursor=null 避免把分页问题带入本次场景。workspace 与每会话 view 状态分开保存；路由按精确 sessionId 选择数据，PATCH 逐版本确认。
- [ ] `captureReadingPosition(page)`：输入 Page；从现有 `[data-message-id]` 的可滚动父容器取 scrollTop、clientHeight、scrollHeight、首个可见 message_id、该消息相对容器顶偏移/offset_ratio；输出观测值。用真实滚动建立非空锚点，等 fixture 收到且确认 view PATCH 后捕获基线。避免底部位置，防止浏览器合法夹取造成错误判断。
- [ ] 新测试名为“受控 API · 同账号切会话保留比例草稿与阅读位置，浮卡交互不重取消息”。输入双会话 seed，输出 s1→s2→s1 行为结果。s1 草稿为新唯一文本；确认发送按钮未点击、无教学 POST；hover/拖动/键盘前后草稿完全相等、确认 anchor message_id 相同、offset_ratio 容差 0.02、DOM 对应位置容差 2px。交互改变开合时先回到同一收缩状态再比较几何。
- [ ] 按“s1就绪 / s1浮卡交互 / 切s2就绪 / s2浮卡交互 / 返回s1就绪”分段记录 snapshot/messages GET。交互段 GET 增量为零；切换段允许受支持加载，不武断要求总数为零。同账号两会话用各自 rect 和共同 ratio 验证位置；不得要求不同内容高度时绝对 top 相等。
- [ ] s2 初始显示其自身草稿/消息，回 s1 显示其新草稿且非空锚点恢复；侧栏固定/展开状态不因切会话自动改变。记录 fixture 的 view-state 回写和 DOM 观测，两者都满足才判通过。

## 执行顺序与失败诊断

1. 独立子代理审阅本计划的来源、三层设计和范围，主会话裁决后才编码。补验编码同时要求原 21 项执行到终态及本计划独立复审 PASS；冻结 OCR 期间不得改同一测试文件。
2. 不改测试，先运行原现有 21 项：`npm.cmd --prefix web run e2e`。无隔离后端时真实组会 skip，明确记为 20 项受控执行范围而非完整验收；保留每项实际状态，collect 不算运行。发现阻塞先区分浏览器启动/端口/代理/环境与产品断言。
3. 配置隔离后端并检查健康、注册和现有 API 可用；不得在用户现用库造测试数据。配置仅启动 Vite，不自动启动后端，需单独记录隔离后端启动方式/数据库类型与服务身份。真实用例禁止静默 skip；后端不可用则保留未验，不转 route mock 通过。
4. 在原有用例已执行结果基础上实现任务 1 和任务 2，先运行各定向用例到终态，再完整 e2e。建议真实组过滤 `--grep "真实 HTTP"`，双会话组过滤 `--grep "同账号切会话"`；均由 `npm.cmd --prefix web run e2e --` 传参。长命令按 30 秒主动轮询，不 sleep，不并发争用 4178。
5. 新增验收测试在当前实现可能直接通过；这属于补覆盖，不伪造行为 RED。若失败，先保留失败现场，定位 fixture 的 owner/revision/version、锚点空间、等待时点、真实保存结果；只有真实受支持路径可复现时才报告产品缺陷。更改旧断言前必须证明原合同已获批准改变。
6. 若产品失败，先列触发/代码证据/用户影响/是否本轮引入/与核心完成条件关系/最小方案；独立审查意见不是自动修复任务。需要改产品或范围时由主会话按既有确认边界处理，本补充计划不授权新增机制。
7. 原矩阵、短高、键盘、touch 等先按已有断言执行；针对实际失败最小定位，不把所有行为乘以 14 视口，不扩展模型教学或 PG 重启。合成 cancel、受控 API、真实 API 各自标注，不能互相替代。
8. 测试/配置有改动后运行完整 web test/build 与受影响独立审查；保存文件哈希、命令、退出码、执行/失败/skip 数、实际视口及未验项。主会话再同步 README/账本；未通过核心闭环不得宣布 Task12 完成。

## 自检与交接状态

原 raw 的真实偏好闭环映射任务 1，深链映射任务 1，跨会话/副作用映射任务 2；原交互矩阵保留并先执行。本计划不补新产品协议，不触碰 Task13。当前状态：计划待独立审阅；未编码、未执行浏览器验收。
