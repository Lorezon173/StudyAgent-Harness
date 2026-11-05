# Task12 M3 baseline 状态准备独立 OCR 增量审查

日期：2026-11-04。结论：**PASS（仅单文件静态增量）**。未发现有实际依据的问题；无 Critical、High、Medium 或有明确价值的 Low 发现。不代表 M3 后段、全部25项功能或整个工作区审查通过。

## 单文件修订核对

已读取 `m3-baseline-state-plan.md`、计划独审 PASS、实施记录、原 `exit-escape-round1-run-summary.md` 及原 run 调用栈，结合原代表合同与本审阅前轮已完整读取的 E2E/浮卡上下文。计划 SHA256 实核为 `BF88FF6691815467DC8280D77BC6BD520F15817E61DC8BC40430634E779A5DAC`。

原run在旧spec `:466` 调用 baseline 的 regions，内部必读条件挂载的 `.floating-profile-content`，但标题自然mouseleave和菜单操作后此前未重新打开；实际栈等待该详情超时。浮卡源码按 open 条件挂载详情，鼠标自然离开可收缩。这个调用前提与原代码一致，不能据此把产品正常收缩定为缺陷，亦不能将当时尚未执行的后段记录为通过。

当前唯一改动在 `web/e2e/workspace-layout.spec.ts:466–467`：真实 trigger.hover，等待 expanded=true/详情可见；复用原 scale，记录 baselineFonts 并核实际字号约等于各自原基线两倍（保留1px容差），然后原 regions 采样。未对 regions 返回 fake/null 或跳过详情，也未 force、隐藏卡片、程序关闭、减字体或改产品行为。

原 scale 在读取任何基线前先恢复全部已有覆盖节点的原 inline 字号，然后一次性读取当前DOM字号，再统一乘二。新挂详情没有旧覆盖标记，其已有祖先在取基线前已恢复，因此不把祖先两倍继承值再乘二。新增准备与原末尾 reopen/scale/after 同态，不用关闭态 baseline 比较展开态 after。hover或可见性失败仍直接失败，不吞掉错误。

完整 before/after 与现源逐字节核对，并用完整文本序列比较确认**只有原第465行后插入两行**，其余522行原样保留。原25项、600×450长数据、人工逐元素实际2倍字号、标题全文/End/真实wheel、命中、代码块、独立滚动与锚定、no-overflow、reduce、截图/附件、链接及目标画像正文断言均未删改；M4焦点 guard/留页完整链和其它24项不变，不重开已通过的guard审查或完整Tab陷阱要求。

## OCR 范围和覆盖

新执行 `ocr delegate preview --format json --exclude 'docs/delivery/study-workspace-goal/evidence/**,docs/rag-work/evidence/**,.pytest-tmp*/**'`，同一进程71859主动检查至 exit0，没有超时重启。完整 [preview](m3-baseline-state-ocr-preview.json) 为 mode=`workspace`、repository=`D:/backup/basic_file/Program/LearningAgent/StudyAgent-Harness`、total_files=4287、reviewable_count=98、excluded_count=4189。该版本没有 from/to/commit/merge_base 字段，未臆造引用；本轮目标在workspace为 untracked added，按全文审查，不伪造相对HEAD的文件diff。

完整 excluded `(path,status,exclude_reason)` 保存在 preview。自定义参数仅排除列出的非产品证据/临时日志目录；目标 E2E 的 default_path 排除显式覆盖。98个默认reviewable全部按Python argv每20路径一批取 rule（5批均exit0），E2E另单独取rule（exit0），结果为 `m3-baseline-state-ocr-rules-1.json` 至 `-5.json` 与 `-target.json`。目标适用TS/React系统规则，已结合类型/null、异步/错误、资源与行为覆盖核对；未把未变的大产品机制重新扩大为任务。

所有99项的 `(path,status)`、规则组映射和 reviewed/skipped具体理由见 [ledger](m3-baseline-state-ocr-ledger.json)。E2E reviewed；前轮已审且本轮冻结未变产品不重审，其余既有历史交付材料/状态产物超出唯一测试增量，逐项注明 skipped。工具 excluded 的4189项单独保留，不混入99项分母。

| 范围 | total_files | reviewed_files | skipped_files | coverage_rate |
|---|---:|---:|---:|---:|
| 本轮唯一增量目标 | 1 | 1 | 0 | 100% |
| workspace reviewable + 显式覆盖E2E | 99 | 1 | 98 | 1.01% |

不得据此称 whole workspace PASS。

## 冻结与未验证范围

before实核 `0941574DD7EB1ED5A586D882E1FDA3C11F3AB201AFAA13DFB8A9A31F6949C3D5`；当前after为 `FE14E88333F6A4B11B72132F12580A717E7527010BD224F027D0E98DE99FB5FD`，完整after快照与现源一致。20项结束哈希全部匹配本轮after，实际1变19同，见 [review-hashes](m3-baseline-state-review-hashes.json)。产品、样式、单元测试、依赖/配置不变；此前428项/build exit0仅属于对应已冻结产品版本，本审阅未重跑或冒充新结果。

已读 collect 日志及退出码：25项、exit0，仅收集。原24 passed/1 failed/0 skipped和M4整链通过是旧spec的实际结果，不能继承为新spec通过。此审阅没有启动服务、浏览器或运行功能；M3完整后段及新的全部25项仍须在隔离HTTP真实执行并核实际附件。没有新增依赖或冒称独立E2E Node类型检查通过。

受控API/人工字体压力与真实HTTP持久化、原生缩放分开；L1–L4、Task13和B候选限制保持，Task12仍 IN_PROGRESS。只新增本审查及OCR/ledger/哈希证据，未改代码、旧计划或失败报告，未stage/commit。README已检查，由主会话串行汇总更新。
