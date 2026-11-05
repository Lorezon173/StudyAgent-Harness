# Task12 浏览器第二轮最小修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 superpowers:subagent-driven-development；先独立计划审阅PASS，再编码；独立OCR增量审查通过后执行功能验收。本文均为文字设计，不代表实现或测试通过。

**Goal:** 修复hover浮卡的Escape覆盖缺口，纠正键盘测试的边界前提，并使深链reload观察明确关联新文档且立即读取响应，保留真实偏好应用断言。

**Architecture:** 仅在现有hook增加一个受交互上下文约束的Escape监听；键盘测试先建立可移动空间；深链使用局部、短期Playwright事件观察，不改产品几何、偏好保存队列或后端。

**Tech Stack:** 现有React18、Vitest/Testing Library、Playwright1.64.1及系统浏览器、隔离HTTP后端。已核本地playwright-core类型提供framenavigated/request/response与监听清理接口。

**Spec:** [Task12 raw](../../../../../superpowers/frontend-ui/2026-11-04-task12-round1-raw.md) B/D及验收合同；[前轮修复计划](browser-first-run-fix-plan.md)、[已批准补验计划](acceptance-supplement-plan.md)继续有效。证据：[22项首轮结果](fix-round1-run-summary.md)、[只读诊断](browser-fix-round1-diagnosis.md)。不修改上述历史报告。

## 第一层：模块总览、事实与边界

当前22项实际19 passed / 3 failed / 0 skipped，exit1；原14尺寸矩阵与受控双会话通过，不代替真实持久化。真实组到达深链reload读取响应体失败，后续B未执行，不能称真实A/B闭环完成。

| 失败 | 已核证据与性质 | 本轮目标 |
|---|---|---|
| hover后Escape不关 | 独立受控复现activeElement=BODY，Escape目标BODY；容器onKeyDown不接收。聚焦手柄后可关/回入口/再入重开。产品事件覆盖缺口 | 无需先点手柄，hover展开后Escape即可关；保留焦点与重开合同 |
| ArrowDown未移12px | 同序受控复现ratio=1，card.bottom=composer.top-8，下方空间0；Up实移12px并PATCH | 保边界Down不动/不保存；先Up建立空间，再严格Down12px |
| reload的response.json失败 | 原读取在await reload之后，Network.getResponseBody资源不可用；旧GET误捕或响应过期只是可能，未证实哪一种 | 关联新文档GET，响应到达立即读体并留结果；真实复验才证明错误解除 |

用户可见产品变化仅为第一项。第二项修正测试前提：原合同一直是每次12px且按安全边界夹取，不允许越界；在底部要求Down仍移动12px属于无效前提，保留Down12px断言但改在有空间的位置验证。第三项不修改产品恢复行为，不允许吞json错误、删除三偏好断言或用独立GET替代新文档应用。

文件白名单：`web/src/hooks/useFloatingProfile.ts`、`web/src/hooks/useFloatingProfile.test.ts`、`web/src/components/profile/FloatingProfile.test.tsx`、`web/e2e/workspace-layout.spec.ts`。仅在必要测试归属内增改；FloatingProfile生产组件、Chat、CSS、workspace队列、配置、依赖、后端均不改。Task13/模型/PG重启/部署/B扩展排除。README/status只作本轮文档检查点，由主会话串行安排，不由实现者并发改。

## 第二层：子模块合同、数据流和错误处理

### A. Escape最小窗口监听

沿用已有dismissed、hover、touchLock、containerRef/triggerRef与open；不新建事件框架或第二套关闭状态。打开时安装一个window冒泡keydown监听，关闭/卸载/sessionId或generation变化时清理；原容器Escape路径改由这个监听统一处理，避免同一键重复关闭/还焦。

监听仅处理未defaultPrevented、非组合输入的Escape，且浮卡仍展开；目标在卡内，或目标为BODY/根节点且当前hover/touchLock参与浮卡交互时才有资格。其他输入框、textarea、contenteditable及卡外已聚焦操作优先，不因鼠标仍悬浮而抢它们的Escape。当前原生`dialog[open]`、已挂载退出`[role="dialog"]`或可见移动导航抽屉优先，浮卡监听不preventDefault、不改变它们的关闭行为、不还焦入口。使用现有DOM标记判断这些已支持覆盖层，不泛化覆盖层协议。

有资格关闭时：preventDefault，dismissed=true、touchLock=false、open=false，焦点回当前trigger；不写prefs或消息。保持原“当前hover/focus仍在时不反开、离开再入/重新focus/显式激活可再开”。外部dialog优先时不偷焦点；未安装/已清理旧监听不得影响新会话。优先级不足若被真实支持路径复现，先报告最小补充，不扩大机制。

### B. 键盘合法前提与边界断言

原组合测试的拖动、350ms、cancel均保留。键盘段先记录展开卡/host/composer rect、ratio及已确认比例PATCH数，确定下边界已到；此时Down应保持位置且无新增比例PATCH。然后Up：确认有上方12px空间，实际y减少12px、出现新确认ratio；再Down：从这一位置增加12px并恢复先前底部位置/ratio。容差1px，不能只验证函数调用或放宽为任意正位移。等待每次保存结束再计下一次PATCH，避免并发队列混淆。

原消息/summary读取零增量、草稿原文、capture/cancel和键盘preventDefault的产品合同保留。若独立环境不在预期边界，显式记录并用已存在用户手势建立边界，不直接改store；不得默默假设ratio=1。

### C. 深链reload的新文档观察

观察限于真实用例两页reload；不得拦截响应或改变服务器行为。在reload前安装主frame导航、request、response监听，保存本次mainFrame对象；以其首个本轮跨文档导航提交事件、期望path作为新文档门槛。只收录门槛之后由该mainFrame发出的`GET /api/workspace-state` Request对象；response必须对应该Request集合，不能仅凭同URL匹配旧文档在途响应。记录事件序号/时间、frame URL、请求对象本地编号与响应状态；不写凭证。

所有监听在reload调用前就位；主frame提交后新文档脚本才发出的GET被request监听登记，response监听立即启动json读取，把成功值或读取异常存为本轮结果。reload完成后等待这个已启动的读取结果，再断言GET200、三偏好等于基线、URL不变、sidebar收起DOM、本观察窗口workspace PATCH为零，之后回Chat验证ratio。没有捕到合格请求、读体失败或导航再次变化都明确失败并输出时序，不能退化为接任意GET/独立request.get/忽略错误。若实际事件次序不满足此关联设计，保留现场再裁决，不扩成通用网络状态机。

goto前一页的监听也应等待其本页workspace GET和DOM应用结束后才移除，以减少在途旧请求；这只是前置稳定，不代替reload的新文档关联。PATCH监听从reload前覆盖到上述GET/DOM断言完成；try/finally移除全部短期监听，超时/异常也清理，读体拒绝明确传回测试，避免异步未处理拒绝。两页窗口独立，不允许profile事件污染knowledge。

## 第三层：函数、字段与实施步骤（无代码）

### 任务1：hook修复与最小行为测试

**输入：** 现有useFloatingProfile Options及refs；**输出：** 原hook返回合同不变，Escape关闭覆盖hover+BODY。

- [ ] 先在必要hook/组件测试中复现“真实focus仍在BODY、mouse hover展开、对BODY派发Escape仍开”的行为RED；不能将聚焦trigger后的旧测试冒称复现。保留旧已聚焦关闭/重开测试。
- [ ] hook增加局部`dismissForEscape(event)`，输入原生KeyboardEvent、现有交互refs，输出是否处理；只执行A的资格判断和原关闭动作。不新增公共导出/状态；原React容器Escape绑定移除，避免两个处理器。window注册effect依赖open/sessionId/generation，cleanup移除原函数引用；现有拖动cleanup不改。
- [ ] 验证BODY hover Escape关、focus回trigger、当前hover不立即反开、鼠标出入/显式激活再开；内部手柄Escape仍关且一次还焦，无prefs保存。
- [ ] 验证defaultPrevented/组合输入、卡外输入焦点、原生dialog、现有role dialog及移动抽屉优先；Escape不会被浮卡preventDefault或抢焦。至少用实际已支持覆盖层DOM合同构造必要组件测试，不发明新产品覆盖层。
- [ ] 验证closed不处理、卸载无残留，session/generation重置后旧监听不能操作旧trigger；rerender后仅当前监听处理一次，不能仅靠spy监听次数宣称行为正确。定向测试GREEN后完整web test/build，保留真实RED日志。

### 任务2：两处E2E修订

**唯一文件：** 既有workspace-layout.spec.ts；原测试名称/22项合同保留，新增必要Escape优先级浏览器断言可并入现有交互/弹窗用例，以实际collect为准，不扩大视口组合。

- [ ] 键盘组合段按B记录`boundaryRect`、`baselineRatio`、`patchCount`，底部Down不动/无新PATCH；Up精确12px并等保存；再Down精确12px并等保存/恢复。其余原阈值、抑制、cancel、草稿及请求数断言保留。
- [ ] 原hover→详情→Escape流程保持无手动focus，修复后核关闭、trigger焦点及再入重开；既有modal用例中核Escape仍由dialog处理且焦点不被浮卡偷走。输入优先级主要由必要组件测试覆盖，不新建全尺寸矩阵。
- [ ] 增加文件局部`observeReloadWorkspace(page, expectedPath)`：输入Page和当前深链path；输出本次新文档GET状态/已解析三偏好/事件时序/方法清单及清理能力。局部字段仅`mainFrame`、`committed`、`requestSet`、`sequence/events`、`bodyResult`、`patches`；不得跨测试共享或保存token。只用当前Playwright已提供事件，不引入CDP文档追踪框架。
- [ ] 深链循环按C执行：监听先装→reload→合格response立即读体→reload与body完成→三prefs/URL/DOM/零PATCH→回Chat ratio；finally清理。保留真实A/B前后所有已批准断言，B未运行历史不能写成已通过。捕获错误必须失败并脱敏附上下文。

### 任务3：独立审查、功能复验及失败分层

- [ ] 本计划独立审阅PASS后才实施任务1/2；读适用karpathy/TDD技能，冻结白名单哈希，保护既有19/3和原21失败报告。保持单轮最小变更。
- [ ] 编码与必要单测/build后，执行OCR preview/rule完整保留清单与排除原因；独立增量审查覆盖本轮全部修改和完整调用上下文，任务外逐项说明，不宣称全工作区通过。未变几何/保存队列仅核哈希，不重审整个产品机制。
- [ ] OCR通过后用隔离后端正式HTTP运行新一轮全部e2e（现22项，实际collect为准），新目录`playwright-fix-round2/`；长命令按30秒主动检查，不sleep、不并发占4178。需要定向定位可先跑三失败项，但保留每次状态并最终全量到终态。
- [ ] 分别报告Escape真实BODY路径及覆盖层优先级、键盘空间/位移/PATCH、深链新文档GET应用及A/B后续闭环。19项已过不能据此自动继承为本轮通过；完整结果按实际运行记录。受控消息/响应与真实持久化结论分开。
- [ ] 深链继续失败时先检查新文档事件关联、读体时序和服务器响应，不删除断言；Escape若侵入dialog/输入即产品回归，停止新增机制，按最小支持路径复核；几何或队列新问题先报告范围而非直接改。
- [ ] 全部核心行为仍未通过则Task12 IN_PROGRESS；Task13仍PENDING。README/账本仅由主会话据实际结果串行收口，不提交/stage/推送。

## 交接状态

本计划只处理三项已观测失败，其中两个有受控根因复现，深链底层原因尚未确证；观测修订是否解除问题由真实复验裁定。计划待独立审阅，未编码；所有原失败证据保留。
