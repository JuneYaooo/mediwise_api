"""
聊天处理辅助函数
封装chat_with_medical_assistant中的业务逻辑
"""
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.conversation import Conversation as ConversationModel, Message as MessageModel
from app.models.patient_detail_helpers import PatientDetailHelper
from app.utils.datetime_utils import get_beijing_now_naive
from app.agents.medical_api import Message as MedicalMessage
from src.utils.logger import BeijingLogger

logger = BeijingLogger().get_logger()


class ChatHelper:
    """聊天辅助类"""

    @staticmethod
    def get_conversation_history(db: Session, conversation_id: str) -> List[MedicalMessage]:
        """
        获取会话历史并转换为MedicalMessage格式

        Args:
            db: 数据库会话
            conversation_id: 会话ID

        Returns:
            MedicalMessage列表
        """
        messages_db = db.query(MessageModel).filter(
            MessageModel.conversation_id == conversation_id
        ).order_by(MessageModel.created_at).all()

        conversation_history = []
        for msg in messages_db:
            if msg.role == "user" and msg.content:
                conversation_history.append(MedicalMessage(
                    role="user",
                    content=msg.content
                ))
            elif msg.role == "assistant" and msg.content:
                conversation_history.append(MedicalMessage(
                    role="assistant",
                    content=msg.content
                ))
            elif msg.role == "assistant" and msg.type == "tool_output":
                conversation_history.append(MedicalMessage(
                    role="assistant",
                    content=f"agent:{msg.agent_name} \n agent相关结果：{msg.tool_outputs}"
                ))

        return conversation_history

    @staticmethod
    def save_user_message(db: Session, conversation_id: str, user_message: str,
                         parent_id: str = None) -> MessageModel:
        """
        保存用户消息到数据库

        Args:
            db: 数据库会话
            conversation_id: 会话ID
            user_message: 用户消息内容
            parent_id: 父消息ID

        Returns:
            保存的消息对象
        """
        # 获取下一个sequence_number
        last_message = db.query(MessageModel).filter(
            MessageModel.conversation_id == conversation_id
        ).order_by(MessageModel.sequence_number.desc()).first()

        next_sequence = 1
        if last_message and last_message.sequence_number is not None:
            next_sequence = last_message.sequence_number + 1

        # 如果没有指定parent_id，查找最近的助手消息
        if parent_id is None:
            last_assistant_message = db.query(MessageModel).filter(
                MessageModel.conversation_id == conversation_id,
                MessageModel.role == "assistant",
                MessageModel.type == "reply"
            ).order_by(MessageModel.sequence_number.desc()).first()

            if last_assistant_message:
                parent_id = last_assistant_message.message_id

        # 为用户消息生成唯一消息ID
        import uuid
        user_message_id = f"user_{uuid.uuid4()}"

        # 保存用户消息
        current_time = get_beijing_now_naive()
        user_msg = MessageModel(
            message_id=user_message_id,
            conversation_id=conversation_id,
            role="user",
            content=user_message,
            type="text",
            sequence_number=next_sequence,
            parent_id=parent_id,
            created_at=current_time,
            updated_at=current_time
        )
        db.add(user_msg)

        # 更新会话的updated_at时间戳
        conversation = db.query(ConversationModel).filter(
            ConversationModel.id == conversation_id
        ).first()
        if conversation:
            conversation.updated_at = current_time
            db.add(conversation)

        db.commit()
        db.refresh(user_msg)

        return user_msg

    @staticmethod
    def get_existing_patient_data(db: Session, conversation_id: str) -> Dict:
        """
        获取现有的患者数据

        Args:
            db: 数据库会话
            conversation_id: 会话ID

        Returns:
            患者数据字典
        """
        try:
            patient_detail = PatientDetailHelper.get_patient_detail_by_conversation_id(
                db, conversation_id
            )

            if patient_detail:
                logger.info(f"找到现有患者数据，conversation_id: {conversation_id}")
                all_existing_data = PatientDetailHelper.get_all_data(patient_detail)

                return {
                    "patient_timeline": all_existing_data.get("patient_timeline", {}),
                    "patient_journey": all_existing_data.get("patient_journey", {}),
                    "mdt_simple_report": all_existing_data.get("mdt_simple_report", {}),
                    "raw_files_data": all_existing_data.get("raw_files_data", []),
                    "raw_file_ids": all_existing_data.get("raw_file_ids", []),
                    "patient_full_content": all_existing_data.get("patient_full_content", ""),
                    "raw_text_data": all_existing_data.get("raw_text_data", "")
                }
            else:
                logger.info(f"未找到现有患者数据，conversation_id: {conversation_id}")
                return {}

        except Exception as e:
            logger.error(f"查询现有患者数据时出错: {str(e)}")
            return {}

    @staticmethod
    def store_patient_details(db: Session, conversation_id: str, user_message: str,
                             uploaded_file_ids: List[str], raw_files_data: List[Dict],
                             extraction_statistics: Dict = None) -> None:
        """
        存储患者详情到数据库

        Args:
            db: 数据库会话
            conversation_id: 会话ID
            user_message: 用户消息
            uploaded_file_ids: 上传的文件ID列表
            raw_files_data: 文件元数据列表
            extraction_statistics: 文件提取统计信息
        """
        try:
            existing_patient_detail = PatientDetailHelper.get_patient_detail_by_conversation_id(
                db, conversation_id
            )

            if existing_patient_detail:
                # 更新现有记录
                current_raw_text = existing_patient_detail.raw_text_data or ""
                updated_raw_text = f"{current_raw_text}\n{user_message}".strip() if current_raw_text else user_message

                current_file_ids = PatientDetailHelper.get_raw_file_ids(existing_patient_detail) or []
                updated_file_ids = current_file_ids + uploaded_file_ids

                current_raw_files_data = PatientDetailHelper.get_raw_files_data(existing_patient_detail) or []
                if raw_files_data:
                    logger.info(
                        f"合并现有文件数据 ({len(current_raw_files_data)} 个) "
                        f"和新文件数据 ({len(raw_files_data)} 个)"
                    )
                    updated_raw_files_data = PatientDetailHelper.merge_raw_files_data(
                        current_raw_files_data, raw_files_data
                    )
                    logger.info(f"合并后文件数据总数: {len(updated_raw_files_data)} 个")
                else:
                    updated_raw_files_data = current_raw_files_data

                # 准备更新数据
                update_data = {
                    "raw_text_data": updated_raw_text,
                    "raw_file_ids": updated_file_ids if updated_file_ids else None,
                    "raw_files_data": updated_raw_files_data if updated_raw_files_data else None
                }

                # 如果有新的提取统计信息，更新或合并
                if extraction_statistics:
                    update_data["extraction_statistics"] = extraction_statistics

                PatientDetailHelper.update_patient_detail(
                    db=db,
                    patient_detail=existing_patient_detail,
                    **update_data
                )
                logger.info(
                    f"更新patient_detail: conversation_id={conversation_id}, "
                    f"新增上传文件数={len(uploaded_file_ids)}, "
                    f"新增提取文件数={len(raw_files_data)}, "
                    f"合并后总文件数={len(updated_raw_files_data)}"
                )

                # 记录提取统计信息
                if extraction_statistics:
                    logger.info(
                        f"文件提取统计: 成功率={extraction_statistics.get('success_rate', 0)}%, "
                        f"成功={extraction_statistics.get('successful_extractions', 0)}, "
                        f"失败={extraction_statistics.get('failed_extractions', 0)}"
                    )
            else:
                # 创建新记录
                create_data = {
                    "conversation_id": conversation_id,
                    "raw_text_data": user_message,
                    "raw_file_ids": uploaded_file_ids if uploaded_file_ids else None,
                    "raw_files_data": raw_files_data if raw_files_data else None
                }

                # 添加提取统计信息
                if extraction_statistics:
                    create_data["extraction_statistics"] = extraction_statistics

                PatientDetailHelper.create_patient_detail(db=db, **create_data)
                logger.info(
                    f"创建新patient_detail: conversation_id={conversation_id}, "
                    f"上传文件数={len(uploaded_file_ids)}, "
                    f"提取文件数={len(raw_files_data)}"
                )

                # 记录提取统计信息
                if extraction_statistics:
                    logger.info(
                        f"文件提取统计: 成功率={extraction_statistics.get('success_rate', 0)}%, "
                        f"成功={extraction_statistics.get('successful_extractions', 0)}, "
                        f"失败={extraction_statistics.get('failed_extractions', 0)}"
                    )

        except Exception as e:
            logger.error(f"存储patient_detail失败: {str(e)}")
            # 不中断主流程

    @staticmethod
    def should_generate_title(conversation: ConversationModel, message_count: int) -> bool:
        """
        判断是否需要生成/更新会话标题

        Args:
            conversation: 会话对象
            message_count: 消息数量

        Returns:
            是否需要生成标题
        """
        if not conversation.title or conversation.title == "新会话":
            return True

        # 当消息数量足够且是5的倍数时，重新生成标题
        if message_count >= 4 and message_count % 5 == 0:
            return True

        return False
