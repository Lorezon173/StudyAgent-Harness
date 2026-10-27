# Task9 round2 独立范围代码复审

结论：**Approved**。R9-I1 **ADDRESSED**；本修复范围内未发现新阻断。

## 审查对象

- 已读取 round2 三层计划及独立 PASS，计划 SHA256：6cdeea6e2ef12a33ae72a250a2a1cb053ff88d73c051b90f12c6009dc2edbf9d。
- 已读取 task9-round2-fix.diff 的全部两文件变化、review manifest、source-freeze、实现报告，以及 RED/GREEN/最终测试/构建日志。
- 独立重算当前全部38文件 SHA256，与 round2 manifest 完全一致（38 files，0 mismatches）。限定差异仅 Login.tsx、Login.test.tsx；36文件仍是上一轮已审对象。
- 未重跑全套，未修改产品/测试/索引/README，未委派。此结论仅范围复审，不冒称重新逐行审查未变的整个工作区。

## R9-I1 关闭依据

Login既有layout effect内同步订阅唯一workspace代际。监听本地observedGeneration只做变化检测，不成为认证真源；普通通知立即返回。当前mount收到真实换代时，先失效submitSequence，再同步释放busyRef并复位busy/error，恢复不依赖旧Promise完成。原current()的mount/sequence/generation全条件保留，因此旧成功、catch及finally均不能改新提交。

测试真实经过当前受保护API401→AuthProvider.logout→workspace换代，不mock内部判定。新增参数化成功/失败两项在旧登录仍pending时先断言恢复、再发新请求，随后释放旧结果并确认新busy/认证/URL不变；另项确认新重试的错误保留且能第三次登录。它们在原实现的401后恢复断言确实失败（RED3失败/11通过），修复后14/14通过。没有把RED尚未到达的后续分支冒称已失败复现。

## 新破坏核对

- 同generation普通sidebar通知不解除提交锁；新增测试确认仍只有1次POST。
- 自有成功保留清busy→login→navigate同步顺序；login通知只清本地提交，没有login后的current检查，故不会吞掉有效导航。既有正常登录/注册及新重试成功测试覆盖实际token/代际/URL。
- 旧请求finally不能释放新忙锁，因为sequence与generation已失效；未放宽current。
- cleanup先退订，再按mount保护失效票据并释放ref，不在卸载后setState。StrictMode setup/cleanup/setup沿用现有真实组件测试，避免遗留订阅/锁。
- 未改auth/client/store/App/Dialog、凭证端点401裁决、依赖或后端，不扩大Task10。

## 验证证据与限度

round2-red.log：3 failed / 11 passed；round2-green.log：14/14；round2-final-test.log：8 files、66/66；round2-final-build.log：tsc及Vite成功。冻结记录各对应终态退出码；当前源码hash与该冻结对象一致。没有新增修改需要再次测试。

真实后端JWT/数据库/浏览器几何仍非本轮证明范围。Approved允许主会话继续README、完成审计及明确文件本地提交，不表示Task9记账与提交已经完成。
