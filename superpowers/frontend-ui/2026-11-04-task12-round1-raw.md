# Task12 A环形浮卡、工作区偏好与响应式：三层设计原稿

日期：2026-11-04。阶段：仅设计，不编码。承接用户已批准的Task10→13终稿，以下是既定范围的技术细化；不重新请求同一授权。实施前须完成独立计划审查。基线为Task11本地提交 `bd3df180f6ef37b922674bc0e16d30d946eb9a54`，并发README/账本由主会话维护，执行前重新核HEAD及差异。

计划产出时主会话已将Task11完成追记提交至 `a6117c48c1ff7e8877806d0862e69ff0e42f13f4`（父提交为上述产品基线）；这是docs-only追记，实施以最新HEAD核查后执行，不把旧计划哈希当产品当前哈希。

## 来源与事实

- 核心合同：`docs/superpowers/plans/2026-10-23-study-workspace-core.md` Task12。
- 视觉与交互：`2026-10-23-paper-preview-raw.md` 第五、七、八节及 `2026-10-23-final-implementation-raw.md` E；后续确认取代早期“取消固定自动收起”。需求关系追溯 `2026-10-23-multi-session-profile-raw.md`。视觉基准为 `docs/designs/frontend-paper-study.html`，实施前记录哈希。
- `Chat.tsx` 已从唯一workspaceStore读取当前bucket，包含profile、profileSummary、session.active_node_id；消息滚动恢复、草稿/请求恢复分支均已存在。
- `ProfileSummaryCard` 当前props为profile、summary、activeNodeId，是纯展示组件；ProfileSummary含profile_revision、nodes、mastery_score、assessment_coverage及assessed_count/total_count，无“下一步”文本字段。
- `/api/workspace-state` GET/PATCH及WorkspaceState/WorkspacePatch已经提供sidebar_pinned、sidebar_collapsed、progress_y_ratio、expected_version。当前controller的loadWorkspace/flushWorkspace只应用/写入最近会话，store没有偏好持久化状态；不能假称prefs已接通。
- 现有壳已采用481–760px的170px双栏、<=480px抽屉，侧栏默认固定展开、手动收起取消固定；本任务补齐压力条件与持久化，不重写导航。
- web现有React18、Vite5、Vitest2、Testing Library/jsdom；无正式Playwright开发依赖。Task10临时验收工具曾固定playwright-core 1.64.1并复用系统浏览器，可复用经验，不能将临时工具当作已存在项目依赖。

## 第一层：模块总览

### 用户行为与完成条件

问答右侧出现A环形窄浮卡，显示当前主题真实总体掌握度；靠近展开、远离收缩，键盘与触屏可独立完成打开、关闭与再开。浮卡可纵向拖动及按键微调，位置按账号保存，重登同账号恢复并适配当前尺寸，其他账号不能看到旧位置/主题。主内容与侧栏完整可达，浮卡不覆盖导航、输入、账号与模态层。

当前缺口是正式Chat没有浮卡、偏好DTO未连入状态保存、缺真实拖动与完整尺寸浏览器验收。完成必须在正式React HTTP页面实际验证交互与服务器偏好读回；单元测试、HTTP200、图片或OCR PASS均不替代行为闭环。Task13的真实模型连续教学/PG重启验收仍保留，不在Task12冒称通过。

### 架构与边界

沿用现有栈与既有API。FloatingProfile纯消费Chat注入的已核profile/summary；useFloatingProfile只处理局部几何与输入事件；现有workspace唯一版本通道最小扩展保存偏好。不得新建第二个workspace PATCH写入者与Task10竞争expected_version。

生产入口是认证工作区 `/chat/:sessionId`；仅ready且session/profile/summary归属与修订匹配时展示真实指标，空会话/加载错误不渲染旧主题；数据暂缺显示“画像暂不可用”，不伪造0%。只读画像和知识库页不出现浮卡。标题、模型文本、节点正文按React安全文本/现有Markdown策略展示，不引入HTML注入。

排除后端/API/迁移、B checkpoint、知识规划K、权重、新图谱、并排会话、上传、新持久化框架、部署和推送。Task10请求关联、幂等、草稿、本机恢复候选、冲突选择、账号generation和导航恢复门禁保留。若必须改这些算法或后端才能实现，先作为实质范围变化报告。

## 第二层：子模块概述

### A. 真实摘要浮卡

Chat仅添加主区/输入区容器ref与浮卡挂载，继续现有消息、draft、request和恢复分支。FloatingProfile接收ProfileItem、ProfileSummary、activeNodeId、sessionId及定位/偏好接口。复用ProfileSummaryCard同一个summary对象，最小增加compact展示变体，保持Task11默认输出合同。环形读mastery_score，null显示待评估，0显示0%，文案仍是“已评估知识点平均掌握度”，显示覆盖n/m，不能称完成率。

展开最多展示summary顺序的前三个有效非归档节点，含nullable掌握度；不足三项如实显示。无服务端下一步字段，不生成教学建议；“下一步”区仅给出真实当前知识点（若有）与“查看完整画像”导航动作，明确不是模型生成建议。完整画像URL携带当前profile_id/session_id。revision不匹配时显示暂不可用，不增加summary GET或消息请求。

### B. 局部收展、拖动与几何

同一连续可命中容器包含窄入口和展开卡，避免入口移向卡片时触发mouseleave闪退。鼠标进入或focus进入展开；离开且无内部focus/触屏锁定/拖动时收缩。触屏点击显式开关；Escape关闭并把焦点回到入口，同时抑制当前hover/focus立即反开；离开后重新进入、blur后重新focus、显式点击都可再次打开。内部Tab不收缩，关闭内容不可被Tab访问。

独立拖动手柄采用touch-action:none，正文保留滚动与链接点击。仅主pointer且左键开始，记录pointerId/startClientY/startTop；capture保证移出仍跟踪，超过4px才成为拖动（恰4px不算）。结束拖动350ms内抑制同一次手势产生的click，普通小位移点击保留。pointerup、pointercancel、lostpointercapture、组件卸载、会话/账号换代和页面隐藏均清理capture与临时状态；取消不提交未完成位置，恢复开始前已确认比例；正常结束只保存一次。键盘手柄ArrowUp/Down每次12px并夹取，防止页面同时滚动；键盘每次改变后可合并至同一偏好队列。

测量使用主区相对坐标：安全顶部为topbar下沿与主区顶部较大值再留8px，安全底部为composer上沿与主区底部较小值减8px。卡片外高不得超过可用高度，展开内容内部overflow-y:auto，宽度不得溢出主区。collapsed/expanded高度均用真实DOM尺寸，展开、ResizeObserver检测主区/导航/输入/卡片尺寸变化、窗口resize及字号改变后重算；不依赖固定75px猜边界。短高不足时压缩非内容间距，保留可访问的手柄与内容滚动，不侵入导航/输入。

ratio为卡片顶部在可移动区间的0–1比例；top=minimumTop+ratio×可移动距离。无移动空间定位minimumTop，保持原有限ratio；只因resize/展开夹取不写回比例，避免越缩越漂移。持久化仅有限0–1数，非法值回默认0.5，不把NaN发API。

### C. 账号偏好与单版本保存

在现有workspace状态旁加prefs子结构，不把位置放session bucket。初始pinned=true、collapsed=false、ratio=0.5；loadWorkspace现有成功结果同时恢复prefs，仅在prefs自读开始后未编辑时应用，避免慢GET覆盖新手势。按既有account ticket/generation清空并隔离所有晚成功、错误和finally。

首次读取由认证WorkspaceLayout承担：effect按有效账号generation调用薄入口ensureWorkspacePreferences(ticket)，覆盖直接打开/刷新 `/profile`、`/knowledge` 与 `/chat` 的全部正式工作区入口。入口仅复用既有loadWorkspace的GET、版本与readSequence门禁、同generation在途请求；已加载prefs可直接返回，失败可显式重试，不新增初始化状态机。该入口不调用lastSession后的导航、不调用selectSession、不写last_session_id、不验证/消费/删除本机最近会话候选；既有loadWorkspace如同时读取服务器最近会话参考值及列出候选，仍只保留原只读行为。返回结果只用于恢复sidebar并缓存ratio，即使本页无浮卡也要缓存，之后进入Chat直接使用。

Layout初读与Chat的lastSession并发时必须共用同代在途GET；loadWorkspace的forceFresh只表示不能复用已完成旧缓存，不允许绕过去重而再发同代并行GET。新读仍按现有readSequence/version门禁发布；最近会话导航只由原Chat hook消费其结果并经过原路由门禁。直接profile/knowledge刷新读取后URL不变、最近会话候选不被选择；初读过程中用户手动收栏或拖动，prefs编辑sequence保护本地新值，A→B换代丢弃A读取及错误/finally。

扩展同一个flushWorkspace单飞循环：请求只包含本轮dirty字段，expected_version共用现有workspace.version；最近会话未dirty时绝不附带last_session_id，更不能把null写回。保存捕获recent sequence及prefs sequence，响应版本推进后仅清除与请求捕获值/序号相同的dirty标记，期间新手势继续下一轮。selectSession既有去重/备份/候选删除只按最近会话dirty/sequence判断，不能把prefs dirty误当最近会话变化。

409继续保留现有最近会话冲突保护与用户明确选择，不自动覆盖其他设备；prefs本地值保持并显示“界面偏好未保存”，提供重试。重读最新workspace只更新确认version/服务器参考；有本地dirty的prefs不被覆盖。用户解决既有workspace冲突后再提交仍dirty prefs；无最近会话冲突的纯prefs 409也采用显式重试，不自动覆盖远端。不能对prefs冲突调用selectSession、改变URL或消费最近会话候选。普通网络失败保留本地值，重试同样经单飞通道；只在服务端确认后称已保存。无需为prefs新增本机恢复协议，强制关闭只承诺服务端已确认偏好；正常退出flushAll必须包含prefs结果，退出失败提示区分最近会话与界面偏好。

### D. 响应式、层级及验收设施

481以上侧栏始终独立占位；481–760为170px，主区min-width/min-height为0且长链接换行；<=480为带遮罩抽屉。默认固定，收起同时取消固定，展开不偷偷固定，切session/视图不自动收起。列表/消息独立纵向滚动、账号底部、输入底部。右上入口可换行，不能挤掉可用主区。浮卡z-index低于移动导航、账号菜单和非原生退出对话框；原生dialog top layer继续高于浮卡。

项目新增仅开发依赖的固定兼容@playwright/test及lock，优先与已有实测1.64.1同系列核Node engines、系统浏览器兼容后使用精确版本1.64.1；核实不可用则记录原因及明确替代精确版本后审查，不静默升级。执行器可复用临时工具定位系统浏览器的经验，不引入playwright运行时到dependencies，不自动下载浏览器或修改全局。配置只启本轮HTTP前端/隔离后端并清理自己进程，重用用户服务须核URL/构建哈希，不绕过file标签拒绝。

## 第三层：详细函数、字段与数据结构（文字，无实现代码）

1. FloatingProfile：输入前述真实DTO及host/topbar/composer DOM引用、ratio、savePreference；输出可访问的窄入口/环形/摘要/拖动手柄/完整画像链接。业务summary只props注入，不能自行加载消息或评估。
2. ProfileSummaryCard新增可选compact展示参数，默认false；输入输出现有三个props不变；紧凑时复用同DTO指标与前三节点，不创建另一套计算分数函数。
3. useFloatingProfile：输入测量元素ref、ratio、账号generation、sessionId、savePreference；输出open、dragging、top、maxHeight及入口/容器/手柄事件绑定。只局部React状态，不订阅或写消息列表。
4. measureFloatingBounds：输入hostRect、topbarRect、composerRect、真实卡片高度及8px留白；输出minimumTop、maximumTop、availableHeight、travel，统一主区坐标，travel不小于0。缺元素时不计算虚构位置，待layout effect测量。
5. normalizeProgressRatio：输入未知值、默认0.5；输出有限且夹在0–1的number。ratioToTop输入ratio与bounds输出top；topToRatio输入top/bounds/上次ratio输出规范比例，零travel保留上次ratio。
6. open/close/toggle处理：输入鼠标/focus/touch/Escape事件及relatedTarget，输出局部收展与焦点转移；使用dismissedWhileEngaged标志防止Escape返回入口后立即反开，重新进入或显式激活清标志。
7. beginDrag/updateDrag/finishDrag/cancelDrag：输入PointerEvent，输出局部drag状态及正常完成的一次savePreference；字段dragRef包含pointerId、captureElement、startY、startTop、startRatio、moved；suppressClickUntil为单调时钟截止点。cleanup幂等，释放前先清dragRef防lostpointercapture重入。
8. moveByKeyboard：输入ArrowUp/Down和当前bounds/top，输出移动12px的top及ratio；不处理其他键，Escape走关闭逻辑。savePreference仅在ratio实际变化时调用。
9. workspace.prefs：字段serverValues/localValues包含pinned、collapsed、progressYRatio；sequence、dirtyFields（字段集合）、saving、error、loaded。复用workspace.version与单飞队列，禁止增加第二version或账号generation；初始化和换代一处重置。
10. setWorkspacePreferences：输入Partial的三个偏好字段及当前ticket，输出本地状态更新与sequence推进；校验布尔和finite ratio，pinned=true强制collapsed=false，手动收起设pinned=false。sidebar按钮调用原store入口，内部最小联接prefs更新。
11. loadWorkspace扩展：输入现有ticket/forceFresh，输出既有boolean；在原校验与readSequence门禁内读取prefs。flushWorkspace扩展输入输出保持现有boolean，构造字段级patch、校验响应version及已提交偏好值，逐序列确认；原recent候选备份与删除条件不变。
12. savePreference：输入规范progressYRatio，输出Promise<boolean>；委托controller的set/save prefs入口，正常拖动结束立即排队；多键事件由单飞自然合并，无每pointermove网络。retryPreferences无输入，输出保存结果，不触发最近会话路由恢复。
    ensureWorkspacePreferences：输入当前AuthTicket，输出Promise<boolean>；有效账号、当前generation且prefs已loaded时返回成功，否则复用现有loadWorkspace的同代在途GET与发布门禁；过期/无账号返回失败，不做导航/写入/候选消费。WorkspaceLayout effect依赖account.generation，在有效userId/token时调用；卸载不取消共享GET，结果发布仍由ticket门禁控制，局部提示不得被旧finally清除。此入口不创建第二缓存、版本队列或generation。
13. Chat挂载：为legacy-chat、composer外围加稳定ref/类名，必要时WorkspaceLayout只公开topbar测量ref或稳定data标记；不改现有scrollRef、preserved/restored effect依赖、恢复按钮分支和发送门禁。会话换切时hook取消活动拖动但从账号prefs保留ratio；摘要随新bucket自然更新。
14. Playwright数据结构：独立场景记录viewport、账号代号、route、build/hash、矩形bounds、持久化GET值、request计数、截图与结论。受控网络/DOM数据与真实账号HTTP分开目录，不记录密码/token。

## 验收与交接

DOM/纯逻辑先RED再GREEN：4px边界、350ms、12px、有限ratio、cancel/capture、Escape再开、null/0、账号换代晚响应与单版本交错；不能用缺导出或收集失败充RED。

浏览器必须正式HTTP React而非HTML原型：真实mouse hover入口→卡片→离开、touch点开/关与handle拖动不滚页面、真实pointer捕获拖出边界/取消、键盘focus/Escape/再开；拖动请求计数证明无snapshot/messages读取；切会话草稿/锚点不变；真实登录A保存/GET读回→退出→重登同A恢复→B默认/独立偏好，不能以仅mock PATCH替代。

深链恢复单列验收：有效登录A保存sidebar取消固定/收起及ratio后，直接reload `/profile` 与 `/knowledge`，HTTP GET返回的sidebar应用、ratio缓存且URL不变、无workspace PATCH；随后进入Chat沿用已缓存ratio。DOM受控并发验证Layout与Chat初始化仅一个同代在途GET、候选未消费、初读慢响应不覆盖新手势、账号换代晚结果不回填。真实浏览器深链恢复与受控并发结论分别记录。

尺寸1440/1024/760/600/481/480/390，每宽正常高度与450短高；检查默认/收起/展开、浮卡两态、账号/输入/导航可达、无横溢、modal层级、中文长标题、无断点长URL、200%字号、focus可见、prefers-reduced-motion。记录未通过/未验证，不能“截图存在”即算通过。

最后完整npm test/build、完整OCR preview所有文件+rule全覆盖、独立新鲜审查（按既定Sol方式由主会话派发）、最小修复后复验；README/账本由主会话串行更新实际能力/未验边界。明确文件add、本地commit、核实际SHA，不amend/push，不宣称Task13完成。
