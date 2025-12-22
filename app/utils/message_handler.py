"""
消息处理工具
处理消息的保存、更新等数据库操作
"""

from typing import Dict, Any, Optional
import uuid

from sqlalchemy.orm import Session
from app.db.database import SessionLocal
from app.models.conversation import Message as MessageModel
from app.utils.datetime_utils import get_beijing_now_naive
from src.utils.logger import BeijingLogger

logger = BeijingLogger().get_logger()


async def save_message_to_db(message_data: Dict[str, Any], conversation_id: str,
                            role: str = "assistant") -> Optional[MessageModel]:
    """
    Save a message to the database (for streaming messages).

    Args:
        message_data: 消息数据字典
        conversation_id: 会话ID
        role: 消息角色，默认为assistant

    Returns:
        MessageModel: 保存的消息对象，如果失败则返回None
    """
    db = SessionLocal()
    try:
        # 保存原始ID为parent_id，用于关联同一轮对话内的消息
        original_id = message_data.get("id")

        # 获取显式提供的用户消息ID（如果有）
        user_message_id = message_data.get("user_message_id")

        # 为每个消息生成全新的唯一message_id
        message_id = f"msg_{uuid.uuid4()}"

        message_type = message_data.get("type", "reply")
        agent_name = message_data.get("agent_name")
        agent_session_id = message_data.get("agent_session_id")

        # Create a timestamp for both created_at and updated_at
        current_time = get_beijing_now_naive()

        # 获取下一个序列号
        next_sequence = 1

        last_message = db.query(MessageModel).filter(
            MessageModel.conversation_id == conversation_id
        ).order_by(MessageModel.sequence_number.desc()).first()

        if last_message and last_message.sequence_number is not None:
            next_sequence = last_message.sequence_number + 1
        else:
            next_sequence = 1

        # 如果是回复类型消息，我们需要找到它应该回复的用户消息
        user_message_to_reply = None
        if role == "assistant" and not user_message_id:
            user_message_to_reply = db.query(MessageModel).filter(
                MessageModel.conversation_id == conversation_id,
                MessageModel.role == "user"
            ).order_by(MessageModel.sequence_number.desc()).first()

        # 统一确定parent_id的逻辑
        parent_id = original_id
        if user_message_id:
            parent_id = user_message_id
        elif user_message_to_reply:
            parent_id = user_message_to_reply.message_id

        # 创建消息
        if message_type == "status":
            message = MessageModel(
                message_id=message_id,
                conversation_id=conversation_id,
                role=role,
                type=message_type,
                parent_id=parent_id,
                sequence_number=next_sequence,
                status_data={
                    "status": message_data.get("status"),
                    "status_msg": message_data.get("status_msg"),
                    "agent_name": agent_name,
                    "agent_session_id": agent_session_id,
                    "need_feedback": message_data.get("need_feedback", False),
                    "sequence_number": next_sequence
                },
                agent_name=agent_name,
                agent_session_id=agent_session_id,
                created_at=current_time,
                updated_at=current_time
            )
        elif message_type == "user_feedback_request":
            message = MessageModel(
                message_id=message_id,
                conversation_id=conversation_id,
                role=role,
                type=message_type,
                parent_id=parent_id,
                sequence_number=next_sequence,
                status_data={
                    "type": message_type,
                    "feedback_id": message_data.get("feedback_id"),
                    "question": message_data.get("question"),
                    "timeout": message_data.get("timeout", 300),
                    "agent_name": agent_name,
                    "agent_session_id": agent_session_id,
                    "conversation_id": message_data.get("conversation_id"),
                    "sequence_number": next_sequence
                },
                agent_name=agent_name,
                agent_session_id=agent_session_id,
                created_at=current_time,
                updated_at=current_time
            )
        elif message_type == "tool_output":
            tool_output = message_data.get("content", {})

            if isinstance(tool_output, dict):
                tool_output["sequence_number"] = next_sequence

            message = MessageModel(
                message_id=message_id,
                conversation_id=conversation_id,
                role=role,
                type=message_type,
                parent_id=parent_id,
                sequence_number=next_sequence,
                tool_outputs=[tool_output],
                agent_name=agent_name,
                agent_session_id=agent_session_id,
                created_at=current_time,
                updated_at=current_time
            )
        else:
            # 处理普通消息（reply或thinking类型）
            message_object = message_data.get("object")
            content = ""

            if message_object == "medical.completion":
                content = message_data.get("choices", [{}])[0].get("message", {}).get("content", "")
            elif message_object == "medical.completion.chunk":
                content = message_data.get("choices", [{}])[0].get("delta", {}).get("content", "")

            # 检查内容是否为空，如果为空则不保存
            if not content or len(content.strip()) == 0:
                db.close()
                return None

            message = MessageModel(
                message_id=message_id,
                conversation_id=conversation_id,
                role=role,
                content=content,
                type=message_type,
                parent_id=parent_id,
                sequence_number=next_sequence,
                agent_name=agent_name,
                agent_session_id=agent_session_id,
                created_at=current_time,
                updated_at=current_time
            )

        # 再次确认消息有有效的sequence_number
        if message.sequence_number is None:
            message.sequence_number = next_sequence

        db.add(message)
        db.commit()
        db.refresh(message)
        return message
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving message to database: {str(e)}")
        return None
    finally:
        db.close()
