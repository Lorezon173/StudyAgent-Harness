# Task9 round2 实现报告（冻结）

只修复 R9-I1；计划 SHA256 6cdeea6e2ef12a33ae72a250a2a1cb053ff88d73c051b90f12c6009dc2edbf9d，独立PASS已读。先载入karpathy-guidelines，核两允许文件与round2-base一致后编码。

## 变化

仅 Login.tsx / Login.test.tsx。原布局effect建立workspace代际订阅，代际变化同步递增本地submitSequence、释放busyRef、复位busy/error。相同generation通知直接返回。cleanup退订、失效mount/sequence、释放忙锁，不在卸载后setState。现有current()全条件不放宽；正常自有成功仍清busy→login→navigate，未加login后的current检查。没有新全局计数或接口。

## RED与验证

原session46100真实RED终态exit1：14项中3失败/11通过，新增两种旧结果及新错误测试均在401后旧请求仍pending时发现按钮仍disabled。未将后续尚未到达的断言冒称RED覆盖。

最小实现后原session45672定向GREEN exit0，Login14/14。新增4项：迟到成功/失败参数化2项（旧请求未settle先允许新提交，旧结果不得改新busy/认证/导航）、新重试失败在旧错误到达后仍保留且可第三次登录、同generation普通sidebar通知不解除双击守卫。既有10项保留，均在StrictMode真实AuthProvider/MemoryRouter框架，仅mock fetch。

完整测试原session22840终态exit0：8文件66/66；原session52058正式构建exit0：tsc+Vite通过。git diff --check -- web exit0。日志见evidence/Task9/round2-{red,green,final-test,final-build,final-diff-check}.log。

最终38文件hash与全套/构建前完全一致；与round2-base比较仅允许两文件变化，其余36不变。证据round2-source-freeze.json已保存；现冻结源码等待独立范围复审。

未修改README/账本/auth/client/store/App/Dialog/依赖/后端，未stage/commit、未委派。未做真实后端JWT/数据库或浏览器几何验收，不扩Task10；已发POST取消本地提交不承诺服务器回滚。
