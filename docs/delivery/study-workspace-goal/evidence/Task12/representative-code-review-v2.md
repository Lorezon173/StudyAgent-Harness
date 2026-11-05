# Task12 代表性补证两项修订：OCR 增量复审

2026-11-04。结论：**PASS（仅本轮单文件静态增量复审）**。原报告两项 Medium 均已关闭；未发现有实际依据的新增问题。未运行功能，不代表25项浏览器通过，也不代表全工作区审查通过。原 `representative-code-review.md` 保留。

## 冻结范围与证据

唯一目标 `web/e2e/workspace-layout.spec.ts`：before SHA256 `6B4147488CEDC9A640DF6867A340CE98638505A0BF6F1630BB3F5B10AEF69413` → after `294B268A46EDC19726D04DEF3C2E46E38A72757E56BEB836C477205DD1BB87E0`。两份 `representative-review-fix-{before,after}.txt` 实际字节哈希匹配，after与当前文件逐字节相同；增量与 `representative-review-fix-increment.diff` 对照。原前448行完全未变，本轮仅修改M3最后结果断言及M4准备/动作/前提/清理，原22项主体、M2和M3其余压力断言未变。

已读修订计划及独审PASS、交接、原两项问题、修订完整上下文，并对照前轮已完整审阅的原文件与必要Profile/ProfileDetail及浮卡触摸/展开/Escape合同。修订计划实际SHA256为 `9AEC3F302E68D2DC03992D9CB0C264D27D5FDB7CA5845B5C640116D6E6155F49`，与授权一致；不重新审查无变的大产品范围。

## 两项关闭核验

1. **原M1：关闭。** 新449–453行限定 `.profile-page .profile-grid` 成功区域及其 `.profile-panel`，核grid可见、页内读取提示消失且无alert，再核正文header h2长主题、当前长n1、节点列表对应标题和select=p1。侧栏同名主题不在该定位范围内，无法再满足正文成功断言。原href、真实Tab/可见焦点、命中、Enter与含p1/s1的URL断言保留。当前节点与列表定位都限detailPanel，不误命中同页摘要。链式h4文本定位可匹配其根元素，已核本地Playwright文本引擎实现，不将其臆断为无子元素导致失败。
2. **原M2：关闭。** 新457–488行以独立390×844、hasTouch/isMobile context创建page，安装相同fail-save fixture；真实trigger.tap后立即经phase断言expanded=true及详情可见。抽屉开启、菜单开关、抽屉关闭/重开、退出提示出现、Tab到留页按钮和Escape前后均核展开，未中途强制重开。点位命中仍由elementFromPoint验证，并用该page的touchscreen.tap真实操作；未引入鼠标hover建立展开前提。原提示可见、Escape不偷焦、留页、路由和草稿断言保留。page/fixture/helper/截图均绑定新context；context创建后纳入try/finally，附件写盘/attach外再嵌套finally关闭context，即使前置失败或附件失败也执行关闭。可选api仅用于准备失败后的安全日志，未跳过正常fixture调用断言。

新日志只增phase、expanded、详情可见性与受控焦点身份；原命中/几何/受控view-state方法记录保留。输出仍用固定文件名及 `testInfo.outputPath`，无不受信路径拼接、令牌、密码或Authorization输出。实际成功附件是否保留仍须运行后核查，本次没有新截图成功证据。

## 新 OCR 范围、规则及覆盖

实际重新执行：

`ocr delegate preview --format json --exclude 'docs/delivery/study-workspace-goal/evidence/**,docs/rag-work/evidence/**,.pytest-tmp*/**'`

只排除已授权的三个非产品/非测试日志产物目录，来源计划和交接仍读作上下文。preview活句柄 **21910正常exit0终态**，未超时重启。原始 `representative-v2-ocr-preview.json` 保留完整mode、文件和3914条excluded及原因；stderr另存。模式 **workspace**，total_files=4011、reviewable_count=97、excluded_count=3914；原输出无from/to/commit/merge_base字段，清单明确记null，不虚构引用。

目标仍以 `(web/e2e/workspace-layout.spec.ts, added)` 被 `default_path` 排除，本轮按唯一授权目标采用 **explicit_scope_override** 并独立取规则；未跟踪新文件按合同全文与冻结快照增量审阅，不冒称Git提交区间。

默认97项全部取规则：使用独立argv路径，每20项一批，5批exit0；目标单独规则exit0。全部规则组内容已读，原始文件 `representative-v2-ocr-rules-{0,20,40,60,80}.json`、`representative-v2-target-rule.json`、`representative-v2-rule-manifest.json` 留存。逐项 `(path,status)`、规则组、review/skip及具体理由见 `representative-v2-ocr-checklist.json`：Task12既有core源码/设施仅按需作上下文，状态账本由主会话维护，其余历史交付/设计/诊断与两处修订无关；没有悄悄漏掉产品或测试。

| 统计口径 | total_files | reviewed_files | skipped_files | coverage_rate |
|---|---:|---:|---:|---:|
| 默认OCR可审范围 | 97 | 0 | 97 | 0% |
| 本轮单目标 | 1 | 1 | 0 | 100% |
| 合并有效清单 | 98 | 1 | 97 | 1.02% |

## 结论边界与结束核验

Critical、High、Medium、Low：本轮均无新增有实际依据的问题。M4 role dialog与仍打开的移动抽屉/遮罩是否实际可命中，继续留给原真实命中断言运行观察；不能据静态怀疑定为产品缺陷，也不能弱化展开、命中或Escape断言来通过。503仍为受控注入，不是真实后端故障。

交接collect日志为25项、exit0，只证明收集；未重跑功能、build或类型检查，既有Node声明限制不因collect而消失。原core22历史通过不继承为本版本25项通过。L1–L4有限覆盖、Task13及B候选边界保留。

结束重核 **19/19冻结文件与交接after一致**，其中另外18项均无变化，见 `representative-v2-review-freeze-check.json`；目标最终仍为 `294B268A46EDC19726D04DEF3C2E46E38A72757E56BEB836C477205DD1BB87E0`。只写本报告及OCR审查证据，未修改代码/测试/配置、未stage/commit。README已在前轮检查，本次依单报告范围由主会话在后续实际验收后统一更新，不宣称Task12完成。
