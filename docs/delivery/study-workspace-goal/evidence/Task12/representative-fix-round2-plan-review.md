# Task12 剩余两项代表性修复计划独立审阅

日期：2026-11-04。结论：**PASS（仅计划）**。未发现有实际依据的范围或可执行性阻断问题。

计划SHA256 `6114708169FE479C751C4B7C3CB433AC1A84499DC360DA4A495468C9D9631ADB`，两次只读核对一致。完整读取计划、`representative-fix-round1-run-summary.md`及诊断，结合前轮已读raw/代表计划，核对当前WorkspaceLayout全文、Sidebar/浮卡/退出相关CSS、M3/M4实际测试段及既有回调合同。

## 两项最小修订

- **M3仅改真实输入前提，有复现依据。** 诊断证明标题End已到末尾，中心被展开浮卡拦截，但可见未遮点命中标题；真实移到该点自然mouseleave收卡后wheel能读回开头。计划限定viewport相交rect内有限候选和elementFromPoint，未找到则失败；不force、不改pointer-events、不程序隐藏或移浮卡。全文/End/真实2倍字号、锚定、独立滚动及后续链接正文断言均保留，并明确不宣称持续展开时标题wheel已验。未据中心hover失败改产品几何。
- **M4处理已复现的提示可操作缺口。** 现role节点确为shell普通flex子项，没有fixed/层级，诊断实际main由390挤到74、留页点命中遮罩。计划将exitError内原role节点放进fixed/inset0/z60静态wrapper，脱离flex并高于遮罩30、sidebar40及账号菜单45；panel有界、可内部滚动、长文本/按钮不裁切。现shell未设置导致fixed被局部包含的transform等属性，方案与当前结构相容，具体尺寸/命中仍待功能验证。
- **业务与焦点边界保持。** 退出仍是同一exitError条件、非原生dialog/同label、原三按钮和原requestLogout/备份/留页回调；留页autoFocus是局部挂载初始安全焦点，无新state/effect/global listener/modal框架。背景无点击dismiss，不通过修改mobileOpen或隐藏遮罩避开竞争。保持抽屉仍开、浮卡展开前提下的真实touch命中/Tab/Escape/留页/草稿链；不添加完整focusTrap或aria-modal承诺。浏览器及必要Layout语义测试须证实这些结果，静态计划不代替。

## 范围、门禁和证据

范围复核保留已过23行为，只补剩余两项hard；白名单为Layout静态包装/autoFocus、退出CSS、E2E与必要Layout测试。Chat、Sidebar、hook、队列、后端不改，不扩场景/矩阵。20项冻结清单已含相关目标，本轮另存完整before/after及哈希，不覆盖历史快照。先完整web回归/build、实际collect25及OCR本轮全部修改增量独审，PASS后才运行正式全部25项，原23不能直接继承。

成功附件须实际落盘，人工字体/受控503与真实HTTP分列；新后段失败先记录并范围复核，不继续加特殊机制。Task12仍IN_PROGRESS，Task13、B候选与L1–L4保留。本PASS不代表退出提示已可操作或M3后段通过。

本审阅仅新增本报告；未改计划、源码、既有证据或账本，未执行功能、未提交。
