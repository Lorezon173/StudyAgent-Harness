# Task10 A 真实浏览器受控交错设施 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development 或 superpowers:executing-plans 逐任务实施。A 已获用户批准，本文件只补 A 任务1既定验收设施；当前仅规划，待独立计划审阅PASS，不表示已安装/执行。

**Goal:** 在系统真实浏览器中，经实际发送和重查按钮补齐已有inconsistent双重查及必要对照证据。

**Architecture:** 单文件验收脚本提供隔离静态HTTP入口，临时playwright-core驱动自有系统浏览器实例，通过context.route有限门闩安排A/B响应。无后端代理、控制API、用户数据库或产品修改。

**Tech Stack:** 现有Node、web构建产物、系统Chrome/Edge；临时目录内固定版本playwright-core。

**Spec:** `superpowers/frontend-ui/2026-11-03-task10-a-browser-controlled-raw.md`；继承 `2026-11-02-task10-goal-recovery-minimal-raw.md` 及配套A计划任务1、5。

## Global Constraints

- 只新增验收脚本`docs/delivery/study-workspace-goal/evidence/Task10/goal-recovery-minimal/a-browser-controlled.cjs`，本轮证据写其下`browser-controlled/<run-id>/`。
- 临时工具目录为`.superpowers/runtime/task10-browser/<run-id>/tool/`；创建新目录，不覆盖已有run，不修改产品package/lock、Python依赖或全局npm配置。web/dist仅由现有build生成。
- 系统浏览器独立非持久context，不接用户窗口、不用用户profile；仅访问自有loopback origin，未知API/外网阻断并报错。
- 不改产品、测试、acceptance_harness.py，不启动既有后端、模型、数据库或服务。根README由主会话集中同步设施状态与未验收项。
- 不替换fetch、不调用内部store/controller制造状态；认证/候选仅使用本context的合成localStorage及现有格式。
- 不宣称当前桌面浏览器工具能网络拦截；Playwright官方能力须在本工具环境实际探针验证。
- 日志、截图、相对网络时序、精确测试副本及退出码保留；不记录认证token、密码、模型配置、真实用户原文。
- 有限条件等待和响应门闩，无sleep；耗时命令每30秒主动检查进度。平台故障遵守项目每动作最多重试一次规则。
- 任何产品依赖、新API、浏览器下载/系统配置或产品修复均先列范围决策，禁止自动扩展。

## Review Focus

1. StrictMode重复初始化GET不能误分配A/B阶段；任务1使用阶段和请求到达事件证明。
2. 未拦截API不能经Vite默认proxy触及8000；任务1静态服务无proxy且未知网络失败。
3. 初始inconsistent必须来自实际发送/消息矛盾，连续两次必须为真实按钮；任务2逐阶段截图与网络证据。
4. 保留本人及另一writer精确副本和原文，禁止只检查“存在某副本”；任务2保存键值前后对照。
5. source变化不是可信冲突，不能以相邻fixture冒充已有inconsistent组合；任务2单列组合可达性与结果。

---

## 第一层：设施目标与验收边界

现有web仅有Vitest/jsdom，`web/vite.config.ts`默认node环境，Chat测试通过文件头选择jsdom；不能证明真实浏览器。现有隔离Python辅助只支持保存503/回包丢失，不能安排消息页顺序。最小补充使用一个验收脚本，没有通用故障模块。

本次目标是实际按钮交错证据，产品用户可见行为仍由A已批准的局部合同定义。脚本的所有API响应为测试合成；fixture persisted=true并非保存证明。A任务5真实模型/正常退出/慢生成/真实故障/PG重启/跨账号验收仍未完成。

## 第二层：子模块及接口

函数详细字段、输入输出、错误策略均以raw第三层为准，实施不得增设未定义模块。

| 子模块 | 接口及输出 | 状态与错误 |
| --- | --- | --- |
| 运行环境 | prepareRun(options)、startStaticServer(distRoot)、openBrowser(toolRoot, executablePath, origin) | 版本/哈希清单、静态HTTP及browser句柄；越界/复用/缺dist/启动失败即停 |
| 固定网络 | installScenarioRoutes(context, scenario)、releaseMessage(which,outcome) | 真实POST身份、初始化/冲突/交错/恢复阶段、两route、事件序号；未知请求/错误释放/超时为设施失败 |
| 页面与副本 | runScenario(page,controls,scenario)、captureEvidence(page,label) | 实际控件、DOM与测试storage快照；不直接读写store/controller，不记录真实凭据 |
| 收尾 | finishRun(resources,result) | 脱敏report与非零失败退出码；finally只关本轮句柄，保留日志/截图 |

## 第三层：详细实施任务

### 任务1：工具探针与隔离运行入口

**文件：** 新建上述单文件脚本；工具文件限本轮runtime/tool；日志限本轮证据目录。产品源码及依赖只读。

**输入：** 项目根、唯一run-id、已核实的系统浏览器绝对路径、固定工具版本；**输出：** 已验证launch/route/close的工具清单与可关闭静态HTTP入口。

- [ ] 写码前加载karpathy-guidelines和适用执行技能，记录当前diff及A产品冻结SHA；确认本次不存在另一进程写同一run目录。
- [ ] 读取`web/src/main.tsx`、auth及测试fixture，确认StrictMode/认证键与API合同；静态服务方法、MIME、SPA回退和路径约束按raw实现，无API代理。
- [ ] 在官方registry查询playwright-core版本及engines，选择与本机Node兼容的确切版本，先记清单再安装。拟执行：`npm view playwright-core version engines --registry=https://registry.npmjs.org`；随后以已校验绝对tool目录和明确版本执行`npm install --prefix <tool-absolute> --no-save --package-lock=false --ignore-scripts --registry=https://registry.npmjs.org playwright-core@<exact-version>`。缓存仅指定本轮runtime内目录；不得将占位符原样执行，不使用npx自动拉latest。
- [ ] 核Node解析确实来自tool目录，记录包版本及系统浏览器文件版本；不运行浏览器安装命令。若已批准依赖约束不允许临时工具安装，由主会话单列设施决策，不改web依赖绕行。
- [ ] 按raw实现prepareRun/startStaticServer/openBrowser及收尾，CLI参数使用明确的`--project-root`、`--tool-root`、`--browser-path`、`--run-id`、`--output-root`、`--probe-only`。默认拒绝缺参数、越界目录与已有run。
- [ ] `node --check <script-absolute>`应退出0。运行`node <script-absolute> <已核实参数> --probe-only`；验证真实浏览器获取route合成probe、API未知路径阻断、SPA可开及关闭后自有HTTP端口释放。用实际请求检查，不添加产品测试；错误时保留日志与非零退出码。
- [ ] 若需重新构建当前前端，执行现有`npm --prefix web run build`并记录退出码及dist/产品源码哈希。不得使用未知旧dist声称当前实现已验收。

### 任务2：真实控件交错、证据与独立审阅

**文件：** 同一脚本；新增本轮场景证据与中文报告，不修改Chat.test.tsx或产品文件。

**输入：** 任务1已通过环境，raw固定JSON合同；**输出：** conflict/network/cursor-loop/source-change各自结果、截图、请求时序与副本证据，未完成原因单列。

- [ ] 按raw实现固定网络和双route释放；所有API方法/身份精确白名单，初始化GET幂等。A/B仅根据当前阶段及消息请求到达事件分配，不机械照搬RTL全局snapshot次数。
- [ ] 按raw实现真实控件场景与证据函数；本人副本从真实发送后的实际storage捕获，另一writer只在该context合成且精确记录原文/身份。不能读应用私有store替代DOM证明。
- [ ] 先将单文件脚本及其完整源码、白名单diff、工具探针日志交独立代码审阅；项目默认OCR获取范围/全部规则，审阅只覆盖明确设施脚本及依赖边界，不能冒称Task10全范围产品审阅。审阅通过后才运行按钮场景。
- [ ] CLI提供`--scenario conflict|network|cursor-loop|source-change|all`，默认每场景全新context；命令形式`node <script-absolute> <已核实路径参数> --scenario all`。每步15秒、整场景90秒上限；超时报告最后阶段，不重发POST自愈。
- [ ] conflict：初始发送进入inconsistent→实际重查A且捕获挂起页→仍冲突时实际重查B→B矛盾先返→A正确后返。两次均截图核警告、禁发、本人/其他writer副本精确相等及POST=1；随后实际主动一致重查，正确答案可见且另一writer仍保留。
- [ ] network/cursor-loop：B先返回503或游标回环，核复核失败/禁发；A正确后返应显示正确答案并按既有门禁恢复，POST=1，其他writer副本未错误清理。
- [ ] source-change：按既有source候选UI运行，响应前精确变化源副本，核警告、恢复出口、其他副本/原文及请求数；已有inconsistent双重查组合不可达则保留UI/网络证据并标blocked，不调用内部函数或改入口合同。不可达与产品失败分别报告，由主会话决定是否还需最小范围内补证据。
- [ ] 检查截图实际可见内容、时序A/B身份和释放顺序、所有断言及finally终态。产出report.json、中文报告、命令及退出码；不以脚本退出0掩盖blocked。产品失败返回原A计划定位，不在设施任务擅改产品。
- [ ] 重算A产品源码/测试哈希，说明未因设施改变；主会话核白名单及README更新，根README仅链接设施计划/结果并保留真实验收未完成状态。无需重复全前端测试，除非产品确有新变更/失败或未解决疑虑。

## 命令、清理与交接说明

以上命令占位参数必须先解析为本机绝对路径和确切版本，运行清单保存展开后的脱敏命令。安装/运行句柄每30秒主动检查状态和日志；不得使用sleep、重复启动未结束句柄或kill现有浏览器。结束仅关闭本脚本HTTP/browser/context，验证自有进程终态；不删除证据、不清用户storage/数据库。

本文件已自审：目标、函数输入输出、数据/状态、原文保护、失败策略、范围白名单、工具能力探针与后续真实验收分界均对应raw。尚未安装或执行；交独立计划review。计划PASS授权的是A任务1测试设施落地，不授权新增产品依赖、新后端接口、系统浏览器安装或B架构扩展。

## 2026-11-03 补充：B/A 观察与 recover 闸门

设计来源为 raw 的“有限浏览器观察合同”。主会话接受常规端到端证据边界，不要求规范级函数退出证明；本补充不引入 CDP，不改变真实按钮或产品代码。

- [ ] B/A 各自在释放前按 held route 的精确 Request 对象身份建立 response/requestfinished 等待；核同一 Request、预置状态与完整 fixture 正文，失败或超时立即停止，不仅按 URL 匹配。
- [ ] 网络结束后等待页面一次独立任务轮转及两次 requestAnimationFrame，再执行既定 DOM、禁发、精确副本、POST=1 断言并保存证据；不使用固定 sleep。
- [ ] B 完成上述观察和断言后才释放 A；A 完成上述观察和断言、证据保存后才允许实际按钮 recover。已存在警告和 fulfill 完成都不能单独打开闸门。
- [ ] 事件分记 release、network-finished、render-observed，不写 handled 或业务函数已返回。报告说明：既有 RTL 验证确定性处理时序，本轮真实浏览器仅验证“指定网络完成并经过页面任务/渲染屏障后，观察到冲突仍保留”；帧屏障不构成业务函数退出证明。合成网络及其他既有未验收边界保持原文。
- [ ] 本补充及后续对应脚本变更交原独立审查者复核，通过后才执行按钮场景；本补充写入本身不表示脚本已实施或验收完成。

## 2026-11-03 补充：network/cursor-loop 恢复验收漏项

来源为 raw 的“会话门禁根因与验收漏项”。首轮 `browser-controlled/20261103-a-browser-final-01/` 的 network/cursor-loop 在正确答案已显示后，因仍待确认/禁发而失败，原证据保留。controller 行817–818、859、865表明旧 A 可匹配消息但因较新观察使会话门禁 uncertain；行881–913及真实页面按钮提供既有恢复出口。本次补的是验收步骤，不改产品行为，不将禁发降级为最终通过。

- [ ] network/cursor-loop 的旧 A 网络及页面观察完成后，先核正确答案、会话状态待确认、发送 disabled、另一 writer 精确副本和 POST=1，保存中间态；本人副本遵循已匹配后的既有清理合同。
- [ ] 实际点击“重新查询会话状态”，验证该次精确 snapshot Request、状态及一致正文（含 active_request_id=null），沿用任务/双帧观察屏障，不注入 store 或合成 success。
- [ ] 保留最终发送 enabled 的原断言，并核正确答案、待确认消失、另一 writer 精确副本、POST=1。出口失败或仍禁发记真实失败，不删断言、不自动改产品。新运行独立保存，不覆盖首轮 fail；source-change=blocked 等既有边界不变。
- [ ] 本补充先交独立复审；本轮仅更新 raw/plan，脚本和产品不在修改范围，尚不宣称复验通过。
