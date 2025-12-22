"""
患者数据处理工具
处理患者详情数据的存储、更新等操作
"""

from typing import Dict, Any
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.patient_detail_helpers import PatientDetailHelper
from app.models.conversation import Conversation as ConversationModel
from src.utils.logger import BeijingLogger

logger = BeijingLogger().get_logger()


async def handle_tool_output_storage(data: Dict[str, Any], conversation_id: str) -> None:
    """
    处理工具输出的存储到patient_details表

    Args:
        data: 工具输出数据
        conversation_id: 会话ID
    """
    # 获取工具输出内容
    content = data.get("content", {})
    tool_name = content.get("tool_name")

    if not tool_name:
        return

    # 创建新的数据库会话
    db = SessionLocal()
    try:
        # 获取现有的patient_detail记录
        existing_patient_detail = PatientDetailHelper.get_patient_detail_by_conversation_id(
            db, conversation_id
        )

        if tool_name == "patient_timeline":
            # 处理patient_timeline工具的输出
            tool_content = content.get("content", {})

            update_data = {}

            # 提取各个字段的数据
            if "patient_timeline" in tool_content:
                update_data["patient_timeline"] = tool_content["patient_timeline"]

            if "patient_journey" in tool_content:
                update_data["patient_journey"] = tool_content["patient_journey"]

            if "mdt_simple_report" in tool_content:
                update_data["mdt_simple_report"] = tool_content["mdt_simple_report"]

            if "patient_full_content" in tool_content:
                update_data["patient_full_content"] = tool_content["patient_full_content"]

            # 更新或创建patient_detail记录
            if existing_patient_detail:
                PatientDetailHelper.update_patient_detail(
                    db=db,
                    patient_detail=existing_patient_detail,
                    **update_data
                )
                logger.info(f"更新patient_timeline数据: conversation_id={conversation_id}")
            else:
                PatientDetailHelper.create_patient_detail(
                    db=db,
                    conversation_id=conversation_id,
                    **update_data
                )
                logger.info(f"创建patient_timeline数据: conversation_id={conversation_id}")

    except Exception as e:
        db.rollback()
        logger.error(f"处理工具输出存储时出错: {str(e)}")
        raise e
    finally:
        db.close()


async def update_patient_data(conversation_id: str, patient_data: Dict[str, Any]) -> None:
    """
    更新会话的患者数据

    Args:
        conversation_id: 会话ID
        patient_data: 患者数据
    """
    db = SessionLocal()
    try:
        conversation = db.query(ConversationModel).filter(
            ConversationModel.id == conversation_id
        ).first()

        if conversation:
            conversation.patient_data = patient_data
            db.add(conversation)
            db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating patient data: {str(e)}")
    finally:
        db.close()
