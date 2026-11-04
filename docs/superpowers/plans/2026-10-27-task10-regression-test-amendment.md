# Task10 原工作区测试迁移增补计划

来源：Task10 v1.3已独立PASS、实际中途全量日志 evidence/Task10/round1-interim-full-test.log，11文件114项中7失败（3个测试文件）。原计划允许更新WorkspaceLayout测试，另两既有测试文件需要明确纳入。用户已授权完成Task10并要求每步计划、子代理计划审查、编码、子代理代码审查、功能验收；本增补必须独立审查PASS后方可修改两文件。

## 第一层：目标和边界

当Task10 /chat恢复最近会话、路由切换加载snapshot与workspace GET/PATCH后，旧测试必须从Task9的临时占位语义迁移到真实Task10语义，原有数据隔离、去重、导航和创建约束不降低。仅额外允许修改 web/src/components/workspace/NewSessionDialog.test.tsx 与 web/src/components/workspace/SessionSidebar.test.tsx；WorkspaceLayout.test.tsx已在主计划白名单。不得修改产品代码或既有终稿/依赖以使这些测试通过；新增测试需模拟实际DTO与真实底层fetch，不能以宽松mock隐藏多余请求或产品缺陷。

## 第二层：职责、契约及数据流

NewSessionDialog测试的fetch按真实URL和HTTP方法区分workspace、分组、画像、创建会话、snapshot与view/workspace保存；新建成功后以其真实ID进入实际选中会话，断言对应snapshot加载与可见状态，不再期待“内容暂不可用”；保留原profile_id/body、单次POST防双击、真403、部分成功绑定、账号换代/旧结果/关闭焦点等全部业务断言。snapshot fixture要包含真实owner/session/profile、消息、view_state和pending字段，异常路径显式报错。

SessionSidebar测试的fetch按URL/方法独立路由workspace GET、sessions group请求及必要snapshot，不依赖首个全局fetch总是group请求。根分页和每组cursor的请求参数与响应分别隔离；保留同名画像分组、并发页/去重/顺序、loading/失败/重试/空态、未分组及无障碍断言。mock不应静默对未知路径返回成功；必要时记录未预期请求并断言为空。

WorkspaceLayout既有白名单下只迁移旧占位/固定次数测试到当前DOM与路由；原独立账号代际、固定/收起、导航、logout守卫均不删除。各失败先核实际原因：若以真实DTO mock后仍出现跨账号更新、丢用户数据、意外POST或错误UI，则记产品缺陷、停止削弱测试，按原Task10修复流程处理。

## 第三层：实施与验证

- 用已保存的中途失败日志定位两文件各一失败；实际断言/请求顺序与响应体从当前源码及后端schema核实，不预先认定7项全是过时测试。
- 调整路由化fetch、真实DTO与实际Task10断言；明确断言输入不泄漏到错误session、账号变更时仍无第二次创建、消息来自snapshot，避免仅检测组件存在。所有原有效断言保留或等价加强；不能仅删除失败断言。记录修改前后测试数量与每个迁移断言的原因。
- 分别运行NewSessionDialog、SessionSidebar、WorkspaceLayout定向测试至原session终态；保存原日志与退出码。失败若暴露新产品缺陷留证，不改产品以绕开审查。主Task10最终全量测试/build和Task8对照由主实施者统一执行，不重复开启仍在运行的命令。
- 独立代码审查必须审计本增补计划和三个测试diff，确认没有删除原保护；之后真实功能验收。主会话最终统一README与明确文件暂存。现阶段没有修改两个测试文件。
