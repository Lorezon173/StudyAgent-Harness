# Task10 A：真实浏览器受控交错最小设施三层设计（raw）

日期：2026-11-03。A 已获用户批准；本补充只落实 A 任务 1 已要求的真实浏览器受控交错设施，供独立计划审阅，不代表已安装依赖、编写脚本或完成验收。产品代码、测试、后端及用户数据均不在本补充修改范围。

设计来源：`docs/superpowers/plans/2026-11-02-task10-goal-recovery-minimal.md` 任务 1，以及 `superpowers/frontend-ui/2026-11-02-task10-goal-recovery-minimal-raw.md` 的真实页面复现合同。原隔离服务计划 `docs/superpowers/plans/2026-10-27-task10-acceptance-harness.md`、round2 与现有 `acceptance_harness.py` 仅支持保存503及成功回包丢失，不支持精确消息页交错；本补充不向其添加接口。

## 第一层：模块总览

### 目标、失败案例与完成条件

已有 jsdom/RTL RED 证明两个实际重查均从 inconsistent 启动时，旧成功曾清除新可信冲突；A 局部实现报告记载修复与365项回归，但明确尚无真实浏览器证据。本设施用本机真实 Chrome 或 Edge 加载当前前端构建，实际输入、发送、连续点击“重新查询”，只在测试网络层控制响应，补齐这个证据缺口。不新增用户可见行为。

完成条件是真实按钮交错及对照各有独立证据：初始冲突；A消息页挂起；B从同一冲突启动且先返回；A后返回；可见警告、禁发、原文和本人/其他writer副本保护；不重复POST；后续主动一致重查可恢复。B分别为可信矛盾、503、游标回环；source失效单列，必须实际选择候选并经现有页面入口，不直接调用controller。不可达时保留证据及未完成项，不通过内部函数制造通过。

### 技术选择、依赖与架构衔接

父会话已探明系统Chrome/Edge可用，Node/Python未安装Playwright/Puppeteer；此处不把该信息当成功启动证据。选择仅在专用临时工具目录安装固定版本 `playwright-core`，复用系统浏览器，避免下载浏览器。版本先从官方registry查询并核对Node兼容性，安装前写入运行清单；版本不能悬空使用latest。产品`web/package.json`、lock文件、Python依赖和全局npm配置均不改。

独立Node脚本只做三件事：loopback HTTP提供`web/dist`静态文件及SPA回退；Playwright新建独立非持久context；context.route拦截测试API并显式释放两条消息响应。不存在测试控制HTTP API、真实后端代理、数据库、模型或通用故障框架。正常页面生命周期及网络客户端仍是真实前端。浏览器内只允许初始合成认证和精确localStorage候选操作，不替换fetch、不注入store/controller、不改bundle。

官方文档说明Playwright支持context.route及品牌浏览器渠道；这不能证明当前桌面浏览器工具具备网络拦截。先运行本工具环境的launch/route/close探针，成功后才运行场景：[网络路由](https://playwright.dev/docs/network)、[品牌浏览器](https://playwright.dev/docs/browsers)、[启动选项](https://playwright.dev/docs/api/class-browsertype)。系统浏览器不兼容时先报告具体错误，不自动下载/升级浏览器或改接用户窗口。

### 边界与白名单

规划交付仅本raw及配套plan。未来实施只新增 `docs/delivery/study-workspace-goal/evidence/Task10/goal-recovery-minimal/a-browser-controlled.cjs`；日志、截图、报告位于同目录新建`browser-controlled/<run-id>/`。临时依赖、工具package/lock/cache位于`.superpowers/runtime/task10-browser/<run-id>/tool/`；允许现有前端构建生成`web/dist`，源码及产品依赖不变。根README由主会话集中同步。

每次创建全新run目录；已存在则拒绝覆盖。不使用用户浏览器profile，不连接现有服务，不读取真实token、密码、模型配置或数据库。API仅同一测试origin的显式方法/路径白名单；未知API及外网请求阻断并记失败，不回落真实8000/8001。静态HTTP端口由本次进程选择可用loopback端口并记录，冲突不终止其他进程。

## 第二层：子模块概述

1. 环境与生命周期：输入绝对工具目录、系统浏览器路径、dist目录和证据目录；输出仅属于本轮的HTTP句柄、browser/context及版本/哈希清单。依赖安装失败、浏览器启动失败、dist缺失均停止；不自动扩大依赖或修改配置。
2. 固定场景网络：输入当前源码合同的profile/session/workspace/request/message固定对象和两个挂起route；输出逐事件时序及受控响应。内存仅保存本轮fixture、捕获的真实POST request_id、阶段、A/B route、请求计数；不持久化产品状态。每阶段只接收预期请求，超时/非预期请求显式失败。
3. 实际页面行为与副本：输入页面与场景；输出DOM断言、截图、同origin合成候选前后快照。用户输入和所有重查均通过真实控件；读取storage不等于产品内存状态证据，报告以可见警告/发送按钮/答案和精确副本对照证明行为。
4. 证据与收尾：输出带环境分类、退出码和未完成项的报告；finally关闭自己context/browser/HTTP句柄，待释放route由关闭context终止。保留失败现场日志及截图、临时工具和证据供复核，不递归删除目录、不触碰既有窗口或服务。

## 第三层：子模块详细实施设计（文字合同，无实现代码）

### 环境函数、数据与错误

`prepareRun(options)`：输入项目根、run-id、工具目录、浏览器绝对路径；校验路径解析后在白名单，输出dist文件SHA256、源码清单SHA256、Node/工具/浏览器版本及运行目录。拒绝缺失构建、目录复用和越界，不读用户凭据。

`startStaticServer(distRoot)`：输入已校验目录，输出loopback origin与close句柄。仅GET/HEAD静态文件，扩展名对应正确MIME；不存在的无扩展SPA导航回退index.html，缺失JS/CSS返回404；拒绝路径穿越；`/api`绝不代理或返回SPA成功页。serve当前dist前记录构建及产品源码一致性，不使用未知旧dist冒充当前实现。

`openBrowser(toolRoot, executablePath, origin)`：从专用工具目录解析playwright-core，启动自有浏览器实例及新非持久context，禁Service Worker；返回browser/context/page。先对合成probe路径route.fulfill并从页面读取探针值，证明路由确实工作。关闭探针页面后开场景新context，禁止共享场景storage。

### 固定响应与受控顺序

`installScenarioRoutes(context, scenario)`：输入conflict/network/cursor-loop/source-change之一，返回捕获事件、POST计数、A/B到达及释放句柄。固定合同参照`web/src/test/setup.ts`、`Chat.test.tsx`末尾已有inconsistent双重查及来源失效用例；不import测试模块，以免引入Vitest钩子。保存显式JSON fixture于脚本内，不添加产品类型或接口。

路由只允许当前origin下GET workspace-state、GET sessions分组、GET指定session snapshot、GET指定request、GET指定session messages；PATCH view-state/workspace-state按原expected_version合同响应；POST chat从真实请求体捕获本轮request_id、payload并回completed/persisted=true合成响应。request GET必须完全匹配捕获身份与baseline，messages的role/id/turn/content保持相同对象，只按场景改变已声明的冲突正文、503或cursor。未知session/request/method立即abort并记失败；所有响应明确标“测试合成”，不得记为真实保存。

初次正常发送后snapshot返回同ID矛盾回答，使页面实际出现冲突。进入交错阶段后按显式阶段而非全局snapshot次数分配old/new cursor：点击A后等待其指定messages请求已被捕获，截图仍冲突，再点击B并等待新messages请求；B先释放、观察UI结果，再释放A。StrictMode初始化重复GET仅在初始化阶段返回幂等一致fixture，不将意外额外请求悄悄当作下一次重查。有限Promise门闩只服务两次请求，每个捕获/释放有单调事件序号；无队列、任务调度框架或sleep。

`releaseMessage(which, outcome)`：输入A或B及预置结果，仅允许对应已捕获route释放一次；输出已完成响应事件。重复/未到达释放为设施失败，不误记产品失败。用有上限的浏览器条件等待及请求事件等待；单步默认15秒、整场景90秒，超时报告阶段与最后事件；耗时进程由主会话每30秒主动检查，不使用强制sleep。

### 真实控件、副本和场景断言

`runScenario(page, controls, scenario)`：输入独立page与路由控制，输出本场景pass/fail/blocked及DOM/storage证据。先在该测试origin设置合成认证三键，再进入真实`/chat/A`；输入“双重查问题”、实际点击发送。认证fixture不证明注册登录或后端权限。捕获POST后复制应用实际写出的request候选作为本人副本快照，按现有schema/key规则构造独立writerId/writeId的另一writer副本；该操作仅影响本context合成storage，记录其完整原文/身份，不改应用writer。

可信冲突场景在B后及A后均断言警告“已保存的消息与请求不一致，请检查”、发送disabled、本人/其他writer精确键和值仍在、原文未丢、POST chat始终1；随后实际新重查返回一致，断言正确回答显示及既有发送合同允许的恢复，另一writer副本仍完整。503/游标回环先断言复核失败与禁发，A正确后应显示正确回答并恢复；保留每阶段截图和请求次序，不仅记HTTP状态。

source-change使用现有prepared候选UI及已有source失效案例的精确候选合同，在实际选择/查询之后、响应之前只替换或移除该候选，A/B仍经按钮启动；核来源警告、恢复出口、保留其他writer及零额外POST，且来源失效响应不作为新可信冲突阻止有效旧成功。若当前入口无法在已有inconsistent起点下保持该交错，则记录具体UI和网络不可达证据交主会话裁决，不改store、不以相邻场景冒充该组合通过。

`captureEvidence(page, label)`：输入阶段名，输出PNG、可见文本/disabled状态及仅测试恢复namespace的键值快照，写入本轮证据；不导出认证token、不保存HAR或通用trace。日志只记方法、相对URL、阶段、request身份、response状态/fixture标识及单调序号；测试原文允许记录，禁止真实用户文本/凭据。页面异常、未知网络、断言错误须保留并使退出码非零。

`finishRun(resources, result)`：输出脱敏report.json、中文报告及退出码；标明browser/controlled-network，不记真实模型、SQLite或PG成功。只关闭本次句柄；清理失败单列并报告自有PID，不kill同名浏览器。保留本轮工具环境与证据，若后续需删除仅精确验证路径后单独执行。

### 实施闸门与后续边界

独立计划审阅PASS后，先安装/验证工具并实施单文件脚本，再独立代码审阅PASS后运行真实按钮场景。任何新增产品依赖、浏览器下载/系统设置、新后端控制接口、修改app/web源码或用户数据库都超出本补充，应单列决策，不能自动执行。UI不可达或设施失败不触发产品修复；实际范围内行为失败回原A计划核实。

本补充只完成A任务1的真实浏览器受控网络证据。真实模型正常/慢生成、正常退出、真实保存故障、PG重启持久化、跨账号拒绝仍按A任务5独立验收；本脚本的persisted=true完全是fixture，不能作为任何数据库写入证据。

## 2026-11-03 补充：有限浏览器观察合同

主会话已接受常规端到端观察边界，不要求规范级函数退出证明。本补充只细化既定设施的 B/A 观察，不引入 CDP、产品接口、私有 store/controller 读取或通用框架。

- 释放 B/A 前，以对应 held route 的精确 Request 对象身份注册响应及请求结束等待，不仅按 URL 匹配。释放后须确认该 Request 的 response 属于同一身份、状态码及完整正文等于预置 fixture，并成功发生 requestfinished；请求失败、正文读取失败、身份/状态/正文不符或超时均停止，不进入下一阶段。
- 精确网络结束后，在页面依次等待一次独立任务轮转及两次 requestAnimationFrame，给予响应 Promise 后续处理、React 提交与渲染机会；这些有限事件屏障不使用固定 sleep。随后才执行既定 DOM、禁发、本人及另一 writer 精确副本、POST=1 断言并保存证据。
- B 的上述观察及断言通过后才释放 A；A 的上述观察及断言通过并保存证据后，才允许实际按钮主动 recover。不能用已存在的同一警告立即满足条件，也不能用 route.fulfill 完成代替观察屏障。
- 事件明确记录 B/A 各自的 network-finished、render-observed，释放仍单记 release；不得将这些事件命名或解释为 handled、confirmCompleted 已返回或业务处理已确定完成。

证据边界：client 的末页 JSON 消费后，confirmCompleted 的消息核对至同步状态处理及 finally 路径没有后续 await，因此上述屏障适用于本有限 fixture 的常规浏览器验收；网络结束和帧屏障仍不是业务函数退出的规范级因果证明。A 被较新冲突丢弃时没有独有 DOM/storage/network 事件，本设施不声称凭黑盒观察证明该函数已退出。确定性响应处理时序由既有 RTL 竞态测试另行验证；真实浏览器报告仅声明“指定网络完成并经过页面任务/渲染屏障后，观察到冲突仍保留”。两类证据分别报告，不能相互替代；合成网络也不证明真实持久化。本补充尚未实施或运行，须交原独立审查者复核。

## 2026-11-03 补充：network/cursor-loop 会话门禁根因与验收漏项

首轮 `browser-controlled/20261103-a-browser-final-01/report.json` 记录 conflict=pass、network/cursor-loop 在发送 enabled 断言失败、source-change=blocked；两失败场景的 `recovered.json` 均显示“正确回答”“会话状态待确认”“重新查询会话状态”和 sendDisabled=true，另一 writer 副本仍在。首轮失败记录及证据完整保留，不改写为通过。

裁决依据：`workspaceController.ts:817–818` 每次 confirmCompleted 推进 activityObservationSequence；较新 B 已启动后，旧 A 的观察序号已过期。行859与865允许旧 A 的消息匹配成功，同时将过期会话活动观察保守置为 uncertain；消息 matched 不等于会话门禁 clear。`Chat.tsx:32` 提供实际“重新查询会话状态”按钮，调用 controller 行881–913 的既有重查；身份一致、无活动请求且观察仍有效时，行907–910 才清除此门禁。这是已有合同，当前失败定位为验收漏掉真实会话重查步骤，不据此修改产品或降低恢复要求。

本补充细化前文“按既有门禁恢复”，network/cursor-loop 不再直接从旧 A 正确答案推断发送应立即 enabled：先在原网络/任务/双帧观察屏障之后，断言正确答案可见、会话状态待确认可见、发送 disabled、另一 writer 精确副本完整且 POST=1，并保存该中间态（本人匹配副本按既有成功清理合同处理）。随后实际点击“重新查询会话状态”，捕获该次精确 snapshot Request 并按同一身份/状态/正文及页面观察屏障验证，返回身份与版本一致且 active_request_id=null 的既定合成 snapshot；禁止内部 store 注入或合成 success。最后仍必须断言正确答案、发送 enabled、待确认门禁消失、另一 writer 精确副本与 POST=1；不能删除或改成期待禁发来通过。出口不存在、不可点击、snapshot 不一致或最终仍禁发均记真实失败，回主会话裁决，不自动补产品分支。该步骤尚待独立复审及执行，不将首轮失败改称已解决。
