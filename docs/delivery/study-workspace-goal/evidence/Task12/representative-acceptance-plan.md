# Task12 三条代表性浏览器补证 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 superpowers:subagent-driven-development。先独立计划审阅PASS，且core round2 OCR及全部用例结果通过后，才实施本补证；不得并发修改当前冻结E2E。编码后单文件OCR增量审查，再执行功能验收。

**Goal:** 为原raw的键盘可达、短高长内容/实际字号压力和覆盖层操作优先补充三条代表性浏览器证据，不将静态CSS或可见性推断为行为通过。

**Architecture:** 只扩展现有正式React HTTP页面的受控fixture和最多3个局部E2E用例；真实键盘、滚轮、点击与命中观察驱动，不改产品样式、布局或后端。核心真实账号/深链闭环仍由原有用例完成。

**Tech Stack:** 现有Playwright及系统Chromium、正式Vite HTTP页面，沿用`/api/` pathname guard。

**Spec:** [Task12 raw](../../../../../superpowers/frontend-ui/2026-11-04-task12-round1-raw.md) B的focus/关闭不可Tab、D及验收段的滚动/可达/层级/200%字号/reduced-motion；[需求证据预审](acceptance-requirements-audit-draft.md) M2/M3/M4，经主会话裁决补最小代表性证据。此文不更改raw，不把预审建议自动升级为产品缺陷。

## 第一层：目标边界与完成条件

唯一代码白名单为`web/e2e/workspace-layout.spec.ts`；本次仅写本文，未编码。最多3条代表性链，不乘以原14视口矩阵，不新建框架、依赖、产品测试接口或故障服务。原core round2冻结与报告保留；本计划不抢实施，需主会话确认core结果后再串行接手同文件。

三链均为**受控API的正式页面、真实浏览器输入**，不是无mock真实HTTP持久化。完成须同时保存实际行为断言、关键几何/焦点/滚动/计算样式与失败现场；截图存在、overflow:auto、`:modal`或emulateMedia成功都不能单独判通过。新增断言暴露实际失败时报告触发、影响和证据，由主会话另裁最小修复；不得改产品CSS、隐藏内容、删断言或增加无关防御来凑通过。

主会话接受有限覆盖L1–L4：不新增OS原生取消设施、纯touch首次拖动全链、极端无travel真实浏览器或全部压力组合；内部竞态仍可引用受控DOM，数据语义可引用DOM/静态。最终不能称这些限制“浏览器已验”。真实模型/PG重启/完整公网验收仍为Task13，不在本补证内。

## 第二层：三条代表性场景合同与数据流

### M2：1024×900，真实Tab/ShiftTab链

最小现有fixture，不用长侧栏。鼠标移到卡外无hover区，从页面自然焦点顺序以Tab进入入口（不能`focus()`入口代替），核aria-expanded及实际activeElement、`:focus-visible`和可见outline；Tab到手柄、完整画像链接，ShiftTab返回手柄/入口，内部切换保持展开。焦点离开整个浮卡且鼠标仍在外时收缩；再用ShiftTab返回入口可重开。

Escape关闭后焦点回入口，确认仍保持关闭；Tab后可访问仍显示的手柄，再离开卡片，整个已关闭期间不能进入详情链接或其它卸载详情节点。再次ShiftTab到入口可开；最后真实鼠标进入→离开、焦点已在卡外时收缩，避免用hover焦点混合状态误判。记录逐步activeElement身份和展开状态；路径最多40次Tab/ShiftTab，超限明确失败，不循环到偶然满足。不改变tabIndex或DOM顺序。

### M3：600×450，长内容、实际两倍字体与操作链

使用同owner/revision的有效长中文主题、3个真实DTO结构的长节点标题及无断点URL；列表约24个会话、消息约30条，使侧栏列表/消息确实溢出。只生成测试数据，不伪造教学或随机评分。先在正常字号记录各区rect/scroll，再施加下述**测试注入的文本字号压力**，不把它称为浏览器原生文本缩放或所有用户字体环境。

字号方案：在当前渲染完成时一次性采集工作区所有已渲染HTMLElement的computed fontSize；再统一将各元素inline fontSize设为其自身基线的2倍，避免px字体未随根字号变化以及逐层继承倍增。只允许字体大小覆盖，不改变width/height/overflow/position/transform/可见性。新增渲染的菜单在打开后按其无覆盖基线同样采样并加倍；不得将继承到的已加倍值再次乘2。保存基线映射及实际computed结果，至少核浮卡标题/正文/末尾链接、导航、侧栏会话按钮、账号与输入控件都约为原值2倍（容差1px），不满足即标字号准备失败。原`html.fontSize=200%`用例保留，但不据它推断所有px字也翻倍；不用transform或页面整体图像缩放代替字体重排。

展开卡片后先核详情scrollHeight>clientHeight，真实wheel使scrollTop>0并到达末尾；用真实Tab到达末尾画像链接（可自动滚入视野），核链接命中、可见焦点与正确href，按Enter实际进入目标画像页，核profile_id/session_id和对应主题。不得直接设置scrollTop或`click(force)`作为可达证据。链接导航安排在本链末尾，避免前面的操作丢失字号注入。

链接导航前：输入草稿并核可编辑/可保存，发送按钮可命中且enabled（不发送教学请求）；侧栏收起/展开按钮实际点击，复核浮卡安全边界。分别滚消息容器和侧栏列表，记录另一容器scrollTop不变、账号footer与composer的rect仍锚定且控件可操作。检查document、workspace-main、消息容器、sidebar-groups、floating-profile-content的scrollWidth≤clientWidth+1；滚动容器的纵向溢出允许，横向裁切不以document单独无溢出替代。

reduce=true时读取浮卡及子元素computed animationName/animationDuration/transitionDuration，证明实际无有效动画（name=none或duration=0）且transitionDuration均0；记录当前值，不编造非reduce对照动画。短高长内容未溢出则说明fixture不足，不能只读overflow样式判通过；按约定数据规模仍不足时报告并最小调整文本/条目，不能改产品尺寸。

### M4：390×844，现有导航/菜单/受控退出提示优先

独立fixture，正常字号，先打开浮卡，再打开现有移动导航。实际操作账号菜单，记录浮卡与抽屉/菜单的rect；如存在几何交集，在交集内选属于可操作按钮的点，elementFromPoint应为该前景按钮或其后代，再真实点击操作。无交集时如实记“无重叠样本”，仍验证按钮中心命中及可操作，不伪造位置或宣称验证了重叠z-index。

先关闭/再开菜单与抽屉，确认这些操作实际生效；抽屉关闭后输入草稿。仅本fixture对当前会话view-state PATCH返回受控503，使原自动保存与退出flush均失败，随后经现有账号UI正常退出，出现现有非原生`role=dialog`“退出登录”提示。该受控网络故障不是后端真实故障；不调用内部store或直接挂dialog DOM。

核退出提示按钮真实命中、浮卡不遮挡；用Tab在提示现有支持路径操作“留在页面”（不额外承诺原产品没有的完整焦点陷阱），按Escape观察焦点不被浮卡偷到入口，提示不因浮卡而关闭；再实际点击“留在页面”确认提示消失、仍登录/原路由、草稿保留。不触发“退出并保留”避免本机退出备份协议扩展。原生dialog优先继续由core用例证明，本链不替换它。

## 第三层：局部函数、字段与可检查步骤

### 任务1：最小fixture及观测

- [ ] 保留现有`controlled(page, multi)`合同，增加可选局部代表性seed/失败开关，默认完全不变；字段仅profile/summary节点标题、group会话条目、messages及failViewSaves。API分支按有效sessionId处理，GET/PATCH版本保持现有契约，非`/api/`继续，未知真实API仍404；failViewSaves只影响指定当前会话PATCH，不拦模块或workspace读取。
- [ ] `tabUntil(page, target, direction, limit)`输入Page、目标定位器、Tab方向及最多40次；输出每步焦点/aria-expanded；仅真实键盘，不用focus()/改tabIndex。目标不可达或循环返回起点就失败并附轨迹，不能无限重试。
- [ ] `readRegionState(page)`输入Page；输出document/main/sidebarList/messages/card/details/composer/footer的rect、scrollTop、scrollWidth/clientWidth、scrollHeight/clientHeight。只读；wheel前后比较不相关区域滚动值与固定控件rect，容差1px。
- [ ] 字号注入局部过程输入已渲染工作区和倍数2，输出元素原fontSize/覆盖值/实际fontSize及恢复函数；所有基线先读完再写，标记只覆盖一次。仅施加上述已说明的测试字号压力；重新渲染或菜单新节点不能误乘继承后的值。无法建立真实基线则标本样本未验证，不能硬宣称200%通过。
- [ ] `assertHit(page, locator, optionalIntersection)`输入目标及可用重叠区域；输出选点和elementFromPoint身份，断言目标或其后代命中并真实点击结果。不得移动浮卡制造交集、加z-index、force点击或直接调用handler。

### 任务2：最多3条用例与断言

- [ ] M2用例按第二层执行完整键盘链；每次内部转移保持开、真正离开关，Escape后的关闭详情不参与Tab；读取focus-visible实际outline样式/宽度/颜色且截取焦点证据。不能以activeElement存在就称视觉焦点可见。
- [ ] M3用例按第二层执行单600×450链：记录有效两倍字体、详情实际scrollTop、末尾链接键盘激活、独立滚动、账号/输入/侧栏操作、容器无横裁切及reduce computed值。缺足够滚动内容或某个按钮不可操作都记录失败，不通过临时删文本、换小字号或隐藏区域绕过。
- [ ] M4用例通过已有受控保存失败触发提示，记录前景命中/实际操作和Escape焦点；最终留在页面并核草稿。若现有样式让提示在视口外或被遮挡，先报告可达失败，不改产品来通过验收。
- [ ] 三条都记录fixture标识、实际输入、视口、字号方法/实测值、焦点轨迹、滚动和rect/命中数据、computed motion值、相关API状态及截图。成功附件确认实际保存，失败保留上下文；不记录token/密码，不将受控数据写成真实服务数据。

### 任务3：串行门禁与交付

- [ ] 本计划独立审阅PASS，且core round2代码OCR和完整功能结果已通过，再核冻结哈希并接手单E2E文件；core未过则等待主会话裁决，不抢改或重跑占端口。
- [ ] 实施后类型/collect检查，再作单文件OCR增量独审（preview/rule保留全部范围/排除理由，任务外注明跳过，不称全工作区审查）；审查通过后定向执行三链和完整E2E，实际collect为准，不预写通过数量。
- [ ] 原14矩阵及真实A/B/深链用例保留；本轮3代表性样本不扩成14倍全组合。API受控/无mock真实组、DOM/静态及接受限制分别汇总，不能以全绿推断所有raw压力组合通过。
- [ ] 若发现真实功能失败，输出触发条件、用户影响、证据及最小修复候选，交主会话另裁；本计划不授权改hook/样式/队列/后端。无功能失败且证据齐备时再做最终需求审计，README/status按实际结果串行更新；不stage/commit/推送。

## 交接状态

仅新增本文，待独审且等待core round2终态；未修改当前冻结E2E、产品、README或账本。M2/M3/M4为代表性受控浏览器补证，L1–L4有限覆盖和Task13边界原样保留。
