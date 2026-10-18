# T03 离线实现与验证记录

日期：2026-10-16  
契约：`rag-mvp-contracts-v1.0.1`  
冻结 spec SHA-256：`31379383758b82c82d5fe583f371e590f4b187ad0371744edcef635743b41f95`（本次复核一致）

本记录只证明 T03 受控离线测试和静态检查，不是实际书籍 baseline、正式 gate 或 G1/G4 通过证明。

## 环境与隔离

- Python：3.12.11；pytest：9.0.3；Ruff：0.15.7（使用本机缓存可执行文件，未安装或升级依赖）。
- 测试使用项目内临时目录 `docs/rag-work/evidence/t03/.pytest-tmp-*`。默认系统临时目录曾被沙箱拒绝，随后检查专属目录不存在再运行；这些目录由本任务创建，并按主控要求保留在证据目录下，未清理。
- Retriever 与 RAG-D 测试固定离线 fake Coordinator/provider；对 PG provider 连接构造和 ChatOpenAI/OpenAI SDK 构造设置失败陷阱及零调用计数。judge 构造默认被替换为不可用，成功路径只用受控 fake judge。真实 PostgreSQL、embedding、judge、网络服务均未调用。
- runner 和 ComponentBench 集成用本地合成资产及受控 provider；没有读取或改写正式书籍题集、corpus 或 EPUB，也没有依赖 T04 新模块。

## TDD 记录

以下红灯均由新行为断言产生，不把环境 setup 故障计为红灯；后续修复后由对应组或最终联合回归验证。

| 组 | 红灯观察 | 绿灯观察 |
|---|---|---|
| evaluate 信封/状态 | 10 项失败，原实现缺少稳定状态/来源字段及非法输入边界 | 10 项通过 |
| 一次检索派生多 k 与 proxy | 9 项失败，原实现缺少多 k proxy 与无 gold 的 null 语义 | 9 项通过 |
| judge 单项有效性 | 12 项失败，暴露缺失分数回填、非有限值及降级处理问题 | 14 项通过 |
| 资产校验 | 初始 7 项失败、2 项通过；覆盖 draft/题目身份等缺口 | 修复后 10 项通过、14 项未选；另加空白 question/gold_answer 的红灯 2 项，修复后纳入全量通过 |
| runner 计数/首次失败 | 初始 runner 契约组 26 项失败、24 项未选，原 runner 未保留失败 attempt 或强制计数不变量 | 首次失败停止、坏 metrics 安全替换、跨字段一致性和计数均纳入最终联合回归 |
| 敏感异常与坏字段 | 4 项失败、8 项通过；暴露 OSError 原文泄露及不可哈希字段导致验证崩溃 | 12 项通过；资产异常仅记录 `rule_id=asset_validation`，不引入公共 `error_code` |
| ComponentBench 真实受控贯通 | 按 plan 记录为实现后首次即绿，未人为破坏代码制造红灯 | 4 项通过，覆盖 null、失败/降级及健康 judge 路径 |
| runner 真实 evaluator 贯通 | 按 plan 在前序实现后首次即绿 | 4 项通过 |
| corpus 非 mapping 行 | 1 项失败，验证器因 list `.get()` 抛 AttributeError | 加入 mapping 校验后，与资产 OSError 安全出口定向测试共 2 项通过 |

## Round 1 定向复核

主控要求的修订保持在原有 T03 文件范围内，未改 `validate_admission`、正式 gate、spec 或 plan。

| 组 | 红灯 | 修复后绿灯 |
|---|---|---|
| A：empty、失败码和 D2 合成结果 | 定向 runner 命令退出码 1：24 failed、1 passed、54 deselected。暴露 empty 非零机械值被接受、`failed+invalid_request` 被接受、六码 D2 合成结果无法通过 validator | 同一覆盖组退出码 0：26 passed、54 deselected。empty 六项机械分固定为零；拒绝反向状态/错误码组合；精确固定的 D2 失败原因可复验，健康结果不能借该原因通过 |
| B：被引用 gold 文本与 excerpt | `pytest tests/eval/test_rag_d.py -k blank_referenced_gold_material ...` 退出码 1：3 failed、80 deselected；空 excerpt、空/空白被引用全文均漏过 | 同命令退出码 0：3 passed、80 deselected；校验只对被 evidence 引用的 corpus 全文与 excerpt 做 strip 非空判断，不改写原文 |
| C：隔离信息与 attestation ID | 投影/类型组退出码 1：3 failed、83 deselected；另一个 run ID 组退出码 1：4 failed、86 deselected。复现额外 NaN/秘密字段回显、mode 列表触发 TypeError、`verified=1` 放行及不安全 run ID 被报告接受 | C 组退出码 0：7 passed、83 deselected；报告仅含 mode/布尔 verified，坏隔离类型和空/非字符串 run ID 在 evaluate 前阻断；JSON `allow_nan=False` 成功 |

修订后的联合命令：

```text
.venv/Scripts/python.exe -m pytest tests/unit/agents/test_retriever.py tests/eval/test_rag_d.py tests/eval/test_component_bench.py --basetemp docs/rag-work/evidence/t03/.pytest-tmp-round1-final -q -p no:cacheprovider
```

退出码 0：`171 passed, 1 deselected`。最终收集 `test_retriever.py` 与 `test_rag_d.py` 为 167/168 项（1 deselected），退出码 0。

修订后限定四文件 Ruff 0.15.7 检查退出码 0：`All checks passed!`。`git diff --check` 限于四文件，退出码 0。冻结 spec SHA-256 复核仍为 `31379383758b82c82d5fe583f371e590f4b187ad0371744edcef635743b41f95`。

## 首次交付验证（历史；当前结果见上方 Round 2）

编码前 pytest 收集：53/54 项（1 项 deselected），退出码 0。最终收集 `test_retriever.py` 与 `test_rag_d.py`：148/149 项（1 项 deselected），退出码 0。

联合离线回归命令：

```text
.venv/Scripts/python.exe -m pytest tests/unit/agents/test_retriever.py tests/eval/test_rag_d.py tests/eval/test_component_bench.py --basetemp docs/rag-work/evidence/t03/.pytest-tmp-final -q -p no:cacheprovider
```

退出码 0：`152 passed, 1 deselected`。临时目录为本任务在执行前确认不存在后创建。

限定四个 T03 代码/测试文件的 Ruff 检查使用缓存的 Ruff 0.15.7，命令为：

```text
ruff.exe check --no-cache app/agents/retriever.py benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py tests/unit/agents/test_retriever.py tests/eval/test_rag_d.py
```

退出码 0：`All checks passed!`。从 HEAD 内容重建的 lint 基线中，原 `retriever.py` 有一个 F841，retriever 测试有一个未使用导入和两个 E402；本次 evaluator 替换消除了 F841，测试清理消除了其余告警。Rag-D 文件基线无告警。

`git diff --check -- app/agents/retriever.py benchmarks/rag/books/the-myth-of-sisyphus/rag_d.py tests/unit/agents/test_retriever.py tests/eval/test_rag_d.py` 退出码 0。

## Round 2 相邻边界

本轮仅处理 golden chunk 元素校验和 empty 来源一致性，未改 gate 或其他审阅范围。

| 覆盖 | 红灯 | 绿灯 |
|---|---|---|
| `golden_chunks` 项必须是非空白字符串；空列表仍合法 | `evaluate_contract_rejects_invalid_inputs_before_search` 退出码 1：1 failed、10 passed、71 deselected；空白项被当作合法输入 | evaluator 输入与多 k proxy 组退出码 0：20 passed、62 deselected；测试断言 search/judge 调用数为零，空列表仍可正常评测 |
| D2 `empty` 必须 `sources_used=[]` | empty 来源/合法空对照组退出码 1：1 failed、2 passed、88 deselected；矛盾来源列表被接受 | 同组退出码 0：3 passed、88 deselected；矛盾来源列表被拒绝，合法 empty 仍完成 |

最终 T03 限定三文件回归命令：

```text
.venv/Scripts/python.exe -m pytest tests/unit/agents/test_retriever.py tests/eval/test_rag_d.py tests/eval/test_component_bench.py --basetemp docs/rag-work/evidence/t03/.pytest-tmp-round2-final -q -p no:cacheprovider
```

退出码 0：`176 passed, 1 deselected`。四文件 Ruff 0.15.7 检查退出码 0：`All checks passed!`；四文件 `git diff --check` 退出码 0。主控另行同步的十文件组合回归为 `547 passed, 1 deselected`，该数字来自主控执行。

## 交接边界

本次只修改 T03 获准的 retriever evaluator、RAG-D runner/资产验证、对应离线测试和本证据文件。在线 `handle` 路径、Coordinator、正式 gate、共享契约、plan、README 与正式资产没有由 T03 修改；README 摘要由主控处理。没有 commit/push。

测试通过不代表真实 PG/embedding/judge 可用，也不构成实际 20 题质量 baseline。真实书籍评测仍须由后续授权流程执行；正式报告、T04 证明绑定和 G1 放行仍由后续任务负责。
