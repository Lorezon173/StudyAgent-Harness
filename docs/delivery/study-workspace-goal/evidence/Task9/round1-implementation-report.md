# Task9 实现交接报告

状态：实现与作者自测完成；**全部 web 源码（含测试、package 与配置）已冻结，等待主会话派发独立代码审查**。未提交、未推送、未部署。README、asset 与任务账本由主会话维护，本实现者未修改。

## 基线与冻结

- 唯一实施计划：`docs/superpowers/plans/2026-10-25-task9-round1.md` v1.3，SHA256 `cdf536584f59bd678c877f2343bad075173ad1da2f1db0e914fc397a45433758`。
- 视觉基准：`docs/designs/frontend-paper-study.html`，SHA256 `9edc828d7a2d7bdb40c0b5fd6d254250c932e754f1dd2723425d8d73beabb91b`。执行前、作者自查及最终验证均核对一致；未修改终稿或复制演示数据。
- 实施 HEAD：`c91b60b54f035231dc7d35dc79fc01e3df641028`；分支 `codex/frontend-ui-optimization`。后端 Task8 冻结实现来自 `c23763d4fa0f2dfb951c4c65ef3670af4ac41d4e`，本轮未修改后端。
- 最终冻结清单：`docs/delivery/study-workspace-goal/evidence/Task9/source-freeze.json`，记录 **38 个 web 文件**、验证前后相同 SHA、HEAD、分支、计划/终稿 SHA、测试摘要与各检查退出码。
- 本轮产品/测试修改共 30 个 web 文件：14 个已跟踪文件修改、16 个新增文件。完整状态见 `final-web-status.log`；未跟踪文件已纳入冻结清单，不能只看 `git diff` 忽略它们。

## 结果与需求映射

最终命令均已实际执行并读取输出：

| 命令 | 实际结果 | 证据（均位于 Task9 evidence 目录） |
|---|---|---|
| `npm.cmd --prefix web test` | 8 文件、62/62，通过；7.77 秒；exit 0 | `final-test.log` |
| `npm.cmd --prefix web run build` | TypeScript 与 Vite 均通过；210 模块；Vite 1.90 秒；exit 0 | `final-build.log` |
| `git diff --check -- web` | 无空白错误；exit 0 | `final-diff-check.log` |
| 对全部 38 个 web 文件验证前后计算 SHA256 | 完全一致 | `source-freeze.json` |
| 核对计划与终稿 SHA256 | 均与冻结值一致 | `source-freeze.json` |

| 需求 | 对应测试/核对 | 最终结果 |
|---|---|---|
| 保留原 GET/POST/ApiError；PATCH JSON、FormData 边界、结构化 409/422、204、非法 JSON、网络/超时、traceback 屏蔽 | `api/client.test.ts`，12 项 | PASS |
| 当前 401 统一失效；旧账号/同凭证旧代际 401 不清新认证、不跳新 URL；无 Provider 兼容清理及跳转 | client、`store/auth.test.tsx`；真实 Provider 与延迟 fetch | PASS |
| 首次挂载同步 bootstrap 先于子树请求；StrictMode 同身份幂等；显式同 id/同 token 登录仍强制换代；退出清缓存 | auth 5 项；WorkspaceLayout 刷新/重登录请求票据 | PASS |
| A/B 会话桶独立、保留草稿；晚响应归原桶；同桶旧 load/request 丢弃；账号换代清桶；未知桶不自动写入；特殊 URL 键不读对象原型 | `store/workspace.test.ts`，7 项 | PASS |
| 根分页与各组分页 cursor/sequence/loading/error 独立；同名不同画像不合并；去重、不重排；失败保留数据与游标；根重复页不复活已耗尽 null 游标 | store、`SessionSidebar.test.tsx` 3 项、API query 测试 | PASS |
| grouped/listGroupSessions 的真实 query、目标组解包与画像身份核验；缺失/异常页返回 ApiError；路径编码、POST/PATCH body 对齐真实契约 | `api/workspace.test.ts`，6 项 | PASS |
| 左栏只有主题会话与底部账号，右上知识库/画像；四路由公共 navigation 唯一；默认固定展开、手动收起取消固定、固定展开、选中不收起 | `WorkspaceLayout.test.tsx`，12 项 | PASS |
| 481/760 为独立桌面侧栏；≤480 为抽屉；移动选中保持打开，Escape/遮罩关闭不改变桌面固定偏好 | Layout DOM 状态断言；CSS 为桌面 264px、481–760 为 170px、topbar 75px | DOM/CSS 核对 PASS；真实几何视觉待 Task12 |
| 真实本人主题选项、显式加载更多、伪造 id 拒绝、服务端 403、两 POST 顺序和中间身份屏障、部分成功绑定锁定/重试复用/显式重选、双提交、迟到结果丢弃 | `NewSessionDialog.test.tsx`，7 项 | PASS |
| URL 是选择真源；编码 id 解码后高亮；返回 `/chat` 清高亮，历史回退重选；不加载 snapshot；旧 Chat 回复与 composer 不冒充选中会话 | Layout、NewSessionDialog | PASS |
| 原生 dialog cancel 关闭及回焦新建按钮；无假回复或分数 | NewSessionDialog；API 只返回真实 id 后 upsert | DOM PASS；原生浏览器行为待 Task12 |
| 用户名/密码与两个原认证端点保留；Login 本地 mount epoch/submit sequence/account generation 栅栏；同步 busyRef；正常成功、失败可重试与旧页面迟到成功/401/忙状态隔离 | `pages/Login.test.tsx`，10 项，真实 Provider/MemoryRouter/延迟 fetch/StrictMode | PASS |
| Knowledge/Profile 仅去重复 nav 与无用 Link，保留业务；Chat 仅拆公共壳/新建/账号导航并保留原 `/chat` send | 两页 diff 各只删除 4 行；Layout 四路由与旧回复隔离测试；构建 | PASS |

## 红绿过程及证据口径

以下日志均在 `docs/delivery/study-workspace-goal/evidence/Task9/`。不把环境加载错误或尚未执行到的分支冒充业务失败。

1. `9.1-red.log`：6 failed / 3 passed。真实已有行为红灯是结构化错误文字、204、原认证 401 文字；其余是新 helper/module 契约缺失。新模块缺失时分页分支尚未执行，不宣称已复现游标混用。随后 `9.1-green.log` 为 9/9。
2. 最小依赖普通安装因 npm 仓库 DNS `ENOTFOUND` 失败（`dom-install.log`），未开始相应测试；仅一次走原生审批通道重试成功（`dom-install-escalated.log`）。RTL16 的必需 peer `@testing-library/dom` 未自动安装，首个 `9.2-red.log` 的 auth suite 因此未收集，不计为业务红灯。补 peer 后 `9.2-red-ready.log` 为 9 failed / 11 passed：4 项 store 接口缺失，5 项真实 auth 行为失败。实现后 `9.2-green.log` 为 23/23。
3. `9.3-9.4-red.log`：27 failed / 9 passed。Login 确实同拍发 2 次 POST，旧 A 成功确实把 B 改成 `1:A`；两个 store 回归确实得到 `stale` 游标及继承属性。新建 7 场景首先停在新入口缺失，其后置 POST 分支在实现后的绿灯中才执行验证。纸感壳与新建组件相互引用，经主会话裁决合批 DOM 先红再联通，没有缩减验收。`9.3-9.4-green.log` 全量为 54/54，`9.5-build.log` 构建通过。
4. `self-check-red.log`：1 failed / 24 passed，唯一红灯为 HTTP200 null 分组页抛 TypeError。此时 URL 解码、历史回退、遮罩及账号退出补证已通过。
5. `self-check-errors-red.log`：2 failed / 25 passed，真实红灯为 traceback 文本被直接展示及上述 null 页 TypeError；Login 两端点凭证 401 不换代、可重试及旧 A 401 不影响 B busy 等 10 项通过。
6. 按明确根因加入数组结构检查和错误文字屏蔽，再补无 Provider 401 清理/旧 401 URL 对照；最终 `final-test.log` 为 62/62，`final-build.log` 与 `final-diff-check.log` exit 0，最终前后全源 SHA 相同。此后不再追加产品或测试改动。

实际分组命令：

```text
npm.cmd --prefix web test -- src/api/client.test.ts src/api/workspace.test.ts
npm.cmd --prefix web test -- src/store/workspace.test.ts src/store/auth.test.tsx src/api/client.test.ts
npm.cmd --prefix web test -- src/store/workspace.test.ts src/store/auth.test.tsx src/api/client.test.ts src/api/workspace.test.ts
npm.cmd --prefix web test -- src/store/workspace.test.ts src/components/workspace/WorkspaceLayout.test.tsx src/components/workspace/SessionSidebar.test.tsx src/components/workspace/NewSessionDialog.test.tsx src/pages/Login.test.tsx
npm.cmd --prefix web test -- src/api/workspace.test.ts src/components/workspace/WorkspaceLayout.test.tsx src/components/workspace/NewSessionDialog.test.tsx
npm.cmd --prefix web test -- src/api/client.test.ts src/api/workspace.test.ts src/pages/Login.test.tsx
npm.cmd --prefix web test
npm.cmd --prefix web run build
git diff --check -- web
```

## 真实 DTO 与设计细化

已直接读取 `app/models/workspace_schemas.py`、`app/models/schemas.py` 及 sessions/topic_profiles/workspace/knowledge 路由；未按未落地计划猜字段。

| 服务端契约 | 前端落实 |
|---|---|
| ProfilePage：`items/next_cursor`；ProfileDetail：`profile/profile_revision/nodes/edges` | 新建从 `detail.profile.id` 取 id，绝不读 `detail.id`；ProfileItem/Node/Edge/Evidence/Summary 与 create/patch/node mutation 类型按实际字段定义 |
| GroupedSessions：`groups/next_group_cursor`；组：`group_key/profile/summary/sessions/next_session_cursor` | 根 `cursor` 与组内 `group_key/session_cursor` 互斥请求；组内响应仍为 GroupedSessions，解包前核目标组和 profile id；unassigned 要求 profile=null |
| WorkspaceSession：稳定 `session_id`，可空 user/profile/node/request id 及时间，state_version/next_turn_index | 不以标题作键，不生成本地成功 session；新建只发送 profile_id/title/active_node_id=null |
| ViewState/WorkspaceState 与 patch 的独立版本空间 | ViewPatch/WorkspacePatch 用 expected_version；ActiveNodePatch/ChatRequest 用 expected_state_version；本轮只提供薄 API，不调用恢复/保存控制器 |
| SessionSnapshot、MessagePage、RequestSnapshot、RetryRequest | 字段、路径及请求 body 对齐实际 schema/路由；页面未接 snapshot/messages/request/retry |
| Task8 ChatRequest/ChatResponse | 对齐实际可选 request_id/profile_id/expected_state_version 和响应 status/attempt/version/error/context 字段；mastery 等可空数值保留 null，日期保留 ISO 字符串 |
| LibraryItem/Create/Update 与知识库路由 | id/user_id 为 number，profile_id 可空；内容、source_type 与时间字段保留；仅新增薄 API，旧页业务未重构 |

实施细化/主会话裁决：

- 唯一账号时钟位于 workspace 单例。bootstrap 按 id+token 幂等；显式 login 即使 id/token 相同也强制 generation+1；client/AuthProvider 共用票据，未新增第二个全局认证计数器。
- Login 的本地 mount epoch、submit sequence 与 busyRef 仅约束本页续体。成功顺序为核票据、清 error/busy、同步 login 换代、无 await navigate；过期 success/catch/finally 均无副作用。
- **仅** `/api/auth/login`、`/api/auth/register` 的 401 按凭证失败交页面反馈，不失效当前账号；否则会使 v1.3 的正常失败票据过期并吞掉反馈。受保护 API 当前 401 仍统一换代退出，旧完整票据不得清新认证。两端点不换代与受保护 401 换代均有测试对照。
- App 以账号 generation 为受保护壳的 key，使原 Chat/Knowledge/Profile 的局部状态在换账号后卸载，避免旧页面迟到结果回填新账号；未重写它们的业务控制器。
- DOM 依赖保持本地 devDependency：jsdom `^24.1.3`、RTL `^16.3.3` 及其必需 DOM peer `^10.4.2`。保留默认 node 环境，各 DOM 文件首行显式 jsdom；未装 Playwright、UI 框架、字体或图标库，未运行 audit-fix。

## 文件清单

```text
web/package.json
web/package-lock.json
web/vite.config.ts
web/src/App.tsx
web/src/index.css
web/src/types.ts
web/src/api/client.ts
web/src/api/client.test.ts
web/src/api/sessions.ts
web/src/api/profiles.ts
web/src/api/knowledge.ts
web/src/api/workspace.ts
web/src/api/workspace.test.ts
web/src/store/auth.tsx
web/src/store/auth.test.tsx
web/src/store/workspace.ts
web/src/store/workspace.test.ts
web/src/components/Sidebar.tsx
web/src/components/workspace/WorkspaceLayout.tsx
web/src/components/workspace/WorkspaceLayout.test.tsx
web/src/components/workspace/SessionSidebar.tsx
web/src/components/workspace/SessionSidebar.test.tsx
web/src/components/workspace/NewSessionDialog.tsx
web/src/components/workspace/NewSessionDialog.test.tsx
web/src/pages/Login.tsx
web/src/pages/Login.test.tsx
web/src/pages/Chat.tsx
web/src/pages/Knowledge.tsx
web/src/pages/Profile.tsx
web/src/test/setup.ts
```

## 未验收边界与后续交接

- `/chat/:sessionId` 仅同步选择与高亮，显示“此会话的内容暂不可用”，不加载历史、不提供会使用旧 local session 的 composer；`/chat` 保留原教学发送入口。不能称为真实恢复/发送已接入。
- Task10 仍负责 last_session、snapshot/messages、教学发送/请求恢复、500ms 草稿防抖、阅读锚点及正常退出 flush。本轮普通退出不承诺保存成功；client 的原 120 秒超时未擅自改为后端 300 秒预算。
- Task11 负责知识库/画像内容重构与真实 summary 映射；两旧页的业务和既有占位内容仍保留。Task12 负责浮动画像、拖动以及真实浏览器/视口/像素视觉验收，本轮未创建假画像卡或分数。
- 新画像与会话是两个真实独立 POST，不能宣称原子事务；部分成功会保留当前表单的真实主题绑定，关闭/换账号清本地绑定，显式重选不会删除已创建画像。
- 所有前端测试通过最下游 fetch mock；dialog polyfill 只实现 showModal/close 属性语义。没有真人 JWT、真实后端/模型/数据库写入、PostgreSQL 重启或公网部署验收，也未证明真实浏览器几何、原生焦点陷阱或像素效果。
- 原 README/asset 与其他用户未提交文件未动。独立审查、README/账本更新、明确文件 git add/提交仍由主会话执行；本报告不表示独立 review PASS。
