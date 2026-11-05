# Task12 M3测量前提最小修订 Implementation Plan

> **For agentic workers:** 使用superpowers:subagent-driven-development；先计划独审，再Terra单文件实施、collect、OCR增量复审，最后全部25项真实运行。

**Goal:** 在浮卡展开且实际两倍字体的同态下采样M3 baseline。
**Architecture:** 只补现有用户hover准备，不改产品或测量函数合同。
**Tech Stack:** 现有Playwright。
**Spec:** [已批代表计划](representative-acceptance-plan.md)M3；[最新24/1结果](exit-escape-round1-run-summary.md)及`playwright-exit-escape-round1/run.log`。

## 第一层：目标与边界

最新25项24通过、1失败、0跳过；M4整链及真实HTTP通过。唯一M3停在466行regions读取不存在的详情。已核现源：标题自然mouseleave及菜单操作后未重开，regions却无条件读取详情。这是测试状态前提缺口，不是产品缺陷。只改`web/e2e/workspace-layout.spec.ts`，原25合同、长数据/字号和失败证据保留；不新增场景或框架。

## 第二层：事件与测量phase合同

baseline前依次真实trigger.hover、等待expanded=true/详情可见、调用原scale并核每项actual约等于baseline×2（原1px容差），再regions。scale沿原恢复inline→一次性读原字号→统一倍增流程，新挂详情必须取未覆盖基线，不对已放大继承值再乘2。

末尾原再次展开/scale/after保留，使前后测量同态。滚动、锚定、横溢、reduce、截图、链接和画像正文断言均不删；regions不得返回fake/null跳过详情，不force或隐藏浮卡。原自然离开收缩行为不变。

## 第三层：语句职责、字段与验收

- [ ] 独审PASS后核旧spec SHA256 `0941574DD7EB1ED5A586D882E1FDA3C11F3AB201AFAA13DFB8A9A31F6949C3D5`；另存before/after完整文本、增量与20项hash，预期1变19同，以实际为准。
- [ ] 仅baseline前补上述展开/可见/scale校验；复用原变量与观测对象，可记baselineFonts，不加新函数或产品字段。等待失败照实报错，原finally附件清理不变。
- [ ] collect仍25；单文件OCR增量复审覆盖前提、字体恢复及所有后续断言。现产品/单元源hash未变，则沿用已冻结428项/build退出0，不重复全量；若碰其它源码先报告，不自动扩范围。Node类型限制保留，不改依赖或冒称E2E tsc通过。
- [ ] OCR PASS后隔离HTTP全25到终态，新目录`playwright-m3-baseline/`；30秒主动检查，不sleep。必须实际到达原M3全部后段，旧24不继承；失败不删断言，成功附件核实际存在。真实HTTP非skip，受控压力与持久化分列。

仅新增本文，待独审；未改README/status/源或旧计划，未stage/commit。Task12仍进行中，Task13及有限边界保留。
