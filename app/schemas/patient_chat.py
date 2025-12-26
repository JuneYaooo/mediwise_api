"""
患者对话相关的 Schema 定义
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class PatientChatRequest(BaseModel):
    """患者对话请求"""
    message: Optional[str] = None
    files: Optional[List[Dict[str, Any]]] = None
    conversation_id: Optional[str] = None  # 可选，指定继续哪个会话


class PatientConversationResponse(BaseModel):
    """患者会话响应"""
    id: str
    patient_id: str
    session_id: Optional[str] = None
    title: Optional[str] = None
    conversation_type: Optional[str] = None
    status: Optional[str] = None
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True


class ConversationMessageResponse(BaseModel):
    """会话消息响应"""
    id: str
    conversation_id: str
    message_id: Optional[str] = None
    role: str
    content: Optional[str] = None
    type: Optional[str] = None
    agent_name: Optional[str] = None
    sequence_number: Optional[int] = None
    created_at: str
    
    class Config:
        from_attributes = True


class IntentResult(BaseModel):
    """意图识别结果"""
    intent: str  # chat | update_data | modify_data
    reason: str
    confidence: float
    user_requirement: Optional[str] = None
    modify_type: Optional[str] = None  # add_new_data | modify_current_data

