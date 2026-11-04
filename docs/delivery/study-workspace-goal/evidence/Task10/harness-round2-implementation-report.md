# Task10 验收辅助第二轮修复报告

依据：独立PASS修复计划50b71ac121e422970141537ff1be3c8bf2b5c78f213e3e474db4dde68a4a19bd；已读取原代码审查和本轮计划/审查。仅修改两辅助源码/测试及本轮证据。未改app/web/README/依赖/账本/用户数据，未stage/commit，未启动模型/真实服务/浏览器，无子代理。

## P1 硬链接与文件身份
解析路径先限制runtime，之后existing_file_identity要求存在文件为常规文件且st_nlink为整数1；读取metadata失败则拒绝。双存在路径额外samefile核查，无法判断或为同文件均拒绝。独立控制文件读取也复核链接数，创建目录后、控制文件创建前及真实app/database导入前重新进行完整路径/身份校验。
真实os.link测试仅用pytest tmp_path为各测试新建唯一目录内自有空文件；模拟study_agent.db亦为空自建，runtime外别名也只在该tmp_path内。不使用--basetemp，不对真实数据库建链接。不删除/清空既有数据库或覆盖凭据。测试实证nlink=2、samefile=True。覆盖DB外部别名、DB/control别名、control外部别名、无法确认link数、stat异常、samefile异常/同文件、配置读取后发生外部变更且敏感初始化前拒绝，不改环境或创建控制文件。原新路径与合法单链接复用回归继续通过。
验收目录仍需独占；不声称抵御同权限恶意进程最后检查之后的替换。

## P2 chat故障配置代际
新增内存chat_generation；每次成功POST控制配置含drop_chat_responses（含相同值/0）同步递增，其他参数不递增。目标请求在调用内层前捕获代际，真实completed/persisted=true后仅同代且尚有计数时消费。旧代完成透传真响应，不消耗新配置。同代并发限量、失败/异常/超限不消费保留原行为。
新增真实延迟ASGI确保A已进入内层后才更新控制配置，覆盖drop1→0→1和drop1→1；A完成200且新计数仍1，B完成503才消费。另覆盖仅view/workspace更新不使现请求失效、旧代失败不破坏新代。

## 实际RED/GREEN与终态

所有本轮Python测试均走原生require_escalated（第一轮已有默认沙箱asyncio初始化阻塞诊断），无重复启动或挂起句柄，无sleep。

- RED：在原冻结源码CC26A0...上先追加2项真实行为测试，原生pytest -q -k "hardlink or reconfigured"；pytest exit1，2 failed/9 deselected；硬链接原代码未拒绝、旧A返回503而非200，均为业务RED，不是缺模块或环境错误。日志harness-round2-red.log。修改实现之前已保存源码真实副本harness-round2-red-source-report.md及同期SHA日志harness-round2-red-sha.log，非重建。
- 针对性GREEN：pytest -q -k "hardlink or reconfigured or identity_checks or rechecks or generation or non_chat"；pytest exit0，6 passed/9 deselected。日志harness-round2-targeted-green.log。
- 完整GREEN：pytest -q；pytest exit0，15 passed in 0.31s，包含既有9项回归。日志harness-round2-green.log。
- py_compile两个文件 exit0；日志harness-round2-compile.log及harness-round2-verification.log。
- 每次exec工具最终shell exit0，以上pytest/compile子退出码由shell明确输出并记录，未以shell0掩盖RED子exit1。

RED同期SHA：
- 实现CC26A0CF479D34D8C91C877F6C0922867279EC41BD3D138305EEC40FA7083DF7
- 测试（先追加2项后）3E0B97FD3F484AD2610E39DABA498B9E7550E1E1D9B930215A0802FC035284D0

最终冻结SHA：
- acceptance_harness.py DFEC2186E73A4E84E2B8BB373E466659FE1136991053EAC69B88A5F88C238875
- acceptance_harness_test.py 90FBD856BB385CA553799AD933BFC799BA0DF33D9EC92055EC3F562012235158

后续门槛：等待原独立reviewer范围复审P1/P2及回归，且辅助与主产品代码均审查PASS后才允许真实隔离功能验收。本轮dummy测试不证明真实模型、数据库FK/持久化、浏览器接收或PostgreSQL重启。冻结后不再改两文件。
