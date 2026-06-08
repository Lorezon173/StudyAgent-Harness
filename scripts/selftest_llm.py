"""新栈 LLM 调用回路自测（一次性脚本，非测试套件）。

验证链路：.env → settings → LLMConfig 兜底 → ChatOpenAI 构造 → 真实 invoke。
用法：.venv/bin/python scripts/selftest_llm.py
"""
import sys


def main():
    # 1. settings 是否读到 .env
    from app.core.config import settings
    key = settings.openai_api_key
    print("【1】settings 读取 .env")
    print(f"    openai_api_key: {'已设置 (len=%d)' % len(key) if key else '空 ❌'}")
    print(f"    openai_base_url: {settings.openai_base_url or '(官方默认)'}")
    print(f"    openai_model: {settings.openai_model}")
    if not key or key == "sk-your-key-here":
        print("\n❌ 请先在 .env 填入真实 OPENAI_API_KEY 再运行本脚本")
        sys.exit(1)

    # 2. LLMService 兜底是否把 key 注入 config
    from app.infrastructure.llm import LLMService
    svc = LLMService()
    print("\n【2】LLMService 兜底注入")
    print(f"    config.api_key: {'已注入 ✅' if svc.config.api_key else '空 ❌'}")
    print(f"    config.primary_model: {svc.config.primary_model}")

    # 3. ChatOpenAI 能否构造
    print("\n【3】ChatOpenAI 构造")
    try:
        _ = svc.llm
        print("    构造成功 ✅")
    except Exception as e:
        print(f"    构造失败 ❌: {type(e).__name__}: {e}")
        sys.exit(1)

    # 4. 真实 invoke_json（打一次真实 API）
    print("\n【4】真实 LLM 调用（invoke_json）")
    try:
        result = svc.invoke_json(
            "你是测试助手。只输出 JSON：{\"ok\": true, \"echo\": \"<把用户消息原样返回>\"}",
            "ping",
            session_id="selftest", node="selftest", intent="selftest",
        )
        print(f"    调用成功 ✅  返回: {result}")
    except Exception as e:
        print(f"    调用失败 ❌: {type(e).__name__}: {e}")
        sys.exit(1)

    print("\n✅ 全链路打通，新栈可用真实 LLM。")


if __name__ == "__main__":
    main()
