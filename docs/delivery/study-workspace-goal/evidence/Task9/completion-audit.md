# Task8/Task9 范围完成审计

范围SC-003：本地分支codex/frontend-ui-optimization，完成Task9即止。Task8功能提交c23763d，检查点c91b60b。五项批准原始文件不得改。

| 要求 | 已检查权威证据 | 结论 |
|---|---|---|
| Task8事务、租约、恢复、隔离、独立审查和README | 已提交Task8 evidence、README、status实际SHA；round3 Approved，主要100/旧路由12/真实PG20/helper6；全量既有检索失败已披露 | PASS |
| Task9每轮三层计划及独立PASS先于执行 | round1 v1.3计划及round1-plan-review-v1.3；round2计划SHA6cdeea6e…及独立plan-review，RED在PASS后 | PASS |
| 真实API DTO与路径 | api/{sessions,profiles,workspace,knowledge}.ts、types及实际app/api路由；workspace契约测试6项；ProfileDetail.profile层级、组内解包与cursor互斥 | PASS（契约层，不代替真实联调） |
| PATCH/FormData、204、结构化错误与旧client行为 | client.ts及12项实际测试，422字段、409code、JSON/连接/超时/traceback、凭证端点401与保护401区分 | PASS |
| 唯一账号代际、同步bootstrap和显式同token换代 | auth.tsx、workspace.ts及auth5/store7实际断言；StrictMode首子树请求身份正确，晚401隔离 | PASS |
| 会话桶与account/request/load票据 | workspace.test.ts中的A/B消息草稿分离、旧load/request、缺桶、旧账号拒绝；无持久化宣称 | PASS |
| 根与组分页独立、错误重试、去重 | sessions.ts、workspace.ts及SessionSidebar3项并发/错误/空态；根cursor与两组cursor分离、null耗尽不复活 | PASS |
| 纸感布局、左下账号、右上入口、唯一公共导航 | 终稿及index.css/WorkspaceLayout/SessionSidebar/App；四路由DOM测试，Knowledge/Profile仅去旧nav | PASS（Task9壳层） |
| 默认固定、收起取消固定、选择保留与宽度边界 | store初始pinned/open，布局测试；CSS264/170与<=480抽屉，main flex/min-width0占位；真实几何留Task12 | PASS（CSS/DOM，不冒称浏览器验收） |
| URL为选择真源，选中历史诚实出口 | syncRouteSelection与App SelectedSession；布局测试返回/chat/选A/选B，无snapshot并不呈现旧消息 | PASS；真实恢复/发送Task10 |
| 创建已有/新画像、两POST屏障、部分成功绑定 | NewSessionDialog7项；真实DTO body/id、403、同步双击、防账号切换、绑定锁定重试与显式重选 | PASS（fetch契约层） |
| Login旧结果隔离、StrictMode、防双击及R9-I1 | round2 RED3fail、GREEN14、实际Login订阅及14项回归；旧request pending先释放、新busy/error不受旧续体影响、普通通知不取消 | PASS，round2独立复审Approved |
| 完整前端测试、正式构建、冻结 | round2-final-test 8文件66/66，build tsc/Vite exit0，diff0；38hash验证前后相同，仅允许两文件改、36不变 | PASS |
| 独立实现审查及阻断关闭 | round1报告唯一R9-I1；Dialog猜测已真实排除；round2限定diff复审Approved，R9-I1 ADDRESSED且无新阻断 | PASS |
| README准确与用户原修改保护 | README已选择性提交，原README142/asset34仍未暂存 | PASS |
| 明确文件本地提交、实际SHA、账本、Goal完成 | 功能提交edaa7c3468fc3f7a500949d6a92f8ee63f3c1eb0；实际分支与HEAD已核，Task8 c23763d保留，status记实际SHA，Goal待工具关闭 | PASS（功能及提交）；Goal关闭为最终记录动作 |

没有真实后端JWT/模型/浏览器验收；这些属于后续批准任务，不以本阶段测试代替。所有范围要求已逐项核实；Task9功能提交edaa7c3468fc3f7a500949d6a92f8ee63f3c1eb0含72个明确文件和README选择段落。未进入Task10、未发布。当前仅关闭原生Goal与记账检查点，未宣称M3(Task9–12)全部完成。
