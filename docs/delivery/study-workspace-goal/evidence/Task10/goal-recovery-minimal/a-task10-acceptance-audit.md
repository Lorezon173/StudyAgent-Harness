# Task10 / 方案 A 完成条件独立证据审计

日期：2026-11-03，最终补证更新。结论：**真实行为验收门槛已有足够证据；交付尚未收口，继续 IN_PROGRESS，不提前标 DONE。** 局部修复、独立产品审查、365项测试和构建、三个真实浏览器受控核心场景、真实问答/退出恢复/在途切换/专用PG重启/本人API读回/跨账号UI，以及新增实际代理连接失败和本机草稿恢复均成立。Task8最终26项后端与测试冻结哈希和当前全部一致，已有HTTP/SSE对照可直接引用。剩余仅最终文档、账本与明确本地提交；没有依据重开产品代码审查/修复或重跑相同验收。

## 审计边界与证据等级

逐项对照 A plan 全部 28 个复选项、原 Task10 计划第 5/6 节及 v1.2 精确消息/功能验收要求。核对本目录当前证据及历史失败/修订关系；[证据快照清单](a-task10-acceptance-audit-inventory.json)列捕获时间、当前证据文件及哈希（审计自身文件不纳入自指纹）。关键日志/报告、原始运行 JSON、各阶段 DOM/storage JSON 已核；选择关键截图人工查看。没有声称逐张重新视觉审计所有重复历史截图，也没有重新运行产品测试、OCR、浏览器或 SQL。这里只新增审计文档，不改产品或台账。

- **RTL/受控模型**：可确定性验证交错与状态，不能证明真实浏览器、模型或数据库。
- **真实浏览器＋合成网络**：可证明实际按钮、可见状态、精确副本与请求数，fixture persisted=true 不是数据库保存。
- **真实浏览器＋实际隔离后端/模型**：证明正常页面行为；屏幕没有消息 ID，不能独自替代权威 API 消息 DTO。
- **专用 PG SQL/重启指纹**：证明数据库中的身份、正文、状态与重启持久性；不是浏览器或原始 HTTP 结果。
- **实际第二账号 HTTP**：证明对应接口拒绝；不能替代第二账号页面实际不展示数据。

报告/截图的真实执行事实由其执行者记录，本审计独立比较一致性及覆盖，不将转述升级为再次独立执行。

## A 计划逐项映射

编号依原计划每任务复选项顺序；“通过（边界）”表示在已批准合同与明确证据等级内成立，不表示任意组合全部实测。

| 项目 | 状态 | 证据与裁决 |
| --- | --- | --- |
| 1.1 工作区/第七轮 46 项与事实冻结 | 通过 | a-implementation-report、a-source-before、a-final-source-before/after、a-ocr-task10-scope/source-after；相对第七轮仅两个产品/测试文件变化，未覆盖未知工作区改动 |
| 1.2 实际页面建立已有冲突并双重查 | 通过 | a-existing-conflict-red.log、Chat 业务测试审阅；final-02 的 initial-conflict/A-held/B 请求与事件独立补真实浏览器受控证据 |
| 1.3 新可信冲突后旧成功不能覆盖/清副本 | 通过 | 原实现 RED 收到 matched 而期望 inconsistent；GREEN、产品 OCR；final-02/conflict 的 B-returned、A-returned 警告/禁发/精确副本、POST=1，随后主动一致重查恢复 |
| 1.4 503/游标/source/主动重查对照 | 通过（边界） | final-02 network/cursor-loop 三核心及 RTL 对照通过；source 相邻可达路径有警告/其他副本保留，特定已有冲突双候选组合按下节裁决不适用，不冒称组合已运行通过 |
| 1.5 真实浏览器按钮交错 | 通过（受控） | browser-final-02 三核心各有阶段 JSON/截图/事件；Playwright 驱动独立真实 Chrome，API/认证合成，不能替代任务 5 |
| 2.1 真实业务 RED 再最小修复 | 通过 | a-existing-conflict-red.log 的业务断言失败，不是缺模块；实施记录与冻结对应 |
| 2.2 完整事实分域/提交冲突/不误清理 | 通过（静态＋RTL＋受控浏览器） | a-ocr-code-review 重点 1/2/4，final-02 核心交错；未修改产品协议 |
| 2.3 自身域实例 finally/生命周期 | 通过（静态） | 独立产品 OCR 核完整身份 key、current/account gate、自身实例回收；不是线上故障注入事故证明 |
| 2.4 身份/source/其他 writer 必要回归 | 通过（分层边界） | 365 测试含既有身份/来源/其他请求/UI sequence，产品 OCR 明示低层注入及未实测全组合；immutable completed 合同与不可达入口不要求绕过按钮穷举矩阵 |
| 2.5 定向 GREEN、两个冲突发布分支 | 通过 | a-existing-conflict-controls/writer、a-chat-suite/a-final-suite，产品 OCR 对同 ID 合并冲突及 catch、独立活动资格均核 |
| 3.1 原排序/游标/跨页停止合同 | 通过（代码合同＋既有测试） | 实施记录、产品 OCR 对原 v1.2 与服务端分页核对；此次不把任意异常 fixture 当真实服务端缺陷 |
| 3.2 网络/游标/版本落后/无基线分类 | 通过（受控＋静态） | 已有测试/产品 OCR；final-02 增补真实浏览器 network/cursor 观察，其他分类没有冒称真实故障 |
| 3.3 合法缺失与原措辞歧义 | 通过（保留原合同） | 独立计划/代码审查已记录两段措辞，未有实际响应触发需改语义；不据此增全历史扫描 |
| 3.4 不为异常页新增框架 | 通过 | 实施/审查范围保持局部，无 B 产品实现证据 |
| 4.1 全前端测试/构建及退出码 | 通过 | a-final-suite.log：11 文件/365 项、exit=0；a-final-build.log：TypeScript/Vite、exit=0；冻结哈希一致 |
| 4.2 冻结并取得完整 preview | 通过 | a-ocr-preview、a-ocr-task10-scope；46 实际范围与原白名单、第七轮、preview 映射，而非只审两个改动 |
| 4.3 全规则/逐项覆盖及报告 | 通过（指定范围） | 产品 OCR：46/46；preview 可审 1677 中13 reviewed/1664逐项skip，规则遗漏0；不宣称工作区全覆盖。设施 v1/v2/v3 独立审查保留 |
| 4.4 OCR 错误纪律 | 通过 | 实际命令/原句柄、退出码、完整文件捕获有记录，没有以失败冒称成功 |
| 4.5 发现先裁决/不扩范围 | 通过 | 产品 PASS；设施初审 M1 Needs changes 经观察合同复审及 v2 PASS 解决；首轮活动门禁漏项经计划审查与 v3 PASS 后才跑 final-02，不改产品解锁 |
| 4.6 根 README 当前结果同步 | 缺证/未完成 | 已追加产品 OCR 与首次问答，但仍称浏览器/退出/切换/重启等未完成、设施准备中，未反映 final-02 与后续真实证据；需最终同步 |
| 5.1 隔离实际环境与启动边界 | 通过 | a-real-services-preparation：57544 前端→57543 后端，随机专用 PG 子库、模型进程配置、迁移、专用账号；非原用户库 |
| 5.2 真实注册/创建/草稿/问答/保存读取/刷新重登 | 通过 | 首轮截图/真实LLM日志、PG completed/persisted与消息正文、刷新/重登及B草稿；新增a-real-owner-api-readback与原始responses记录重启后session/snapshot/messages/四request/profile/B均200，八消息全部字段/四保存response与PG相符。原始私有访问日志先有一次profile POST、A session POST，后有B session POST；同画像两会话的页面与API身份相符，支持B复用本人既有画像。没有专门保存选择框截图，不要求因此重做创建 |
| 5.3 正常退出保存及重登恢复 | 通过（操作＋持久化） | a-real-refresh-logout-verification：未保存草稿实际点击退出→登录页→同账号重登恢复；PG draft精确值/view version3/workspace最近会话及截图相符。日志中A的view-state PATCH 200及后续auth/login 200提供辅助；没有时间戳/关联ID，不能将特定PATCH强行绑定某个点击或证明精确毫秒顺序。操作事实＋重登＋PG已足够支持原保存门禁行为，无需重跑 |
| 5.4 真实在途 A→B、完成归位 | 通过（时钟边界） | 第四轮CUA切换15:39:34.961–35.034，PG该真实请求完成事务时间15:39:40.362；B后态精确草稿无A消息，回A AX含ID8精确回复，B数据库无消息。第二/三轮单独不够的历史结论保留，不再要求重复同类慢请求 |
| 5.5 失败/冲突/断开连接及恢复 UI | 通过（分别分类） | final-02覆盖消息矛盾、503读取失败、游标回环及按钮恢复；新增a-real-connection-failure-recovery与失败/恢复txt/png覆盖实际Vite代理连接关闭→保存连接失败、完整原文/重试出口→恢复后实际HMR reload→发现本机草稿并由用户选择恢复→草稿已保存；本人真实API/PG精确草稿、版本2→3、消息0。不是browser offline，也不是无刷新手动retry；没有推测客户端尝试总数 |
| 5.6 真实 PG 重启后相同消息可读 | 通过（数据库＋页面） | a-real-pg-restart-verification：指定容器实际restart、新连接稳定排序全字段指纹前后一致；a-real-after-pg-a.txt/png见8消息，B txt/png见精确草稿。后者证明页面恢复，仍不冒称原始API DTO |
| 5.7 第二账号 API 拒绝及实际 UI | 通过（两个独立账号事实） | a-real-cross-account-api记录user2接口拒绝；新增a-real-cross-account-ui.png显示另一新账号task10_b_ui_20261103自有无主题、直访A为无权访问/无权写入，无A标题画像/正文/草稿。该UI账号不同于API的user2，不合并成同一次会话；页面A ID来自主动输入URL，不是继承敏感内容。txt仅记录AX无变化，主要UI证据为截图＋主会话操作事实 |
| 5.8 分类汇总、实际结果与不冒称完成 | 未完成 | 当前证据分散，原A复选框全未勾；需主会话按本审计更新结果矩阵/账本及README，保留source不适用、未验收故障与真实教学质量限制 |

## final-02 汇总 failed 与 source blocked 的裁决

final-02/report.json 的真实值仍是 status=failed：conflict/network/cursor-loop=pass，source-change=blocked；不能改写原报告或说整轮全绿。本审计复核三核心阶段 JSON：conflict 的 A-returned 仍禁发且保留冲突；network/cursor 的 activity-pending 禁发、activity-recovered 可发且无待确认；三者末态另一 writer 的精确 key/value 与初始相等，POST=1、errors/failures为空。C事件在两恢复对照中确有held/release/network-finished/render-observed。首轮 final-01 的两个失败由保留门禁下的真实重查步骤补齐，旧失败没有抹除。

**source blocked 不应永久当产品失败。** 产品独立 OCR 已给出真实支持调用链：已有inconsistent的主按钮不带source；候选入口遇existing inconsistent即退出，无法由这两个候选按钮制造该指定组合。A计划明确允许不可达证据替代伪造内部状态。因此主会话可将“已有inconsistent双候选source”业务验收项裁决为“不适用：支持入口不可达”，引用 a-ocr-code-review 的对应行证据；相邻source场景仅证明真实候选入口、精确变化警告/其他副本/POST=0，不说它证明了不适用组合。保留脚本 blocked 和汇总failed，不需要为了显示全绿改产品、删场景或再造矩阵。缺的是最终汇总对该边界的明确裁决，不是新产品机制。

## 真实证据的充分性与限制

- **真实模型与保存**：a-real-first-turn-verification 有 gpt-6-luna critic/tutor 日志、PG响应与消息精确比较；首次页面截图与正文一致，后续第四轮有AX文本精确匹配。回复仍反问，和“不要先考我”的需求有教学质量限制；原Task10不把另一窗口意图路由质量纳入完成条件，必须如实记录，不升级为本轮修复。
- **在途切换**：第四轮具有动作时钟、完成事务时间与最终桶隔离的组合证据；PG now()非精确接收/提交时间、主机/容器未独立校时的限制保留。接受其支持实际后端在切换后完成的常规验收强度，不重启无限“再一轮”测试。第四轮显示B既有编辑草稿保持，不声明该5秒窗口内又完成了新编辑。
- **重启**：实际数据库restart和新连接全字段指纹是真实PG证据；健康200只作辅助。PG后真实reload A与切B恢复补齐页面；新增a-real-owner-api-responses.json独立记录重启后实际HTTP及全部比较结果，补齐本人权威API身份/ID/正文。API日志的首次错误画像结构KeyError没有生成证据，成功重读已单独记录，不冒称首次脚本即通过。
- **退出**：实际操作记录＋PG持久草稿＋重登页面足以支持退出恢复行为；私有后端日志的A PATCH与login仅辅助，不用无时间戳日志重建不存在的精确请求关联，不以增加同类问答代替证据。
- **连接故障恢复**：a-real-connection-failure-recovery.md记录只停专用Vite，原后端/JWT/PG保持；输入AX完整原文、连接失败与重试出口，恢复后HMR自动reload，出现本机完整草稿，用户实际选择后saved。本人API和PG最终草稿相同、view version=3、消息0，已补齐剩余实际连接失败恢复行为。累计三条B PATCH 200无时间戳，不能断言其均属于该轮或推算所有失败尝试；本验收不需要伪造次数，也不声称验证browser offline或无刷新retry。

## Task8 HTTP/SSE 既有同冻结证据复核

只读核对 `Task8/round3-code-freeze-manifest.json` 的26项现有源码/测试SHA256，差异为0；并执行 `git --no-pager diff --no-ext-diff --no-textconv --no-color --name-only c23763d4fa0f2dfb951c4c65ef3670af4ac41d4e -- app tests`，输出为空。没有重审未变化产品，也没有重跑测试。

已实读原始 `round3-commands.md` 与日志末尾：`round3-affected-primary.log`为100 passed，`round3-affected-routes.log`为12 passed/1既有warning，`round3-pg.log`为20 passed。routes明确包含test_chat_stream_error/test_chat_stream_realtime，primary为会话事务及workspace API，原Task8独立round3-code-review已核HTTP/SSE变体与原问题关闭。因此原Task10“检查Task8 HTTP/SSE对照仍通过”可引用这组**相同后端/测试冻结的历史实测＋本次哈希复核**，不得说本轮又跑了132项或当前真实模型SSE。无需为文档收口再跑一遍。

## 剩余必须完成的最小动作：仅交付收口

1. **最终分类报告与README**：统一链接本审计及全部实际证据；区分RTL/受控浏览器/真模型/PG/API/UI、代理连接失败与browser offline、HMR reload恢复与无刷新retry；明确source不适用而非产品失败，首轮失败及final-02原汇总failed值原样保留。保留教学质量、时钟、无关联日志等实际限制。无需额外故障矩阵或重跑已成立行为。
2. **台账与计划进度**：按实际结果更新A复选项、progress/status/current_round/next_step/evidence/review；没有全部交付前不提前DONE。Task13范围不能由这组Task10结果自动勾选，B依旧独立候选。
3. **明确本地提交**：按已授权范围精确暂存Task10文件，保留用户README既有修改及任务外工作，记录真实本地commit和交付账本。审计查验时HEAD为 `6d5829303f639e50ca15b11a9c8f79ee093caff1`，Task10 commit=null/evidence空/review=null，current_round仍旧round1 IMPLEMENTING；这些是待文档交付者更新的状态，不是行为验收失败。没有依据再改产品或扩新框架。

审计过程中已补齐的最小动作不再重复：本人权威API读回和重启后应用重连已由a-real-owner-api-readback.md与a-real-owner-api-responses.json完成；实际跨账号UI已由a-real-cross-account-ui.png及主会话操作事实完成；连接失败恢复已由a-real-connection-failure-recovery.md、实际截图/AX及API/PG终态完成。API账号和UI账号不同，分别记录通过，不拼接为同一执行会话。

上述剩余动作仅是原计划的文档/账本/提交交付，不授权修改产品。B仍为独立TODO候选，本次不补IndexedDB/FIFO/全历史扫描。行为门槛已成立，文档与明确本地提交完成前Task10/A仍保持交付未完成；Task13整体验收不能由这组Task10有限证据自动勾选。
