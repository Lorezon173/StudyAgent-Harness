# Task12 剩余两项代表性验收最小修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: 使用superpowers:subagent-driven-development。独立计划审阅PASS后Terra实施；完整web回归/build、冻结与OCR增量审查后再正式功能复验。本文仅文字设计，不代表代码或验收已完成。

**Goal:** 以真实未遮标题点完成原短高读取测试，并修复已复现的退出保存失败提示被flex挤压/遮罩拦截，使原三操作可用。

**Architecture:** 标题只修测试输入点；退出提示仅增加条件挂载的静态fixed overlay与局部CSS，脱离shell flex并位于抽屉前方。原保存/退出/备份回调原样，不新增函数、状态、全局事件或modal框架。

**Tech Stack:** 现有React/CSS、Vitest及Playwright正式HTTP页面。

**Spec:** [原raw](../../../../../superpowers/frontend-ui/2026-11-04-task12-round1-raw.md)短高全文可读/账号输入可操作与浮卡低于导航和退出提示；[已批代表计划](representative-acceptance-plan.md)、[前轮局部布局计划](representative-round1-fix-plan.md)。证据为[最新23/2结果](representative-fix-round1-run-summary.md)及[只读诊断](representative-fix-round1-diagnosis.md)；主会话已据报告裁决下述范围。

## 范围复核与第一层：保留成果，只补剩余硬项

最新25项为23 passed / 2 failed / 0 skipped、exit1；原core22及M2真实键盘链本轮通过。M3样本已改善：afterFill发送382–450、footer底部450、列表clientHeight64、消息scrollWidth=clientWidth430；这些进展保留，M3后段和M4 Escape/留页仍未通过，不能称完整三链完成。

M3诊断已证标题键盘End可到末尾；中心被浮卡覆盖，但实际未遮点(174,79)命中标题，真实mouse.move自然mouseleave收卡后wheel能滚回开头。这不是标题整体不可读；本轮只纠正中心hover假设，不改几何或宣称浮卡持续展开时wheel已验。

M4为受控503触发的真实产品DOM可操作性缺口：退出前main宽390，提示出现后static role节点参与shell flex使main宽74、卡宽58，留页点被z30遮罩命中；aside为fixed z40。与原raw退出提示可操作且高于导航/浮卡直接相关，本次修。503只是受控故障，不说成真实后端事故。

范围不再扩张：保留已有23行为、不新增场景/矩阵；必要新增复杂度仅一层静态overlay、局部CSS及测试真实输入点。前轮已审Sidebar/Chat静态滚动区与hook/队列/后端保持冻结；不新建focusTrap、modal控制器或状态机。原失败报告保留，仍不将测试数量替代行为。

**唯一白名单：**

- `web/src/components/workspace/WorkspaceLayout.tsx`：仅exitError条件内静态wrapper/class，现“留在页面”按钮加autoFocus；原role/name、文字、三按钮及所有处理器原样。
- `web/src/index.css`：仅退出overlay/panel样式；不动已审标题/Sidebar/消息/浮卡几何规则。
- `web/e2e/workspace-layout.spec.ts`：M3未遮点真实鼠标准备、M4必要main宽/命中观察；原25项和所有压力/锚定/留页断言保留。
- 必要`web/src/components/workspace/WorkspaceLayout.test.tsx`：现支持失败出口的初始焦点/留页语义行为验证，不为CSS断言写镜像测试。

## 第二层：子区结构、合同与数据流

### A. 标题读取的真实输入准备（仅E2E）

保留600×450、原长数据、逐元素实际2倍字体、title全文及End到末尾断言。将无指定点的`title.hover()`替换为当前title可见rect内有限候选点（四内角/左中点等，距边界4px；与viewport相交范围内选取）的只读elementFromPoint验证。只选实际命中title或其后代的点；无点则失败附rect/命中，不force hover/不隐藏浮卡/不改pointer-events/不程序关闭。

mouse.move到该点，让既有mouseleave自然处理，再真实wheel上滚，核title.scrollTop从末尾回0，文本未裁短；记录输入点、命中、前后展开状态和滚动。此链允许自然离卡收缩，不能把结果写成“持续展开时标题wheel可用”。后续顶部区滚读、发送/账号命中、区域锚定/独立滚动、代码块/reduce、末尾链接及目标正文全部保留，不以此准备绕过未验操作。

### B. 退出提示静态fixed overlay（产品局部）

`exitError`仍是唯一挂载条件，原提示role节点放入新增`.workspace-exit-overlay`；role节点加`.workspace-exit-dialog`。wrapper为position:fixed/inset:0/z-index:60，覆盖viewport、16px留白、grid居中及必要overflow:auto；60明确高于现有sidebar40、账号菜单45、遮罩30和浮卡5。它脱离shell flex，不应改变main/sidebar/footer的正常宽度。

panel宽度不超过520px且受wrapper可用宽限制，min-width:0、max-height:calc(100dvh - 32px)、overflow-y:auto、长文本换行、padding24px、纸感背景和边框；按钮允许按可用宽换行且保全部文字/动作。role/name保持`dialog/退出登录`，不迁移原生dialog，不冒称完整aria-modal焦点陷阱。外层背景无点击dismiss；不能用改mobileOpen或隐藏遮罩来避开竞争。

原`requestLogout`、`flushAll`、`failedItems`、`backupError`、`logoutWithBackup`、留页清exitError/exitPending等逻辑不改。安全焦点仅在现留页button增加React autoFocus：提示挂载时先聚焦非破坏性的留页动作；不添加effect、全局key监听或焦点返回协议。浮卡现有role优先级及原提示Escape行为继续验证：Escape不得误关提示/浮卡或偷焦trigger；不声称背景所有Tab均被禁止。卸载由原exitError条件自然完成，无新清理逻辑。

### C. 受控与真实验收边界

M4保持真实touch/tap、展开前提与原受控view-state503；抽屉仍开，必须在该原路径证明留页button命中前景并实际操作。记录提示出现前后main宽，390样本应保持原宽（容差1px），浮卡不再因role参与flex被压窄；角色panel及按钮在viewport内、内容高时可内部滚动。

autoFocus只增加初始焦点可观察断言，不取代真实Tab/Escape/留页链。原三按钮不因样式丢失；必要Layout测试沿既有保存失败出口证明提示挂载焦点在留页、留页不logout且保草稿。真实HTTP A/B组维持不mock；503/人工字体与真实后端结论分列。

## 第三层：字段、步骤与证据门禁

**没有新业务函数/字段/数据结构。** 产品变化仅两个class、一个静态wrapper和button autoFocus；E2E用现局部observations/log增加titlePoint/titleHit/titleScroll与mainBefore/mainAfter/roleRect等只读字段，不新建通用helper框架。

- [ ] 开工核E2E旧SHA为`9F26C8C60C00941E62A67BFB80AB0795F99819751E84A7AAE7AD933E7E0CD652`；用前轮20项冻结清单逐项核验，WorkspaceLayout及其测试已在20项内，不凭空新增第21项；明确本轮实际修改source列表。保存全部本轮目标before/after完整文本和20项哈希，新文件名不覆盖原快照。
- [ ] 先独立计划审阅PASS再实施；必要Layout行为测试复现失败提示初始焦点缺口，CSS可操作性RED引用已执行M4命中遮罩和诊断实测，不能假称jsdom测得层级。修改仅B的静态结构/样式，原三处理器逐字核无业务变化。
- [ ] M3按A选择真实未遮点、mouse.move和wheel；不删除End/title.scrollTop/全文/原两倍样本或区域锚定断言。不改变Sidebar/Chat代码或浮卡展开几何。
- [ ] M4保原phase的aria-expanded=true、hit、受控503、Tab/Escape和留页/草稿断言；增加autoFocus留页及main宽稳定观察，context finally和实际附件写盘保留。焦点已有正确初值时不为走Tab而先主动移走来掩盖行为；原有有界Tab路径仍可验证当前支持范围，不新增完整focusTrap要求。
- [ ] 运行完整前端回归及build，既有基线426项；新增必要语义测试后数量按实际记录，不能固定旧数量伪称本轮通过。collect仍预期25，以实际结果为准；collect/类型边界与真实功能分别表述。
- [ ] 冻结after全文/20项hash，实际修改四目标以内；Sidebar/Chat/其余非目标必须无变。OCR preview/rule保留全部范围和排除原因，独立增量审覆盖本轮全部实际修改及原回调上下文；不重做未变20项全套，不称全工作区PASS。
- [ ] OCR PASS后使用隔离后端正式运行全部25项到终态，新目录`playwright-representative-fix-round2/`；必要定向定位可先执行但保留每次结果。30秒主动检查、不sleep、不并发争用4178。原真实A/B组不能skip，原23通过不得自动继承。
- [ ] 验收要证明M3原压力场景后续完整操作和目标画像正文；M4抽屉仍开时提示不挤main、前景命中、焦点优先、Escape不偷焦、真实留页及原草稿可读。若后段新失败，先记录现场并按scope复核，不继续堆特殊分支或弱化断言。
- [ ] 核附件实际存在并按证据类型汇总。Task12仍IN_PROGRESS直至必要行为/最终审计与明确提交；Task13、B候选、L1–L4限制保留，不stage/commit/推送。

## 交接状态

本轮仅计划，待独审；未新执行功能。已完成23行为保留，只补剩余标题真实输入与退出提示前景两个硬项；不改变信任边界或持久化合同。
