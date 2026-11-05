# Task12 代表性首轮失败：范围复核与最小修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: 使用superpowers:subagent-driven-development；先独立计划审阅PASS，再Terra实施；必要测试/build与独立OCR增量审查后，执行全部25项功能验收。本文仅设计，未编码。

**Goal:** 保留三条原硬要求代表性补证，纠正两个无效测试前提，并局部修复已复现的短高双倍字体下标题挤占、侧栏不可达和长消息横溢。

**Architecture:** 仅调整静态布局class/容器与CSS，让标题和侧栏顶部各自有界滚动、消息独立滚动、composer和账号留在可见底部；测试按原focus合同与精确按钮名称执行。无新函数、产品状态、事件框架或保存通道。

**Tech Stack:** 既有React/CSS、Playwright受控正式HTTP页面、既有web回归。

**Spec:** [原Task12 raw](../../../../../superpowers/frontend-ui/2026-11-04-task12-round1-raw.md) B/D及验收段；[已批准代表性计划](representative-acceptance-plan.md)；[25项首轮结果](representative-round1-run-summary.md)、[只读诊断](representative-round1-diagnosis.md)。主会话已明确裁决：保留三类hard行为，M2/M4最小测试纠正，M3三类实际布局缺口本次修复；原报告和成果保留。

## 范围与根因复核：先作取舍，再继续实现

AGENTS第7节要求扩张信号出现时先列已完成行为、未完成核心项和必要复杂度，不能只“再审一轮”。本轮新增代表测试连续出现自身前提问题，触发此复核。

| 项目 | 已有事实 | 本轮裁决 |
|---|---|---|
| 已完成核心 | core22上轮全通过，本轮25中原22再次全通过：真实A偏好保存/退出重登/两深链恢复/B独立保存与403/回A、14尺寸、受控双会话草稿锚点及基本交互等 | 保留现有用户行为和原22主体，不重写既有机制 |
| 未完成原hard行为 | 新增3链均失败；完整focus链后段、600×450实际2倍字体长内容可操作/独立滚动、受控退出提示命中/Escape后段尚未通过 | 保留3条代表链，不增场景数或矩阵；修复前提再实测，不假称后段通过 |
| 新增复杂度 | 3个E2E用例、长数据/字体注入/受控503与观测；没有新增产品机制 | 保留必要证据，停止新增helper框架/通用故障设施。字体注入明确是人工压力样本，不是原生浏览器缩放 |
| M2根因 | Escape后内部手柄仍关闭、Tab到BODY关闭；ShiftTab重新进入手柄后expanded=true、inDetails=false，符合raw“blur后重新focus可开”；closedhelper无条件要求false错误 | 只纠正测试阶段边界，不改hook，不删关闭详情不可Tab断言 |
| M4根因 | 非exact“关闭会话导航”同时匹配遮罩与按钮，strict失败，尚未到退出提示 | 所有相同关闭按钮locator精确匹配；不预修未复现role层级问题 |
| M3根因 | 同人工2倍/长数据受控复现：h1高761.5超过chat375，composer随外层滚动；fill后send中心y506.41在450视口外。侧栏列表高0、footer y498.33/h200.19。消息长URL横溢4169/430 | 与原“短高/字号下输入账号可操作、列表/消息独立滚动且不横裁切”直接相关；局部布局修复，不靠scrollIntoView、缩短fixture/减字号或隐藏功能绕过 |

结论为“继续，但简化到静态布局和测试两处纠正”，不拆出新产品模块、不把全部压力组合加入本轮。标题/顶部功能滚动区是本次必要新增DOM复杂度：现有无界固定内容已把列表/输入推出视口，单加min-height:0或测试滚动不能同时满足底部锚定和列表正高度。状态/数据流完全沿用原合同。

## 第一层：模块总览与文件白名单

- `web/src/index.css`：主改动；有界标题/顶部区、消息换行与代码块内滚、composer布局、账号菜单前景及必要焦点样式。
- `web/src/pages/Chat.tsx`：仅给现有h1、消息scroller、composer ref外围加稳定布局class；标题可加静态tabIndex和名称以便键盘滚动全文。不改scrollRef/hostRef/composerRef语义、恢复effect、消息DOM id、draft/readingAnchor/发送/教学算法。
- `web/src/components/workspace/SessionSidebar.tsx`：仅将品牌、固定/收起、新建和TOPICS标签包成静态顶部操作区；列表和账号footer仍为其兄弟。功能、回调、可访问名称不变。
- `web/e2e/workspace-layout.spec.ts`：M2阶段纠正、M4精确定位；M3保全部原合同并补必要前后测量，不另加矩阵或改变字体/长数据规模。
- 必要现有Chat/WorkspaceLayout测试：只核新增静态可访问结构和原操作回调仍有效，不改旧用户合同或为CSS写大量镜像测试。无新增生产MessageBubble改动；现有Chat命名空间可覆盖其子树换行和pre，因此不列可选越界文件。

排除hook、几何算法、workspace/prefs队列、后端/API/迁移、配置依赖与其他生产组件。README/status此子任务不动，不stage/commit。Task13及B独立候选、L1–L4有限覆盖保留。原冻结E2E SHA256 `294B268A46EDC19726D04DEF3C2E46E38A72757E56BEB836C477205DD1BB87E0`；另存本轮完整before/after及哈希，不覆盖历史快照。

## 第二层：静态子区合同、数据流及尺寸依据

### A. Chat：有界全文标题、消息与输入

现有纵向flex内h1改为`chat-session-title`，保留全文文本，`flex-shrink:0`、顶部区最大高度为chat高度25%且不超过96px、底部间距8px、overflow-y:auto、长词anywhere换行。标题本身静态tabIndex=0并有可见focus样式，使全文可滚读；无折叠toggle或截断ellipsis。以样本chat375为例上限93.75px，避免761.5px标题挤走composer；正常短标题仍自然高度。

现有消息ref元素加`chat-messages`，仍是唯一消息滚动容器，flex分配剩余空间、min-height:0/min-width:0，现有overflow-y:auto保留；composer ref外围加`chat-composer-area`，不可收缩并在主区底部。form采用flex+8px gap，输入flex:1/min-width:0，发送不可收缩；不增加发送操作或改变disabled条件。既有保存状态提示仍显示，不能隐藏腾空间；本样本需测消息正高度，极端超出所有固定内容预算仍属既有有限覆盖，不能在样本失败时拿此免责。

在`.legacy-chat [data-message-id]`及其现有bubble子布局范围设置min-width:0和overflow-wrap:anywhere，使普通文本/无断点URL参与换行、不撑消息容器。Markdown pre明确max-width:100%、overflow-x:auto、white-space:pre、overflow-wrap:normal，内部code同样保留代码行；代码需要的横滚留在pre内部，不把整页/消息区撑宽。无需更改MessageBubble JSX或Markdown解析。

数据流仍是bucket→原消息/标题/输入DOM；布局测量由现有ResizeObserver按实际rect重算浮卡，不保存resize夹取ratio。不得新增JS高度测量器或将位置保存反向耦合到CSS。

### B. Sidebar：顶部功能有界滚动、列表正高度、账号底部

在现有aside内加`sidebar-top-controls`静态wrapper，包含原品牌/controls/new/label；max-height为侧栏内容区35%，min-height:0、overflow-y:auto、flex:0 1 auto。wrapper可用静态tabIndex=0/region名称“会话导航操作”供键盘滚动，焦点样式沿用可见outline；不隐藏固定/收起/新建功能，不缩回2倍字号。列表仍为`.sidebar-groups`，flex:1且本代表样本最低48px，纵向独立滚动；footer仍不可收缩并留在底部。

35%与48px来自本样本预算：450高侧栏扣顶部22px约428px；顶部约150px上限＋实测footer约200px＋原14px间距后仍给列表约64px，满足正高度。900高时约315px上限，正常顶部自然高度不必撑满。若浏览器复验实际box模型不满足预算，只在本局部限额内据rect修正，记录数值依据；不能加JS状态、减字号或删功能。brand/装饰只可紧凑间距，不依赖隐藏功能。

账号footer不放进新滚动wrapper，菜单保留footer内绝对定位，并给现有`.account-actions`明确高于浮卡5的层级45；aside本体不加overflow裁剪。移动aside现有z40保持，其内部菜单不受顶部scroll裁剪。此项是原raw“账号菜单高于浮卡”的局部合同；非原生退出dialog尚未跑，不在这里预先改其层级。

### C. M2/M4测试精确恢复原合同

M2将关闭期与重新focus期分开：Escape后入口→仍在卡内手柄→卡外BODY期间，详情不在DOM、焦点不在详情、expanded=false；从卡外ShiftTab重新进入手柄时应expanded=true（raw允许），且本次焦点是手柄而非此前隐藏详情。再按原顺序回入口/离开及鼠标出入检查。仅到重新进入那一步切换期望，不删先前不可Tab断言，也不改产品阻止重开。

M4所有“关闭会话导航”按钮定位器含末尾条件分支都用exact=true，明确选择既有关闭按钮；遮罩另名不误匹配。保留touch/mobile上下文、真实tap、各phase展开前提、命中/Tab/Escape/留页/草稿及context finally。是否role提示可命中留给实际运行；失败按新现场报告，不用先关抽屉、跳过命中等方式悄悄绕过待验路径。

## 第三层：字段、步骤和验证（无实现代码）

### 任务1：小范围生产布局

无新函数、业务字段、状态结构或接口。新增仅上述class、两个可滚读区域的静态可访问属性和Sidebar顶部wrapper。输入是原DOM文本/回调及现有viewport；输出为真实rect/scroll分配，错误处理仍用原加载/保存提示。

- [ ] 核before全文/白名单哈希，读适用karpathy/TDD技能；M3当前失败为已执行行为RED，补充fill后composer/send rect与hit、title高度、sidebar列表/footer及URL横溢记录，不能只引用输入前y898冒充fill后位置。
- [ ] 按A给Chat仅加class/标题静态可访问属性；消息scroller和composer refs仍在原元素，标题正文无裁短。按B只包顶部功能，列表/账号回调与focus refs不变。
- [ ] CSS实现上述限额、flex分配、wrap/pre内滚和菜单层级；不改字体注入、不加transform反缩、不隐藏状态/按钮。顶部区滚动和标题滚动均可真实键盘/滚轮读取全文。
- [ ] 必要现有组件语义回归验证新标题/顶部region保留原文本和操作；完整web test/build，不以jsdom rect证明浏览器布局。复核Chat恢复effect/refs/消息id与保存调用链无差异。

### 任务2：测试纠正与原M3行为复验

- [ ] M2只调整现有step的阶段处理：闭合链逐步断言closed及无详情，重新进入目标手柄这一刻断言可重开；保留bounded Tab轨迹、focus-visible和后续mouse链。不新建通用焦点框架。
- [ ] M4现有关闭locator全部exact；不改变toggle/角色/菜单结构，不弱化任何展开或hit前提。
- [ ] M3保600×450、同长数据/实际逐元素2倍字体、reduce computed、滚动/链接/正文断言。增加紧邻fill后的regions/send矩形和命中记录，断言composer/send/账号在可视区、列表和消息clientHeight>0；不通过scrollIntoView使发送临时可达。
- [ ] 把“滚消息/滚列表前后锚定”基线放在相同的已加载字体/草稿保存状态，避免把新增“草稿已保存”行导致的合理布局变化当滚动漂移；保存原输入前观测作诊断，但不能拿不同时态baseline假证锚定。未改变“消息/列表滚动不带走账号和composer”合同。
- [ ] 原25项构成和core22主体保留，collect记录实际数量；无法到后段时明确标未验。若出现非原生role提示真实遮挡或后续新问题，记录触发/展开/命中/影响并交主裁，不继续扩改本轮白名单。

### 任务3：独审后功能门禁与验收

- [ ] 本计划独审PASS→Terra实施→完整测试/build与冻结before/after→OCR本轮全部修改增量独审。preview/rule保留全清单/排除原因，授权目标全覆盖，任务外注明跳过，不重做未变产品整套审查或称全工作区PASS。
- [ ] OCR通过后正式HTTP完整25项至终态，新目录`playwright-representative-fix-round1/`；可先定向三链定位，但保存每次结果并最终全量。30秒主动轮询，不sleep、不并发争用4178；真实账号组非skip。
- [ ] 浏览器必须证明：原core22不回归；M2关闭不可Tab且重新focus可开；M3原压力样本composer/账号可操作、标题全文可滚、列表/消息正高度且独立滚动、普通长URL不横裁切、字体实际2倍、详情末尾链接/正文与reduce值均满足；M4精确关闭后继续完整原覆盖层链。额外代码块样本可在既有长消息中保留一条等规模代码文本用于核pre内部scroll，不新增独立用例/矩阵或替换原长URL。
- [ ] 成功截图/JSON须核实际落盘；受控字体/503与真实后端结论分列，历史失败不改。若新增布局修复主要再生特殊分支而核心仍停滞，再按AGENTS范围复核，不能自动下一轮堆机制。
- [ ] Task12继续IN_PROGRESS直到全部必要行为/最终需求审计及明确提交；Task13和L1–L4边界保留。此任务不改README/status，不stage/commit。

## 交接状态

范围与根因已复核，主会话裁决为保留3代表hard要求、修两个测试错误及三个样本内实际布局缺口。仅新增本文，待独立审阅；没有代码修改或新功能执行。
