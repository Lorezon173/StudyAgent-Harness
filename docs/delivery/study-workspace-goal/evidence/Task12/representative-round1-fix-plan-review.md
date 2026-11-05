# Task12 代表性首轮局部修复计划独立审阅

日期：2026-11-04。结论：**PASS（仅计划）**。未发现有实际依据的可执行性或范围阻断问题。

计划 SHA256 `F55DEC17511648F07E956166ECA8954D614AC148744E3C05648E0A891185460C`，两次只读核对一致。已完整阅读计划、25项首轮汇总及诊断，对照前轮已读原raw/代表计划，并核现有Chat、SessionSidebar、MessageBubble、CSS及M2/M4实际测试入口。读取MessageBubble仅为核CSS可覆盖的DOM上下文，不授权修改该组件。

## 范围与根因复核

计划明确回应连续测试前提修订的扩张信号：原core22本轮仍通过，新3链属于原键盘/短高可达/覆盖层hard合同；保留必要证据但不增用例矩阵或通用框架。区分M2/M4测试前提与M3实测布局问题，说明静态wrapper/class增加为何必要，保留已有工作成果。不是仅以再审一轮代替范围裁决。

- **M2**：Escape后的内部转移不立即反开与离开后重新focus可开是两个阶段；诊断实际是重新进入手柄、inDetails=false。计划仅修阶段期待，保留关闭详情卸载/不可Tab、当前内部关闭及重开/鼠标后段合同，不改hook来迁就测试。
- **M4**：两个实际关闭入口（主步骤及末尾条件分支）均要求exact，排除遮罩同名前缀。触屏持续展开、命中、Tab/Escape、留页/草稿与finally不弱化。role dialog后段此前未运行，计划正确不预修产品层级或先关抽屉绕过路径。
- **M3**：依据同人工2倍样本实际标题761.5px/chat375px、fill后send中心506.41超450、列表0/footer越界及长URL横溢；准确区分输入前与输入后，不把scrollIntoView能触及当作底部锚定通过。与本次hard验收直接相关，未扩到极端全组合。

## 布局方案与实际结构

1. Chat已有确定高度的纵向flex；标题最大25%且≤96px、8px间距及全文滚读可限制挤占，composer不收缩、消息min-height:0可分配剩余正高度。标题静态tabIndex/可见focus使全文可键盘读取，不截短文案。现有scrollRef/hostRef/composerRef位置及恢复effect、message id、草稿/锚点算法均冻结，新增仅class/可访问属性。
2. Sidebar现有aside为固定视口高度纵向flex。顶部静态wrapper与列表/footer兄弟关系可实现局部滚动而不裁账号菜单；450高扣22px顶部padding约428，35%约150，加footer实测200与14间距及列表48约412，预算在当前样本有依据。max-height而非强制高度，正常短内容可自然高度；具体box模型仍须浏览器rect验证。footer不进入顶部滚动区，aside不加overflow裁剪，account-actions定位于footer并设高于浮卡5的层级，方向符合现有DOM。不是对未知role dialog的提前修复。
3. MessageBubble现为外flex+内maxWidth75%的现有子树；在Chat命名空间约束min-width和普通长词换行可局部覆盖，不需改Markdown解析或组件。pre/code单独保留white-space:pre、pre内部横滚，避免把代码行强行断开或撑宽整消息区。composer表单flex/input min-width0与原组件输入/发送结构一致。

## 验证合同与交付边界

同长fixture、600×450和逐元素实测2倍字体保持，不减字号、删文本、隐藏状态/按钮或使用transform；消息/列表滚动前后的锚定基线要求相同字体与保存状态，避免新增状态行导致合理布局变化被误判。原输入前记录继续作诊断，紧邻fill后的composer/send rect及命中另存，不能互相替代。

计划保留原core22及3链，实际collect25后经必要单测/build、完整快照/哈希和本轮全部修改OCR增量独审，再跑完整功能。新增浏览器证据须核标题全文滚读、列表/消息正高度与独立滚动、composer/footer可视及可操作、长URL不外溢/代码pre内滚、字体/reduce/末尾链接及正文；失败不自动扩大白名单。必要组件测试仅验证结构语义/既有回调，不用jsdom矩形冒充布局验收。

本PASS不代表静态限额已实际解决样本问题，也不继承旧22通过为本轮通过。Task12仍IN_PROGRESS；L1–L4、Task13及B候选边界保留。本审阅仅新增报告，未改计划、代码、既有证据或账本，未执行功能、未提交。后续文档检查点快审独立进行，不阻本计划结论。
