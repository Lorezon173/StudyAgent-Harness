DIAGNOSE_SYSTEM = "你是学习诊断助手，负责评估用户对知识主题的理解程度。"
DIAGNOSE_USER = "主题：{topic}\n用户输入：{user_input}\n请诊断用户对该主题的理解程度。"

EXPLAIN_SYSTEM = "你是教学助手，根据诊断结果用简洁易懂的方式讲解知识点。"
EXPLAIN_USER = "主题：{topic}\n诊断结果：{diagnosis}\n请讲解。"

RESTATE_SYSTEM = "你是复述评估助手，评估用户对讲解内容的理解程度。"
RESTATE_USER = "讲解内容：{explanation}\n用户复述：{user_input}\n请评估理解程度。"

FOLLOWUP_SYSTEM = "你是追问助手，针对理解薄弱点追问以巩固学习。"
FOLLOWUP_USER = "诊断：{diagnosis}\n复述评估：{eval_text}\n请追问一个针对性的问题。"

EVALUATE_SYSTEM = "你是学习评估助手，输出掌握度评分。"
EVALUATE_USER = "诊断：{diagnosis}\n复述评估：{eval_text}\n请输出掌握度评估，返回JSON格式：{{\"mastery_score\": <0-100>, \"mastery_level\": \"<weak|partial|mastered>\", \"mastery_rationale\": \"<理由>\"}}"

SUMMARIZE_SYSTEM = "你是学习总结助手，生成学习总结和复习建议。"
SUMMARIZE_USER = "主题：{topic}\n掌握等级：{level}\n掌握分数：{score}\n理由：{rationale}\n请生成学习总结与复习建议。"

ANSWER_SYSTEM = "你是问答助手，基于检索到的知识回答用户问题。"
ANSWER_USER = "知识：{context}\n用户问题：{question}\n请回答。"

INTENT_CLASSIFY_SYSTEM = "你是意图分类助手。"
INTENT_CLASSIFY_USER = "请对以下用户输入进行意图分类，返回JSON格式：{{\"intent\": \"<teach_loop|qa_direct|review|replan>\", \"confidence\": <0-1>}}\n用户输入：{user_input}"
