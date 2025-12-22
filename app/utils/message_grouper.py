"""
消息分组和处理工具
封装get_conversation_messages中的消息分组逻辑
"""
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.conversation import Message as MessageModel
from app.utils.datetime_utils import get_beijing_now_naive
from src.utils.logger import BeijingLogger

logger = BeijingLogger().get_logger()


class MessageGrouper:
    """消息分组处理类"""

    @staticmethod
    def ensure_message_defaults(messages: List[MessageModel]) -> None:
        """确保消息具有有效的默认值"""
        for msg in messages:
            if msg.sequence_number is None:
                msg.sequence_number = 0
            if msg.created_at is None:
                msg.created_at = get_beijing_now_naive()

    @staticmethod
    def group_messages(messages: List[MessageModel]) -> tuple[Dict, List]:
        """
        将消息按parent_id分组

        Returns:
            (message_groups, standalone_messages)
        """
        message_groups = {}
        standalone_messages = []

        for msg in messages:
            if msg.role == "user" and msg.type != "user_mid_feedback":
                # 普通用户消息作为独立消息
                standalone_messages.append(msg)
            elif msg.role == "assistant" or (msg.role == "user" and msg.type == "user_mid_feedback"):
                # 助手消息和用户中间反馈消息需要分组
                if msg.parent_id:
                    if msg.parent_id not in message_groups:
                        message_groups[msg.parent_id] = []
                    message_groups[msg.parent_id].append(msg)
                else:
                    standalone_messages.append(msg)

        return message_groups, standalone_messages

    @staticmethod
    def find_main_message(related_messages: List[MessageModel]) -> MessageModel:
        """查找主消息（reply类型的助手消息）"""
        # 优先查找reply类型的助手消息
        for msg in related_messages:
            if msg.role == "assistant" and msg.type == "reply":
                return msg

        # 如果没有reply消息，使用第一个助手消息
        for msg in related_messages:
            if msg.role == "assistant":
                return msg

        # 如果还是没找到，返回第一个消息
        return related_messages[0] if related_messages else None

    @staticmethod
    def create_message_copy(msg: MessageModel) -> MessageModel:
        """创建消息副本"""
        current_time = get_beijing_now_naive()

        message_copy = MessageModel(
            id=msg.id,
            conversation_id=msg.conversation_id,
            message_id=msg.message_id,
            role=msg.role,
            content=msg.content,
            type=msg.type,
            agent_name=msg.agent_name,
            agent_session_id=msg.agent_session_id,
            parent_id=msg.parent_id,
            sequence_number=msg.sequence_number if msg.sequence_number is not None else 0,
            tool_outputs=msg.tool_outputs or [],
            status_data=msg.status_data or {},
            created_at=msg.created_at if msg.created_at is not None else current_time,
            updated_at=msg.updated_at if msg.updated_at is not None else current_time
        )

        # 添加特殊字段用于分组数据
        message_copy.grouped_status_data = []
        message_copy.user_mid_feedback = []

        return message_copy

    @staticmethod
    def process_status_message(msg: MessageModel) -> Dict:
        """处理status类型消息"""
        current_time = get_beijing_now_naive()
        status_data = msg.status_data.copy() if msg.status_data else {}

        status_data.update({
            'id': msg.id,
            'message_id': msg.message_id,
            'original_message_id': msg.id,
            'created_at': msg.created_at if msg.created_at is not None else current_time,
            'sequence_number': msg.sequence_number if msg.sequence_number is not None else 0
        })

        return status_data

    @staticmethod
    def process_feedback_request_message(msg: MessageModel, related_messages: List[MessageModel]) -> Dict:
        """处理用户反馈请求消息"""
        current_time = get_beijing_now_naive()
        feedback_data = msg.status_data.copy() if msg.status_data else {}

        feedback_data.update({
            'id': msg.id,
            'message_id': msg.id,
            'original_message_id': msg.id,
            'created_at': msg.created_at if msg.created_at is not None else current_time,
            'sequence_number': msg.sequence_number if msg.sequence_number is not None else 0,
            'type': msg.type
        })

        # 查找对应的用户反馈
        feedback_id = feedback_data.get('feedback_id')
        if feedback_id:
            corresponding_user_feedback = None
            for related_msg in related_messages:
                if (related_msg.type == "user_mid_feedback" and
                    related_msg.status_data and
                    related_msg.status_data.get('original_feedback_id') == feedback_id):
                    corresponding_user_feedback = related_msg
                    break

            if corresponding_user_feedback:
                feedback_data['submitted'] = True
                feedback_data['user_submitted_content'] = corresponding_user_feedback.content
                feedback_data['submitted_at'] = corresponding_user_feedback.created_at
                logger.debug(f"找到feedback_id {feedback_id}的用户回答")
            else:
                feedback_data['submitted'] = False
                logger.debug(f"未找到feedback_id {feedback_id}的用户回答")

        return feedback_data

    @staticmethod
    def process_user_feedback_message(msg: MessageModel) -> Dict:
        """处理用户中间反馈消息"""
        current_time = get_beijing_now_naive()

        feedback_data = {
            'id': msg.id,
            'message_id': msg.message_id,
            'original_message_id': msg.id,
            'type': msg.type,
            'content': msg.content,
            'created_at': msg.created_at if msg.created_at is not None else current_time,
            'sequence_number': msg.sequence_number if msg.sequence_number is not None else 0,
            'status_data': msg.status_data or {},
            'is_user_feedback': True,
            'original_feedback_id': msg.status_data.get('original_feedback_id') if msg.status_data else None
        }

        return feedback_data

    @staticmethod
    def process_tool_output_message(msg: MessageModel) -> List[Dict]:
        """处理工具输出消息"""
        current_time = get_beijing_now_naive()
        tool_outputs = []

        if msg.tool_outputs:
            for tool_output in msg.tool_outputs:
                tool_output_copy = tool_output.copy()
                tool_output_copy.update({
                    'message_id': msg.message_id,
                    'original_message_id': msg.id,
                    'created_at': msg.created_at if msg.created_at is not None else current_time,
                    'sequence_number': msg.sequence_number if msg.sequence_number is not None else 0
                })
                tool_outputs.append(tool_output_copy)

        return tool_outputs

    @classmethod
    def process_grouped_messages(cls, message_groups: Dict) -> List[MessageModel]:
        """处理分组消息，合并相关内容"""
        processed_messages = []

        for parent_id, related_messages in message_groups.items():
            # 查找主消息
            main_message = cls.find_main_message(related_messages)
            if not main_message:
                continue

            # 创建主消息副本
            main_message_copy = cls.create_message_copy(main_message)

            # 排序相关消息
            sorted_related_messages = sorted(
                related_messages,
                key=lambda x: (
                    x.sequence_number if x.sequence_number is not None else 0,
                    x.created_at if x.created_at is not None else get_beijing_now_naive()
                )
            )

            # 处理每个相关消息
            for msg in sorted_related_messages:
                if msg.id == main_message.id:
                    continue

                if msg.type == "status" and msg.status_data:
                    status_data = cls.process_status_message(msg)
                    main_message_copy.grouped_status_data.append(status_data)

                elif msg.type == "user_feedback_request" and msg.status_data:
                    feedback_data = cls.process_feedback_request_message(msg, sorted_related_messages)
                    main_message_copy.grouped_status_data.append(feedback_data)

                elif msg.type == "user_mid_feedback" and msg.role == "user":
                    feedback_data = cls.process_user_feedback_message(msg)
                    # 添加到grouped_status_data中以便前端显示
                    main_message_copy.grouped_status_data.append(feedback_data)
                    # 同时保留在user_mid_feedback列表中（向后兼容）
                    main_message_copy.user_mid_feedback.append(feedback_data)

                elif msg.type == "tool_output" and msg.tool_outputs:
                    tool_outputs = cls.process_tool_output_message(msg)
                    if not main_message_copy.tool_outputs:
                        main_message_copy.tool_outputs = []
                    main_message_copy.tool_outputs.extend(tool_outputs)

                elif msg.type == "thinking" and msg.content:
                    main_message_copy.thinking_content = msg.content
                    main_message_copy.thinking_message_id = msg.id

            processed_messages.append(main_message_copy)

        return processed_messages

    @classmethod
    def group_and_process_messages(cls, messages: List[MessageModel],
                                  skip: int = 0, limit: int = 100) -> List[MessageModel]:
        """
        主函数：分组并处理消息

        Args:
            messages: 原始消息列表
            skip: 跳过的消息数
            limit: 返回的消息数限制

        Returns:
            处理后的消息列表
        """
        # 确保消息有有效的默认值
        cls.ensure_message_defaults(messages)

        # 分组消息
        message_groups, standalone_messages = cls.group_messages(messages)

        # 处理分组消息
        processed_grouped_messages = cls.process_grouped_messages(message_groups)

        # 合并独立消息和处理后的分组消息
        all_processed_messages = standalone_messages + processed_grouped_messages

        # 按时间顺序排序
        all_processed_messages.sort(
            key=lambda x: (
                x.sequence_number if x.sequence_number is not None else 0,
                x.created_at if x.created_at is not None else get_beijing_now_naive()
            )
        )

        # 应用分页
        return all_processed_messages[skip:skip + limit]
