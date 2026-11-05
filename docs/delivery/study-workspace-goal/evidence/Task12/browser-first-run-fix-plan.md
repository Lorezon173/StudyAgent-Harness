# Task12 首轮浏览器夹具与手势命中修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 superpowers:subagent-driven-development；本计划先独立审阅 PASS，再实施单文件修复；编码后完成 OCR 增量审查，再运行功能测试。各步骤以复选框记录，不以计划文本代替实际结果。

**Goal:** 修正阻断原浏览器验收的 API 拦截边界与拖动坐标采样顺序，让正式 React 页加载，并让拖动手势实际命中当前手柄；与已批准补验合并单文件增量审查后重新验证。

**Architecture:** 仅修复 Playwright 局部夹具和输入序列，不改产品布局、几何算法或保存通道。非 API 模块请求正常继续；拖动前先显式展开、确认布局稳定，再获取当下手柄坐标并验证捕获和移动。

**Tech Stack:** 现有 @playwright/test 1.64.1、系统 Chromium、既有 Vite HTTP 配置与隔离 FastAPI。

**Spec:** 来源为 [Task12 raw](../../../../../superpowers/frontend-ui/2026-11-04-task12-round1-raw.md) 的局部几何、浏览器验收合同及 [round1 计划](../../../../superpowers/plans/2026-11-04-task12-round1.md) Task D；事实依据为 [首轮诊断](browser-first-run-diagnosis.md)。与已独审 PASS 的 [验收补充计划](acceptance-supplement-plan.md) 并用，不替换其真实 A/B、reload 和双会话合同。

## Global Constraints

- 仅允许修改 `web/e2e/workspace-layout.spec.ts`；不修改产品、后端、配置、依赖、README、status 或既有失败证据，不提交/推送/部署。
- 原 [21 项首轮结果](original-run-summary.md) 为 0 passed / 21 failed / 0 skipped、exit 1，完整 run、截图和退出码原样保留；修复后另建运行目录。
- 原 4px 阈值、350ms 抑制、cancel 不保存、键盘位移、请求计数、草稿、副作用及跨账号拒绝等断言全部保留，不通过降级期待或删断言掩盖回归。
- 真实组继续使用正式 UI 登录及真实 API；受控 PATCH 的成功不能冒充真实持久化。真实组不得 route mock。
- 先加载 planning/karpathy/TDD 等适用执行技能；主会话规划审阅，子代理实施。不得未经审阅直接写测试修复。
- 长命令每 30 秒主动检查进展，不 sleep；不并发争用 4178，不自动下载浏览器或更改全局设置。

## Review Focus

1. Vite `/src/api/client.ts` 虽含 `/api/` 片段，pathname 不以 `/api/` 开头，必须正常加载。
2. hover 展开会改变手柄位置；不得复用展开前坐标或用旧中心命中详情后称已拖动。
3. hover 稳定后手柄可能又因详情高度/resize 改变；pointerdown 前须核当前命中，不能用固定等待猜稳定。
4. 稳定手势准备不能引入比例 PATCH 或额外消息读取，否则原阈值和副作用测试会失去意义。
5. 原真实失败现场未记录 pointer target；受控复现仅支持一种机制，修复后真实后端复验仍是完成门槛。

## 第一层：模块总览

### 事实与用户行为边界

诊断已确认原受控 `page.route('**/api/**')` 误拦 Vite 模块 `/src/api/client.ts`，未知端点分支返回 404，导致模块 ERR_ABORTED 和空 body。修复目标是受控正式页可以加载并显示原草稿，不是给页面增加降级界面。

原真实组页面已渲染，最早失败是拖动后 ratio 仍为 0.5；现场没有 pointer 事件证据，具体原因尚未完全证明。独立受控复现原“先取收起坐标再 mouse.move”顺序时，hover 展开后旧中心实际命中详情 div，无比例 PATCH。先展开稳定再采样，在有评估与待评估两组受控摘要中，pointerdown 均命中手柄、capture=true、移动60px确实位移60px并发出比例 PATCH。这不能证明真实持久化或全部交互通过。

主会话已裁决 raw 允许展开重测几何，本轮仅修验收夹具与手势命中。首次 hover 导致手柄移动仍是可记录的交互限制候选，不因此改产品或宣称问题已全面解决。

### 完成条件与排除项

原受控正式页面不再因模块被夹具404而白屏；真实/受控拖动输入实际命中手柄并建立捕获，受空间允许的位移与目标相符；保留原21项合同，并与已批准补验取得新的终态和逐项证据，真实组非 skip 且真实 PATCH/GET 核对成功才计真实通过。若仍失败，保留现场并按实际症状诊断，不预先保证全绿。

本计划无新产品机制，不扩大到拖拽重构、布局状态机、触屏协议、模型教学、数据库重启或 Task13。测试文件修复不等于 Task12 完成；后续仍须执行已批准补验。

## 第二层：子模块职责、接口及数据流

### A. 受控 API 路由边界

输入是 page.route 回调接收的请求 URL、method、body。首先读取 URL pathname；只有以 `/api/` 开头的请求进入现有 API 夹具和 calls 统计，其余立即 continue，不能解析请求体、改状态、计为 API 或走未知端点404。真实 `/api/` 未知端点仍返回404，避免静默吞掉漏配接口。

数据流：Vite 模块请求 → pathname guard → continue → 浏览器加载 React；真实 API 请求 → guard → 原现有分支 → 受控响应。API 调用清单只记录真实 API pathname，既有断言口径不变。

### B. 拖动准备与命中验证

输入是 Page、手柄定位器和当前测试目标；输出当下稳定的可见手柄中心及必要观测。先 hover 学习画像入口，等 aria-expanded=true 和详情可见，再轮询当前手柄 rect 稳定（相邻样本位置/尺寸差不超过1px，无固定 sleep）。定位后 mouse.move 至当前中心；pointerdown 前核 elementFromPoint 对应手柄或其内部元素，坐标不再属于手柄时重新采样，不能盲点。

真实 mouse.down 或 CDP touchStart 后断言手柄持有该活动 pointer 的 capture。鼠标移动后先观测实际位移，再 mouse.up/触屏结束及原保存断言。原4px用例保持4px不提交，超过阈值的完成拖动保持一次提交；正常释放后 capture 结束。cancel 仍明确为合成注入，不能升级成真实操作系统取消证据。

hover 准备不保存位置，不触发 snapshot/messages/summary 读取；消息请求基线在会话ready后、准备前记录，因此不能把准备阶段的异常GET藏到新基线之前。多次拖动各自重新取当前rect，不能复用上一手势中心。仅展开夹取不应写 ratio，原 resize 不保存断言继续保留。

### C. 真实后端验证与证据分层

真实组沿用隔离账号/主题/会话准备、正式登录和 workspace 读回。拖动前确认目标位置有足够安全 travel；向下60px若空间不足，先在允许区间选择明确可达到的起点/方向，并记录实际距离，不能碰到边界后仍期待60px。当前正常高度应优先验证诊断中可行的60px。

真实组保存必须观察本轮 UI 引发的 workspace PATCH 成功，再通过该账号独立 GET 验证有限非默认 ratio 与实际位移一致，不能仅凭受控PATCH或服务端旧值判通过。失败保留 pointer目标、capture、前后rect、请求状态/脱敏body及GET结果，区分未命中、捕获失败、几何夹取、请求未发和服务端保存失败。不记录密码、token或Authorization。

## 第三层：函数、字段和文字实施步骤

### 任务 1：最小夹具与手势修复

**唯一文件：** `web/e2e/workspace-layout.spec.ts`。保留现有测试名称及断言；按照补验计划扩展真实用例并新增一个双会话回归，预计22项，以实际collect为准，便于首轮对照。

- [ ] 修改 `controlled(page)` 的 route 回调：输入现有 Route；最前方构造pathname并执行上述guard；输出非API continue或原API响应。calls数据结构仍是 url/method/body，不新增公共路由框架；未知真实API仍404。
- [ ] 增加文件局部 `prepareFloatingDrag(page)`：输入 Page；输出当前 handleRect、中心x/y、准备前后浮卡rect及aria-expanded状态。显式hover、等待展开与rect稳定、定位当前手柄；不操作store、不直接调用handler、不自动写prefs。稳定性通过expect.poll/浏览器采样确认，超时附rect轨迹。
- [ ] 增加最小观测 `assertDragTarget(page, point)`：输入Page和当前中心；输出命中元素的标签/可访问名称并断言其位于手柄内；真实pointerdown后直接核capture。若记录pointerId，使用短期DOM事件观察并及时移除，不硬把触摸pointerId当成鼠标1。
- [ ] 修复“指针阈值、捕获、取消、键盘及请求计数”中的每次坐标采样：准备稳定后取rect，4px边界和正常拖动分别采样；cancel第二手势也重新准备。保留原4px零比例PATCH、完成一次PATCH、350ms前后click状态、cancel不增加保存、ArrowDown及消息GET/草稿断言。4px手势可有4px视觉位移与否按原合同核“不成为拖动”，不得改成超过4px再期待不保存。
- [ ] 修复真实“A保存并重登、B隔离和深链恢复”的首段拖动：先稳定展开、重新定位、命中/capture核对，再移动/释放；真实PATCH与GET均需验证，原重登/B默认/403和深链旧断言保留；该用例新增序列严格依已批准补验计划执行。
- [ ] 修复“触屏手柄拖动不滚动页面”的坐标依赖：保持hasTouch/isMobile context及CDP触摸输入，先通过现有合法浏览器交互使展开状态确定再取当前rect；记录实际touch pointerId并核capture/位移，保留一次比例PATCH和window.scrollY不变。hover只是本受控手柄拖动用例的定位准备，不据此声称证明纯触屏用户路径；原触屏显式开关测试保留并单独验证该路径。
- [ ] 检查所有mouse.down、CDP touchStart及新增拖动使用点，确保凡依赖坐标的拖动均不复用展开前位置；原14尺寸用例、hover连续性、短高/resize用例不做无关重写。
- [ ] 记录准备前后API计数及本轮事件/rect，证明准备没有新增ratio PATCH和消息/画像读取；仅保留必要的局部helper，不新增产品测试接口或通用框架。

### 任务 2：独审与功能验收顺序（选择一次单文件改动）

选择本计划与已批准补验计划合并一次测试文件改动、一次OCR增量审查，再运行全部用例。成本是同轮含修复和新增断言，必须按请求phase和逐项结果区分；收益是避免同文件两次修改与重复审查。未变产品不重做19项全范围OCR。

- [ ] 本计划独立审阅PASS后实施任务1及已批准补验计划；补验新增拖动也复用稳定手势准备且保留各组副作用断言。先作测试文件类型/收集检查，收集成功不能算行为通过，新增观测在现实现可能直接通过，不伪造RED。
- [ ] 对修订测试文件执行OCR preview及rule，按项目要求保留全清单和排除原因，但独立增量审查范围仅该文件差异/完整上下文及对应原合同；工作区其他文件逐项注明任务外，不宣称全工作区PASS。源文件/配置未变通过哈希复核；报告PASS后才开始正式功能运行。
- [ ] 使用现有隔离后端与配置，记录服务身份/健康、测试文件哈希、collect数量和运行命令；全部用例运行至终态，输出到独立 `playwright-fix-round1/`，不覆盖原run。允许先单独跑受控加载/手势与真实组定位，但每次记录真实状态，最终完整执行一次（预计22项，以实际collect为准）。
- [ ] 失败先按A/B/C分层规则诊断；真实首次drag未确认通过，不能继续把后续闭环记为已验。若出现产品问题，先报告根因、实际支持入口与最小方案，再走批准计划/审查流程，不在本修复内越界。
- [ ] 逐项对照原21项合同与补验新增断言，分别记录原失败是否解除、A/B真实闭环及受控双会话结论；若原核心仍失败，不以新增项通过宣称Task12完成。
- [ ] 测试文件最终变更后核完整web test/build及浏览器证据；README/账本由主会话另行串行更新。本计划作者不更新这些文件，不提交。

## 自检与交接

诊断白屏对应任务1路由guard，受控手柄失配机制对应稳定采样/命中/capture/位移，原真实现场证据不足对应真实PATCH与GET复验门槛；原4px/350ms/cancel/副作用合同全部保留。本文状态：仅计划，待独立审阅；未编码、未重新运行原21项，不宣称修复或验收完成。
