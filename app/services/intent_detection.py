"""
意图识别服务 - 使用大模型识别用户意图
参考 mediwise IntentDetermineCrew 实现
"""
import os
import json
from typing import Any, List, Dict

from src.utils.logger import BeijingLogger

logger = BeijingLogger().get_logger()


# 意图类型定义
INTENT_TYPES = {
    "chat": "普通对话、咨询问题、寻求建议",
    "update_data": "更新/补充/新增患者数据（上传文件、录入信息等）",
    "modify_data": "修改已有的患者数据（时间轴、旅程中的具体内容）",
}


async def detect_intent_with_llm(
    message: str, 
    files: List[Dict] = None,
    patient_context: Dict[str, Any] = None,
    conversation_history: List[Dict] = None
) -> Dict[str, Any]:
    """
    使用大模型进行意图识别
    
    意图类型:
    - chat: 普通对话（咨询问题、询问建议、闲聊等）
    - update_data: 新增患者数据（上传文件、录入新信息）
    - modify_data: 修改已有数据（修改时间轴、旅程中的内容）
    
    返回:
        {
            "intent": "chat" | "update_data" | "modify_data",
            "reason": str,
            "confidence": float,
            "user_requirement": str,  # 用户的具体需求描述
            "modify_type": str,  # 仅 modify_data 时有效: "add_new_data" | "modify_current_data"
        }
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage
    
    try:
        # 如果有文件上传，直接判定为更新数据（不需要调用LLM）
        if files and len(files) > 0:
            file_names = [f.get('file_name', '未知文件') for f in files]
            return {
                "intent": "update_data",
                "reason": f"用户上传了文件: {', '.join(file_names)}",
                "confidence": 1.0,
                "user_requirement": f"处理并提取上传的 {len(files)} 个文件中的患者数据",
                "modify_type": "add_new_data"
            }
        
        # 使用大模型进行意图识别
        model = ChatOpenAI(
            model=os.getenv('GENERAL_CHAT_MODEL_NAME', 'deepseek-chat'),
            api_key=os.getenv('GENERAL_CHAT_API_KEY'),
            base_url=os.getenv('GENERAL_CHAT_BASE_URL'),
            temperature=0.1,  # 低温度以获得更一致的结果
            timeout=30
        )
        
        # 构建患者上下文信息
        patient_info_str = ""
        if patient_context:
            patient_info = patient_context.get("patient_info") or {}
            if patient_info:
                patient_info_str = f"\n当前患者: {patient_info.get('name', '未知')}"
                if patient_info.get('age'):
                    patient_info_str += f"，{patient_info.get('age')}岁"
                if patient_info.get('gender'):
                    patient_info_str += f"，{patient_info.get('gender')}"
        
        # 构建对话历史
        history_str = ""
        if conversation_history and len(conversation_history) > 0:
            recent_history = conversation_history[-5:]  # 只取最近5条
            history_parts = []
            for msg in recent_history:
                role = "用户" if msg.get("role") == "user" else "助手"
                content = msg.get("content", "")[:200]  # 截断过长内容
                history_parts.append(f"{role}: {content}")
            history_str = "\n".join(history_parts)
        
        system_prompt = """你是医疗AI助手的意图识别模块。判断用户消息属于以下三种意图之一：

## 意图类型（只有这3种，必须选其一）

1. **chat** - 对话/咨询/问诊/提问（默认）
   - 询问诊断、治疗建议、用药咨询
   - 病情分析、症状解读
   - 任何问答类需求
   - 问候、感谢、闲聊

2. **update_data** - 新增患者数据
   - 录入/上传新的检查报告、化验单、病历
   - 补充/添加诊断结果、用药记录

3. **modify_data** - 修改已有数据
   - 修改/更正时间轴、旅程中的某条记录
   - 删除错误数据

## 输出（严格JSON格式）

{"intent": "chat|update_data|modify_data", "reason": "理由", "confidence": 0.9, "user_requirement": "具体需求"}"""

        user_prompt = f"""## 上下文信息
{patient_info_str if patient_info_str else "（无患者信息）"}

## 对话历史
{history_str if history_str else "（无历史对话）"}

## 用户最新消息
{message}

请判断用户意图："""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = await model.ainvoke(messages)
        response_text = response.content.strip()
        
        logger.debug(f"意图识别原始响应: {response_text}")
        
        # 解析JSON响应
        try:
            # 尝试直接解析
            result = json.loads(response_text)
        except json.JSONDecodeError:
            # 尝试提取JSON部分
            import re
            json_match = re.search(r'\{[^}]+\}', response_text, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                except:
                    logger.warning(f"意图识别响应解析失败: {response_text}")
                    return {
                        "intent": "chat",
                        "reason": "意图识别响应解析失败，默认为对话",
                        "confidence": 0.5,
                        "user_requirement": message
                    }
            else:
                logger.warning(f"意图识别响应解析失败: {response_text}")
                return {
                    "intent": "chat",
                    "reason": "意图识别响应解析失败，默认为对话",
                    "confidence": 0.5,
                    "user_requirement": message
                }
        
        # 验证并标准化意图类型
        intent = result.get("intent", "chat")
        if intent not in ["chat", "update_data", "modify_data"]:
            # 尝试映射常见变体
            intent_mapping = {
                "modify_patient_info": "modify_data",
                "add_data": "update_data",
                "normal_diagnose": "chat",
                "diagnose": "chat",
                "question": "chat",
            }
            intent = intent_mapping.get(intent, "chat")
        
        # 根据意图确定默认的 modify_type
        if intent == "modify_data":
            default_modify_type = "modify_current_data"
        elif intent == "update_data":
            default_modify_type = "add_new_data"
        else:
            default_modify_type = None
        
        return {
            "intent": intent,
            "reason": result.get("reason", ""),
            "confidence": float(result.get("confidence", 0.8)),
            "user_requirement": result.get("user_requirement", message),
            "modify_type": result.get("modify_type", default_modify_type)
        }
        
    except Exception as e:
        logger.error(f"意图识别失败: {str(e)}")
        # 出错时默认为chat
        return {
            "intent": "chat",
            "reason": f"意图识别出错，默认为对话: {str(e)}",
            "confidence": 0.5,
            "user_requirement": message
        }

