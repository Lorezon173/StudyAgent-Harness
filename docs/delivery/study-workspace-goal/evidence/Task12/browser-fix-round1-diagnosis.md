# Task12 修订轮浏览器失败诊断

修订轮原始记录见 `playwright-fix-round1/`：22 项中 19 通过、3 失败、0 跳过；其中 14 个尺寸用例通过，同账号切会话受控用例通过。以下复现均为独立浏览器和内存受控 API，不等同真实后端验收；未修改源码、测试、配置或原始证据，诊断用 Vite 已停止。

## Escape：已复现 hover 时事件未进入浮卡

原用例第 129–131 行仅 hover 入口和详情后按 Escape，期望 `aria-expanded=false`，实际仍为 `true`。独立受控复现记录 hover 后 `document.activeElement` 为 `BODY`；Escape 的实际事件目标是 `BODY`，不在 `.floating-profile` 内，展开状态仍为 `true`。`useFloatingProfile.ts` 的 Escape 处理在 `containerEvents.onKeyDown`，由 `FloatingProfile.tsx` 绑定到浮卡容器，BODY 上的键盘事件不会冒泡经过该容器。

对照复现：聚焦手柄后按 Escape，事件目标为手柄，浮卡关闭、焦点回入口；鼠标移出再进入可重新展开。该证据与已批准的 hover 状态 Escape 可关闭合同不符，属于产品事件覆盖缺口。最小方案应在浮卡展开且适当的交互上下文中接收 Escape，保留原关闭、焦点和重开行为；需要明确与原生 dialog 或其他覆盖层的优先级，避免抢走其 Escape。仅给测试手动聚焦会掩盖已确认的 hover 路径，不能替代修复。具体实现须先经计划与独立审阅。

## ArrowDown：受控复现已在下边界

原第 154–155 行先完成向下拖动和取消，再按 ArrowDown，期待向下超过 11px；原日志为原位置 214.25，实际仍为 214.25。按相同操作顺序的独立受控复现记录，拖动后 `progress_y_ratio=1`；卡片 bottom 为 668.203125，等于 composer top 676.203125 减去 8px，向下剩余空间为 0。ArrowDown 事件确实到达手柄，卡片不动；随后 ArrowUp 移动 12px，从 y=214.25 到 202.25，并发出 ratio=0.9085714285714286 的受控 PATCH。

因此，已复现的失败由测试要求在边界外继续向下移动造成；原失败未记录 ratio 或矩形，不能把独立复现数据冒充原现场记录。最小测试调整应先记录或构造有余量的方向，继续严格验证 12px 移动、请求和边界夹取；不能只删除或放松键盘断言。此结论不证明所有视口和方向键场景均通过。

## 真实 HTTP 深链：响应体不可读取，捕获来源未证实

原第 235–237 行在 `reload()` 前建立 `waitForResponse`，等待 pathname 为 `/api/workspace-state` 的任意 GET，待 `await page.reload()` 返回后才调用捕获响应的 `json()`；浏览器报 `Network.getResponseBody: No resource with given identifier found`，提示响应对应的页面已离开。截图位于 `/profile` 且侧栏已收起；这些事实不能证明此处三项偏好全部已从本次 reload 响应正确恢复。

该监听窗口从 reload 前开始，匹配条件没有标识请求所属文档；理论上可能命中前一页面仍在途的 GET，也可能捕获正确请求但等待 reload 后读取响应体时已不可用。原日志没有请求身份、发生时间和文档关联证据，无法裁定是哪一种；上述原因属于待验证的可能性，不应当作已复现根因。

建议将观察窗口限定到 reload 的新文档，并在目标响应到达时立即读取并保存 body，记录请求开始、主框架导航和响应的先后与关联；不能把旧页面晚到的 GET 计作新文档证据，也不能吞掉读体异常。保留对三项偏好的响应内容比较、URL 和侧栏 DOM 状态、无 PATCH、之后进入 Chat 检查 ratio 的断言。独立服务端 GET 可作补充，不能代替浏览器恢复证据。本次真实用例在此停止，后续 B 隔离等步骤未验，不能据此前步骤推断通过。
