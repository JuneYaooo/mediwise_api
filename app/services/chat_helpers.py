"""
患者对话辅助函数
- 会话管理
- 消息存储
- 上下文获取
"""
import uuid
from typing import Any, List, Dict, Optional
from sqlalchemy.orm import Session

from app.models.bus_models import (
    Patient,
    PatientConversation,
    ConversationMessage
)
from app.models.bus_patient_helpers import BusPatientHelper
from app.models.patient_detail_helpers import PatientDetailHelper
from app.utils.datetime_utils import get_beijing_now_naive
from src.utils.logger import BeijingLogger

logger = BeijingLogger().get_logger()


def get_or_create_conversation(
    db: Session,
    patient_id: str,
    user_id: str,
    conversation_id: Optional[str] = None,
    title: Optional[str] = None
) -> PatientConversation:
    """获取或创建患者会话"""
    
    # 如果指定了 conversation_id，尝试获取现有会话
    if conversation_id:
        conversation = db.query(PatientConversation).filter(
            PatientConversation.id == conversation_id,
            PatientConversation.patient_id == patient_id
        ).first()
        
        if conversation:
            logger.info(f"使用现有会话: {conversation_id}")
            return conversation
        else:
            logger.warning(f"指定的会话不存在: {conversation_id}，将创建新会话")
    
    # 创建新会话
    session_id = f"chat_{uuid.uuid4()}"
    conversation_title = title or f"对话 - {get_beijing_now_naive().strftime('%Y-%m-%d %H:%M')}"
    
    conversation = BusPatientHelper.create_conversation(
        db=db,
        patient_id=patient_id,
        user_id=user_id,
        title=conversation_title,
        session_id=session_id,
        conversation_type="chat"
    )
    db.commit()
    
    logger.info(f"创建新会话: {conversation.id}")
    return conversation


def save_message(
    db: Session,
    conversation_id: str,
    role: str,
    content: str,
    message_type: str = "text",
    parent_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    tool_outputs: Optional[List[Dict]] = None,
    status_data: Optional[Dict] = None
) -> ConversationMessage:
    """保存消息到 bus_conversation_messages 表"""
    
    # 获取下一个序列号
    last_message = db.query(ConversationMessage).filter(
        ConversationMessage.conversation_id == conversation_id
    ).order_by(ConversationMessage.sequence_number.desc()).first()
    
    next_sequence = 1
    if last_message and last_message.sequence_number:
        next_sequence = last_message.sequence_number + 1
    
    current_time = get_beijing_now_naive()
    message_id = f"msg_{uuid.uuid4().hex[:12]}_{int(current_time.timestamp())}"
    
    message = ConversationMessage(
        id=str(uuid.uuid4()),
        conversation_id=conversation_id,
        message_id=message_id,
        role=role,
        content=content,
        type=message_type,
        parent_id=parent_id,
        agent_name=agent_name,
        sequence_number=next_sequence,
        tooloutputs=tool_outputs or [],
        statusdata=status_data or {},
        created_at=current_time,
        updated_at=current_time
    )
    
    db.add(message)
    db.flush()
    
    logger.debug(f"保存消息: {message_id}, role={role}, type={message_type}")
    return message


def get_conversation_history(
    db: Session,
    conversation_id: str,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """获取会话历史消息"""
    
    messages = db.query(ConversationMessage).filter(
        ConversationMessage.conversation_id == conversation_id
    ).order_by(ConversationMessage.sequence_number.asc()).limit(limit).all()
    
    history = []
    for msg in messages:
        # 只包含用户和助手的文本消息
        if msg.role in ["user", "assistant"] and msg.content:
            history.append({
                "role": msg.role,
                "content": msg.content
            })
    
    return history


def get_patient_context(
    db: Session,
    patient_id: str
) -> Dict[str, Any]:
    """获取患者上下文信息（用于对话）"""
    
    context = {
        "patient_info": None,
        "patient_timeline": None,
        "recent_files": []
    }
    
    # 获取患者基本信息
    patient = db.query(Patient).filter(
        Patient.patient_id == patient_id,
        Patient.is_deleted == False
    ).first()
    
    if patient:
        context["patient_info"] = {
            "name": patient.name,
            "gender": patient.gender,
            "phone": patient.phone,
            "allergies": patient.allergies,
            "medical_history": patient.medical_history
        }
    
    # 获取最新的患者时间轴数据
    patient_detail = PatientDetailHelper.get_latest_patient_detail_by_patient_id(db, patient_id)
    if patient_detail:
        context["patient_timeline"] = PatientDetailHelper.get_patient_timeline(patient_detail)
    
    return context

