"""Spike: 验证 DeepEval GEval 与 build_judge() 的兼容性

验证目标：
  1. GEval 构造函数是否接受 langchain_openai.ChatOpenAI 对象
  2. measure() 方法的签名和用法
  3. score 和 reason 的获取方式
  4. 与 build_judge() 返回值的接口兼容性

运行方式：
  python spike_geval_compat.py
"""

import inspect
import sys

# ─── 1. 检查 deepeval 是否安装 ───
try:
    import deepeval
    print(f"[OK] deepeval 已安装，版本: {deepeval.__version__}")
except ImportError:
    print("[FAIL] deepeval 未安装")
    sys.exit(1)

# ─── 2. 检查 GEval 导入和构造函数签名 ───
from deepeval.metrics import GEval

sig = inspect.signature(GEval.__init__)
print("\n[OK] GEval 构造函数签名:")
for name, param in sig.parameters.items():
    if name == "self":
        continue
    print(f"  {name}: {param.annotation} = {param.default}")

# ─── 3. 检查 model 参数的类型注解 ───
model_param = sig.parameters.get("model")
print(f"\n[INFO] model 参数类型注解: {model_param.annotation}")
print(f"[INFO] model 参数默认值: {model_param.default}")

# ─── 4. 检查 LLMTestCase 字段 ───
from deepeval.test_case import LLMTestCase  # noqa: E402 - staged compatibility probe imports after prerequisite checks

print("\n[OK] LLMTestCase 字段:")
for field_name, field_info in LLMTestCase.model_fields.items():
    required = field_info.is_required()
    print(f"  {field_name}: required={required}, type={field_info.annotation}")

# ─── 5. 检查 DeepEvalBaseLLM 抽象基类 ───
from deepeval.models.base_model import DeepEvalBaseLLM  # noqa: E402 - staged compatibility probe imports after prerequisite checks

print("\n[OK] DeepEvalBaseLLM 抽象方法:")
for name, method in inspect.getmembers(DeepEvalBaseLLM):
    if getattr(method, "__isabstractmethod__", False):
        print(f"  {name}")

# ─── 6. 检查 SingleTurnParams（evaluation_params 用） ───
try:
    from deepeval.metrics import SingleTurnParams
    print("\n[OK] SingleTurnParams 枚举值:")
    for member in SingleTurnParams:
        print(f"  {member.name} = {member.value}")
except ImportError:
    print("\n[WARN] SingleTurnParams 不可用，尝试 LLMTestCaseParams")
    from deepeval.test_case import LLMTestCaseParams
    for member in LLMTestCaseParams:
        print(f"  {member.name} = {member.value}")

# ─── 7. 核心兼容性验证：ChatOpenAI vs GEval model 参数 ───
print("\n" + "=" * 60)
print("核心兼容性验证")
print("=" * 60)

# 7a. 类型检查
from langchain_openai import ChatOpenAI  # noqa: E402 - staged compatibility probe imports after prerequisite checks

print("\n[TEST] ChatOpenAI 是否是 DeepEvalBaseLLM 的子类？")
print(f"  结果: {issubclass(ChatOpenAI, DeepEvalBaseLLM)}")
print(f"  结论: {'兼容' if issubclass(ChatOpenAI, DeepEvalBaseLLM) else '不兼容 — ChatOpenAI 不是 DeepEvalBaseLLM 子类'}")

# 7b. 尝试用 ChatOpenAI 构造 GEval（预期会失败或行为异常）
print("\n[TEST] 尝试用 ChatOpenAI 实例构造 GEval...")
try:
    fake_llm = ChatOpenAI(
        api_key="sk-fake-key-for-spike",
        model="gpt-4o-mini",
        temperature=0.0,
    )
    # 尝试构造 GEval
    metric = GEval(
        name="test_metric",
        model=fake_llm,
        criteria="Test criteria",
        evaluation_steps=["Step 1"],
        async_mode=False,
    )
    print("  构造函数调用: 成功（未报错）")
    print(f"  metric.model 类型: {type(metric.model)}")
except Exception as e:
    print("  构造函数调用: 失败")
    print(f"  异常类型: {type(e).__name__}")
    print(f"  异常信息: {e}")

# 7c. 验证正确用法：传字符串
print("\n[TEST] 用字符串 model 构造 GEval（正确用法）...")
try:
    metric_str = GEval(
        name="test_metric_str",
        model="gpt-4o-mini",
        criteria="Evaluate clarity of the response",
        evaluation_steps=[
            "Check if the response is well-structured",
            "Check if key concepts are explained clearly",
        ],
        threshold=0.5,
        async_mode=False,
    )
    print("  构造函数调用: 成功")
    print(f"  metric_str.model 类型: {type(metric_str.model)}")
except Exception as e:
    print(f"  构造函数调用: 失败 — {type(e).__name__}: {e}")

# ─── 8. measure() 方法签名 ───
print("\n[INFO] measure() 方法签名:")
measure_sig = inspect.signature(GEval.measure)
for name, param in measure_sig.parameters.items():
    if name == "self":
        continue
    print(f"  {name}: {param.annotation} = {param.default}")

# ─── 9. LLMTestCase 构造测试 ───
print("\n[TEST] 构造 LLMTestCase...")
try:
    tc = LLMTestCase(
        input="学生问：什么是牛顿第三定律？",
        actual_output="牛顿第三定律说的是作用力与反作用力大小相等、方向相反。",
        expected_output="牛顿第三定律指出，两个物体之间的作用力和反作用力总是大小相等、方向相反、作用在同一条直线上。",
    )
    print("  构造成功")
    print(f"  input: {tc.input[:30]}...")
    print(f"  actual_output: {tc.actual_output[:30]}...")
except Exception as e:
    print(f"  构造失败: {e}")

# ─── 10. score/reason 访问方式（不真实调用 API） ───
print("\n[INFO] score/reason 属性检查:")
print(f"  GEval 是否有 score 属性: {hasattr(GEval, 'score') or 'score' in GEval.__annotations__ if hasattr(GEval, '__annotations__') else '需要实例化后检查'}")
print(f"  GEval 是否有 reason 属性: {hasattr(GEval, 'reason') or 'reason' in GEval.__annotations__ if hasattr(GEval, '__annotations__') else '需要实例化后检查'}")

# 检查 BaseMetric 父类
from deepeval.metrics.base_metric import BaseMetric  # noqa: E402 - staged compatibility probe imports after prerequisite checks

print(f"  BaseMetric 字段: {[f for f in dir(BaseMetric) if not f.startswith('_')]}")

# ─── 11. 检查 initialize_model 逻辑 ───
print("\n[INFO] 检查 deepeval 内部 model 初始化逻辑...")
try:
    from deepeval.models import initialize_model
    sig_init = inspect.signature(initialize_model)
    print(f"  initialize_model 签名: {sig_init}")
    src = inspect.getsource(initialize_model)
    # 只看前 30 行
    lines = src.split("\n")[:30]
    print("  initialize_model 源码（前 30 行）:")
    for line in lines:
        print(f"    {line}")
except Exception as e:
    print(f"  无法检查: {e}")

# ─── 总结 ───
print("\n" + "=" * 60)
print("兼容性结论")
print("=" * 60)
print("""
1. GEval.model 参数类型: Optional[Union[str, DeepEvalBaseLLM]]
   - 接受字符串（如 "gpt-4o-mini"）→ 内部自动创建 GPTModel
   - 接受 DeepEvalBaseLLM 子类实例 → 自定义模型
   - 不接受 langchain_openai.ChatOpenAI（不是 DeepEvalBaseLLM 子类）

2. build_judge() 返回 {"llm": ChatOpenAI, ...}
   - ChatOpenAI 对象不能直接传给 GEval.model
   - 需要适配方案

3. 适配方案:
   a) 最简单：直接传 model="gpt-4o-mini" 字符串，绕过 build_judge() 的 llm
   b) 自定义 wrapper：继承 DeepEvalBaseLLM，内部包装 ChatOpenAI
   c) 传 None，让 GEval 使用默认 GPTModel（需要 OPENAI_API_KEY 环境变量）

4. measure() 用法:
   metric = GEval(name="xxx", model="gpt-4o-mini", criteria="...", ...)
   score = metric.measure(test_case)  # 返回 float
   print(metric.score)   # 同上
   print(metric.reason)  # LLM 给出的评估理由
""")
