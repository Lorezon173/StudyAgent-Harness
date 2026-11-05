# Task12 最终验收证据独立审计

2026-11-04。结论：**PASS（仅Task12功能验收与累计审查证据；UNCOMMITTED）**。现有证据足以支持Task12在下列有限覆盖边界内进入文档收口与明确本地提交，未发现需要再补的核心验收证据。此结论不是Task12已提交/DONE、Task13完成、整个MVP完成或已部署；实际任务状态及提交仍由主会话裁决。

本次只读审计并新增本报告，未重跑浏览器、单测、build、OCR或联网审计，未修改产品、测试、计划、README或status，未stage/commit。没有把测试数量或代码审查PASS单独当作完成依据。

## 输入、冻结与执行身份

- 原合同：`superpowers/frontend-ui/2026-11-04-task12-round1-raw.md`、`docs/superpowers/plans/2026-11-04-task12-round1.md`及[原计划复审v2](round1-plan-review-v2.md)，完整阅读承接本审计前轮需求预审；[需求证据预审草稿](acceptance-requirements-audit-draft.md)是旧检查点，不是当前失败状态。批准补验、代表性补验及各局部修复计划/PASS与下列代码审查链结合使用，不修改历史设计或失败报告。
- 最新功能来源：[汇总](m3-baseline-round1-run-summary.md)、[实际run](playwright-m3-baseline-round1/run.log)、[exit-code](playwright-m3-baseline-round1/exit-code.txt)。**25 passed / 0 failed / 0 skipped，56.7秒，exit0**；24项受控API正式React HTTP浏览器场景、1项无mock真实HTTP账号组。第19项真实组确实执行并通过，不是skip。
- 当前完整E2E为524行，已分段完整读取。实算SHA256为 `FE14E88333F6A4B11B72132F12580A717E7527010BD224F027D0E98DE99FB5FD`，与最新run、实施after快照及最终审查冻结一致。当前20项全部重新计算SHA256，**20/20匹配**[最终审查hash清单](m3-baseline-state-review-hashes.json)，无漂移；本报告不另造一个产品冻结版本。
- `web/playwright.config.ts` 使用系统Chromium、本机4178正式React服务、单worker、retries=0、trace off、reuseExistingServer=false；显式隔离后端变量经Vite代理。真实组没有调用controlled/page.route或伪造登录；账号API准备数据后实际UI登录/退出。隔离PostgreSQL子库与后端身份见[环境记录](isolated-environment-preparation.md)。正式HTTP开发服务的验证不是dist静态托管直访或公网部署。
- [428项测试日志](exit-escape-priority-web-test.log)记录16文件/428测试通过，[build日志](exit-escape-priority-build.log)记录TypeScript/Vite构建成功；exit0及冻结关联见[实施交接](exit-escape-priority-implementation.md)及[独立复审](exit-escape-priority-code-review.md)。此后唯一源码变化为E2E baseline准备两行；19项其余产品/单元测试/配置均未变并经当前hash复核，所以可以沿用对应产品版本428/build证据。不是本审计重新运行，也不是独立E2E TypeScript检查全过。

## 原要求→实际证据

表内“通过”只覆盖所列场景；DOM/逻辑和静态结论不提升为真实后端或浏览器交互。

| 原raw核心用户行为/约束 | 证据层次与实际范围 | 审计判断 |
|---|---|---|
| 当前Chat真实摘要、owner/profile/revision门禁，null与0、覆盖n/m、前三非归档节点、当前节点、不伪造下一步、完整画像链接 | DOM/逻辑：Chat末尾同源42%/无额外读取，FloatingProfile的null/0/revision错配/链接及SummaryCard前三节点测试；静态：原19项审查及当前hash。受控浏览器键盘截图显示0%、覆盖1/1、当前条件概率，M3实际href与目标画像正文/当前节点成功；真实账号组使用实际新建主题，未生成教学评估 | 同源与语义证据充分；真实模型产生非零评估不是本轮门槛。其他ready/加载错误/非Chat门禁保留DOM与静态覆盖，不称各自真实浏览器穷举 |
| mouse连续进入详情、离开收缩；hover焦点BODY时Escape关闭并还焦/可再入；focus进入、内部Tab/ShiftTab保持、关闭详情不可Tab、再focus可开 | 最新run第15、23项；[keyboard-trace.json](playwright-m3-baseline-round1/artifacts/workspace-layout-受控-API-·-代表性键盘焦点与关闭详情/keyboard-trace.json)39条轨迹及当前spec375–411。入口→手柄→链接→反向、移出关闭、重新进入打开；Escape→入口关闭→手柄仍关→BODY仍关且链接DOM=0；反向重新进入手柄inDetails=false/expanded=true符合raw。真实focus-visible outline非none且宽度正；后续鼠标进入/离开也实际执行 | 通过。修正旧closed helper的阶段前提，没有用聚焦代替原BODY hover Escape，也没有删除关闭内容不可访问合同 |
| touch显式开关、纵向拖动、capture/4px/350ms/取消、键盘12px/边界夹取、比例0–1 | 第16/17/20项实际通过：恰4px零比例PATCH，正常拖动一次PATCH；350ms内click抑制/之后可开关；capture建立/释放；合成cancel不保存；底部Down不动且不写，再Up12/Down12并确认ratio；触屏tap与CDP手柄拖动、window.scrollY不变。零travel/非法ratio与生命周期清理有DOM/纯函数/静态证据 | 通过对应范围，原生OS取消、纯touch首次进入到拖动与卡外捕获极端路径按L1限定，不冒充已测 |
| 真实rect的8px安全区、宽度夹取、展开/resize不写ratio，短高实际内容可滚 | 14宽高矩阵两态bounds；第21项760×900→450展开调整且ratio/PATCH不变。M3真实滚详情末尾、标题End/滚轮、发送与账号命中、侧栏收展后bounds。公式及零travel由纯逻辑补足 | 通过；几何与手势依赖真实DOM，不以固定尺寸或CSS声明替代。未要求所有压力因素×14组合 |
| 默认固定、收起取消固定、展开不偷偷固定、切会话无自动收起；481–760侧栏170、<=480抽屉 | 第1–14项覆盖1440/1024/760/600/481/480/390各900/450；默认固定、170宽、收起释放主区、展开未固定入口、移动抽屉可见；Layout DOM核视图/选择合同；双会话第22项固定保持；真实组收栏/移动抽屉退出/新尺寸重登 | 通过。现有正常高度900与短高450明确，不扩称所有设备尺寸 |
| 长中文/长URL/两倍字号、主区/侧栏/消息独立滚动、账号/输入底部可达、可见焦点、reduced-motion | 第24项600×450长主题/长会话/24会话/30消息与无断点URL；[long-observations.json](playwright-m3-baseline-round1/artifacts/workspace-layout-受控-API-·-代表性短高长内容与两倍实际字号/long-observations.json)及spec413–485完整后段；详见下节数值 | 已通过代表性硬合同；是人工实际字号约2倍，不能称浏览器原生缩放或全部尺寸压力组合通过。正文可滚读/控件可操作，不承诺所有长文在屏内同时展示 |
| 浮卡低于移动导航、账号菜单、原生/非原生退出提示；Escape不抢前景焦点 | 第18项原生dialog :modal与Escape关闭；第25项真实touch保持浮卡展开→抽屉/菜单开关→受控503→role退出提示，实际命中/Stay焦点/Escape/抽屉保持/留页/草稿均执行通过；[overlay-observations.json](playwright-m3-baseline-round1/artifacts/workspace-layout-受控-API-·-代表性移动抽屉菜单与退出提示/overlay-observations.json) | 通过所测前景优先及操作合同；菜单本次点无几何交集，只证明可命中；退出Stay有实际交叠点命中。没有称完整Tab陷阱或所有可能重叠布局通过 |
| 无拖动/收展新增snapshot/messages/summary请求；不动draft/readingAnchor；同账号跨会话ratio | 第16项分段计数与草稿；第22项受控双会话真实滚到中段、写新草稿、非空anchor、浮卡手势后不增读/s1→s2→s1恢复id及偏移≤2px、共享ratio且无教学POST | 通过受控浏览器回归；合法切换GET另计，不误要求全程零GET。没有把fixture草稿回写冒充真实后端教学消息持久化 |
| prefs与recent单版本/单飞、dirty分离、慢GET/旧账号晚响应、409/失败显式重试、正常退出等待 | DOM/逻辑测试及[原代码审查](round1-code-review.md)、原计划v2的入口/去重合同、当前store/controller哈希未变；真实偏好正常退出见第19项 | 证据层次恰当：内部竞态可受控证明，不要求真实后端随机碰撞；未重新设计Task10请求算法或强关闭未确认prefs承诺 |
| A实际保存三偏好→GET→退出→新尺寸重登恢复→B默认/保存/拒绝A→回A原值 | 最新第19项完整通过；spec215–301不走mock：UI drag60/90实际位移、PATCH200、独立认证GET；A未固定/收起/非默认ratio，390移动抽屉正常退出不改确认三字段，1024重登收起DOM+实际ratio映射；B默认true/false/.5、本人主题、读A snapshot403，B保存不同ratio，回A三字段+DOM仍原值 | 真实HTTP通过。不是只有PATCH200或服务器仍存ratio；新尺寸DOM和A/B往返都实际断言 |
| profile/knowledge显式reload：新文档GET三偏好、URL稳定、收栏应用、零workspace PATCH，回Chat沿用ratio | 第19项两页均到后段；当前observeReloadWorkspace主frame提交后登记Request对象、response立即读体，断言GET200、三字段、一次导航、sidebar/URL、零PATCH并返回Chat按rect核ratio。顺序初始化与竞态DOM分开 | 真实HTTP通过。独立GET未替代新文档读体与UI应用；原读体失败不删不覆盖 |

## 代表性附件与关键实测复核

独立读取全部3份JSON，检查3份PNG非空并实际查看图片。路径均位于 `playwright-m3-baseline-round1/artifacts/` 下对应三个“代表性…”目录；显式PNG分别为keyboard-focus 67585字节、long-content 52373字节、overlay 34233字节，JSON分别4559、182175、3491字节。它们确实是本轮终态文件；未保留的14尺寸成功截图/矩形、真实组成功附件不虚构为归档证据。

- **M3字体与布局**：fonts/menuFonts/baselineFonts/reopenedFonts分别232/221/233/233个样本，各自actual−2×baseline最大绝对误差均0。采样前先恢复旧inline字号再计算，避免重复乘倍。600×450填草稿后composer y382.40625、高67.59375，send中心(559,416.203125)命中true；footer y249.8125、高200.1875在视口内，sidebar clientHeight64、messages130，均正高度。标题高93.75（budget≤96），内容高762，End滚末尾再真实wheel从668回0，全文文本不截短；顶部控制区也实际End/wheel可滚。
- **M3真实后段**：详情sh4923/ch291实际滚至末尾；侧栏和消息wheel各滚到500且彼此不变，footer/composer在同态展开+同倍率baseline前后y差≤1。document/main/sidebar/messages/details最终sw/cw分别600/600、430/430、149/149、430/430、279/279。pre保持white-space=pre，sw4926/cw269是代码块内部横向滚动，未撑宽消息区；不是错误把所有code改强制断行。19个motion样本animationName=none、duration/transition=0s。Tab到画像链接、focus-visible、命中、Enter后URL带p1/s1，目标`.profile-page .profile-grid .profile-panel`成功、无加载/alert、标题/当前知识点/节点列表/select=p1均通过；不是侧栏同名主题冒充正文。
- **M4真实后段**：抽屉/菜单tap开关后受控view-state PATCH503才触发退出提示。Stay点(86,483.6953125)与浮卡有实际几何交叠，elementFromPoint命中自身；main前后宽390一致，role/Stay均在390×844视口内。before/after escape均expanded=true、detailsVisible=true、drawerVisible=true、stayFocused=true，随后真实tap Stay、提示消失、URL仍chat/s1、草稿原文保留。JSON末尾在tap前记录，**Stay/草稿通过证据来自同一完整用例其后断言与run成功**，不是虚构JSON含成功后记录。此处Tab循环因初始autoFocus已在Stay可为零次，不当作完整Tab循环/陷阱证明。
- **目视边界**：两倍字体截图部分长文/侧栏顶部文案需要局部滚读，不能称全部同时可见或视觉美观穷举；关键操作、全文滚读与无指定区域横溢依据实际断言。overlay截图显示退出前景遮罩与留页动作高于卡片，键盘截图显示入口可见焦点及真实摘要语义。图片只作辅助，不替代操作和状态断言。

## 累计静态审查与20项映射

本次是证据审计，无新OCR preview或产品代码审查。累计覆盖的是Task12冻结20项，不是整个工作区；已有各报告完整preview/rule/ledger与具体任务外跳过原因继续有效，不把它们合并算出whole workspace PASS。

| 当前文件（均已实算hash匹配最终20项） | 最后相关审查/累计依据 |
|---|---|
| package-lock.json、package.json、playwright.config.ts、ProfileSummaryCard.tsx及.test.tsx、FloatingProfile.tsx、useFloatingProfile.test.ts、Chat.test.tsx、workspace.test.ts、workspace.ts、workspaceController.ts、vite.config.ts（12项） | [round1-code-review.md](round1-code-review.md)原19项完整审查；后续冻结未变hash桥接，不重复审历史大机制 |
| useFloatingProfile.ts、FloatingProfile.test.tsx（2项） | [browser-fix-round2-code-review.md](browser-fix-round2-code-review.md)当前BODY Escape/前景guard及必要测试，后续未变 |
| Chat.tsx、SessionSidebar.tsx（2项） | [representative-round1-fix-code-review.md](representative-round1-fix-code-review.md)静态class/tabIndex/wrapper；SessionSidebar为新增第20项上下文目标，后续hash未变 |
| index.css（1项） | [representative-fix-round2-code-review.md](representative-fix-round2-code-review.md)完整四目标审阅：CSS等无新增问题，唯一Medium在Layout Escape；该发现经下条PASS关闭，CSS本身hash后续不变，不把Needs changes整份忽略 |
| WorkspaceLayout.tsx及.test.tsx（2项） | [exit-escape-priority-code-review.md](exit-escape-priority-code-review.md)关闭唯一Medium，真实role guard对齐与行为RED/GREEN、当前hash一致 |
| workspace-layout.spec.ts（1项） | 原完整审查→[e2e修订](e2e-revision-code-review.md)→[core round2](browser-fix-round2-code-review.md)→[代表v2](representative-code-review-v2.md)→[局部布局](representative-round1-fix-code-review.md)→[代表round2发现](representative-fix-round2-code-review.md)→[Escape关闭发现](exit-escape-priority-code-review.md)→[最终baseline两行增量PASS](m3-baseline-state-code-review.md)；最终FE14…与实际run一致 |

统计：当前Task12冻结 `total_files=20, mapped_files=20, unmapped_files=0, evidence_mapping_coverage=100%`。这是累计审查证据映射，不冒充本审计重新逐文件代码Review的reviewed_files，也不覆盖任务外工作区。

## 历史、有限覆盖与后续边界

原21全失败、修订22的19/3、代表25的22/3、后续各原失败与Needs changes均保留。M2重新focus前提、M4定位双匹配、M3真实布局、退出Escape guard及最终baseline前提分别有诊断、计划、独审和实际新run，不用删除旧断言或覆盖旧报告掩盖。最新25全过只证明当前冻结场景，未改写历史失败性质。

以下为已约定的L1–L4有限范围，足以披露，不自动列新阻断或无限补测任务：

1. **L1**：合成pointercancel、CDP touch且拖动准备先hover，不称真实OS取消、纯触屏首次进入到拖动全链或全部卡外capture情形实测；生命周期/失capture等以DOM/逻辑及静态为主。
2. **L2**：14基础宽高+单600×450实际两倍字体代表压力，未穷举全部宽高×字号×长文×模态。人工字体注入不是原生浏览器文字缩放；零travel、非法ratio、动态输入极端高度等不冒称全浏览器覆盖。现代表长标题/侧栏/URL缺口已经补实测，不继续沿用旧草稿“未测”判断。
3. **L3**：并发GET/dirty/version/409/换代等接受受控DOM与静态证据；双会话草稿/锚点是受控浏览器回归，真实HTTP组是实际账号偏好保存。真实教学模型、PostgreSQL重启消息持久化与完整端到端另归Task13，不互相替代。
4. **L4**：null/0、revision/owner、前三筛选等数据分支由DOM/静态与少量浏览器当前文本/链接补足，不要求把每个DTO分支搬进全视口矩阵。真实新主题无非零评估不是缺陷，也不要求本轮调用模型补它。

独立E2E tsc既有Node声明缺失仍是未通过边界，不能因src build通过就称E2E独立类型检查成功；本轮未引入新依赖解决它。[原静态审查](round1-code-review.md)记录fresh npm audit因DNS ENOTFOUND失败，原13告警属于既有依赖树（含运行时React Router，不能统称开发依赖），新增3个1.64.1 Playwright包为精确dev包且旧lock对象未变；不称新鲜联网安全审计通过或全部告警已修。此证据审计不自动扩大为整树升级任务。

Task13仅按原计划继续隔离PostgreSQL/真实模型/账号B跨账号/HTTP浏览器全链，不推送、部署或发布。公网部署及直访验收需独立授权，不是stop13完成门槛。DEC-SESSION-001的B扩展恢复为独立候选，不是账号B，也不属于当前goal；独立实算TODO指向的原raw `superpowers/frontend-ui/task10-review-fix-round8-raw.md` SHA256为 `9ca7afdb94b3608168e1cb8a4e548bb59c2f5ad073bd6adb08bfe16fd45c34a4`，原plan `docs/superpowers/plans/2026-10-30-task10-review-fix-round8.md` 为 `fdde997b44bb64a23243c6d5063d639ede4c044bc2187b73f6fa48b03d08a65e`，均匹配保留记录。

## 收口裁决建议

Task12功能验收与必要累计独审证据**充分，PASS / VERIFIED_UNCOMMITTED**；无须仅为增加测试数量再开框架或全组合矩阵。主会话仍需独立安排README/账本准确收口、明确文件选择性提交及实际SHA/index核验后才能标DONE；本报告没有代替该步骤，也没有修改用户既有README/asset差异。Task11 DONE保留、Task13 PENDING及总goal未完成，不据Task12 PASS宣称上线。
