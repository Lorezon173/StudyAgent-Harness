import json


class LLMService:
    def __init__(self, api_key: str = "", base_url: str = "", model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def invoke(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import SystemMessage, HumanMessage
        llm = ChatOpenAI(
            api_key=self.api_key,
            base_url=self.base_url or None,
            model=self.model,
        )
        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        return response.content

    def invoke_json(self, system_prompt: str, user_prompt: str, **kwargs) -> dict:
        text = self.invoke(system_prompt, user_prompt, **kwargs)
        return json.loads(text)


class FakeLLM:
    RESPONSES = {
        "诊断": "用户对主题有基础了解，需要补充细节",
        "讲解": "知识点讲解内容...",
        "评估": '{"mastery_score": 65, "mastery_level": "medium"}',
        "意图": '{"intent": "teach_loop", "confidence": 0.9}',
    }

    def invoke(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        for keyword, response in self.RESPONSES.items():
            if keyword in user_prompt:
                return response
        return "默认测试回复"

    def invoke_json(self, system_prompt: str, user_prompt: str, **kwargs) -> dict:
        return json.loads(self.invoke(system_prompt, user_prompt))
