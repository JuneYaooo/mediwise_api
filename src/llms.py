import os

# 尝试导入dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv不是必需的，可以直接使用环境变量

from crewai import  LLM

# 通用医疗分析模型 - 用于诊断、文献搜索、药物分析等通用任务 (使用34次)
general_llm = LLM(
		model=os.getenv('GENERAL_CHAT_MODEL_NAME'),
        api_key=os.getenv('GENERAL_CHAT_API_KEY'),
        base_url=os.getenv('GENERAL_CHAT_BASE_URL')
    )

# 文档生成专用模型 - 用于患者数据结构化、PPT/Word生成等文档处理任务 (使用8次)
document_generation_llm = LLM(
		model=os.getenv('ONLINE_GEMINI_MODEL_NAME'),
		api_key=os.getenv('ONLINE_GEMINI_API_KEY'),
		base_url=os.getenv('ONLINE_GEMINI_BASE_URL'),
		max_tokens=65535,
		temperature=0.1,
        timeout=300
	)
