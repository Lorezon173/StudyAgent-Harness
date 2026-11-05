# Task13 首笔产品与验收提交核验

对象 `b7484f13bc31b6e29fafb905e5a77219d75e4c41`，直接父提交 `3c9fae413309731b181e72475cf71c980531e7e4`。对照[修订后明确清单](local-closeout-commit-manifest.json)，使用 Git NUL 分隔路径逐项比较：提交 59 项，清单 59 项，无额外或遗漏；清单 SHA256 `dbc97bf28b7608ab5ec2c3d0fc40f221048ea98919a32acaabc60ff3392b0ae4`。首笔不含 status/progress，核验时索引为空。

17 项产品与测试增量逐项计算工作树 SHA256，并用 Git 路径过滤规则计算规范化 blob 与提交中的 blob 比对，均与冻结候选、实际提交一致。README 提交内容只含知识库鉴权一处更正和 Task13 自有段；资产清单提交内容仅 Task13 自有追加。

首笔 HEAD 对工作树的 README、资产清单差异分别为用户原 162 行、34 行；与私有原始差异基线的增删行多重集及非空增删序列一致。Git 空行 hunk 对齐可改变空白行位置，按零上下文 Git 差异比较时分别有 46、34 个序列位置不同，不称全部增删序列逐行一致。README 去除自有末尾段并逆向恢复鉴权旧句后，与私有原文件逐字节一致，原文件 SHA256 `d47d3713c1dc4beace439e9e502f6af852088186b99775caab992697f27ad6f7`；资产清单当前文件的原长前缀与私有原文件逐字节一致，其 SHA256 `41462288eb1a53ebf320126a3a77047b9e2242fa497ec951ac8d29701248de1b`。原文、私有快照及差异基线不纳入提交。

对首笔 `git diff --check HEAD^ HEAD` 实核并非零诊断：四处均为已审冻结文件末尾空行，分别位于 `web/e2e/workspace-real.spec.ts:230`、`account-final-web-test.log:52`、`local-closeout-plan.md:41`、`real-browser-first-run-summary.md:12`。首笔暂存检查曾因此停止，主会话核对仅此四项并决定保留冻结源码和原始证据后完成提交；本记录不称空白检查全通过。固定 Ruff 全仓 599 条既有诊断、exit 1 与此为独立限制。

Task13 功能与证据通过范围见[验收审计](acceptance-audit.md)及[交付记录](../../../2026-10-23-workspace-acceptance.md)。本记录仅核验首笔，第二笔白名单仅 `docs/delivery/study-workspace-goal/status.json`、`docs/delivery/study-workspace-goal/progress.md` 和本文件。第二笔实际 SHA、直接父链、三文件、账本引用、空索引及用户差异须在第二笔完成后核验；不预写第二笔 SHA，实际核验前不正式结束当前 goal。

原 Task13 状态账本中的 `node-ui-plan.md`、`node-ui-plan-review.md` 和 `environment-preparation.md` 目前仅在工作树，未纳入首笔提交；原有引用保留为本地历史依据。当前核心验收、候选覆盖及审阅证据在首笔提交中可读取；这三个历史文件不加入第二笔白名单。

本地交付范围止于 Task13，账本将 SC-004 记 COMPLETE；平台原生 Goal 当前仍为 active，主会话须在第二笔成功实核后独立更新，本文不预填第二笔 SHA 或平台会计。
