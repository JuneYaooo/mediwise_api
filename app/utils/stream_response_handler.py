"""
流式响应处理器
封装chat_with_medical_assistant中的流式响应处理逻辑
"""
import json
from typing import Dict, Any, Optional, AsyncGenerator
from app.utils.message_handler import save_message_to_db
from app.utils.patient_data_handler import handle_tool_output_storage, update_patient_data
from src.utils.logger import BeijingLogger

logger = BeijingLogger().get_logger()


class StreamResponseHandler:
    """流式响应处理器"""

    def __init__(self, conversation_id: str, user_message_id: str):
        """
        初始化处理器

        Args:
            conversation_id: 会话ID
            user_message_id: 用户消息ID（用于关联助手响应）
        """
        self.conversation_id = conversation_id
        self.user_message_id = user_message_id

        # 跟踪当前消息ID
        self.current_message_id = None

        # 累积不同类型内容的字典
        self.accumulated_contents = {
            "reply": "",
            "thinking": ""
        }
        self.accumulated_datas = {
            "reply": None,
            "thinking": None
        }

        # 记录上一次收到的消息类型
        self.last_object_type = None

    async def save_accumulated_content(self, msg_type: str) -> Optional[Any]:
        """
        保存累积的内容

        Args:
            msg_type: 消息类型（reply或thinking）

        Returns:
            保存的消息对象
        """
        accumulated_data = self.accumulated_datas.get(msg_type)
        accumulated_content = self.accumulated_contents.get(msg_type)

        if not accumulated_data or not accumulated_content or not accumulated_content.strip():
            return None

        # 复制数据，设置正确的类型
        save_data = accumulated_data.copy()
        save_data["type"] = msg_type

        # 更新内容
        if "choices" in save_data and len(save_data["choices"]) > 0:
            if "delta" in save_data["choices"][0]:
                save_data["choices"][0]["delta"]["content"] = accumulated_content

        # 设置用户消息ID
        save_data["user_message_id"] = self.user_message_id

        # 保存到数据库
        saved_message = await save_message_to_db(save_data, self.conversation_id)

        if saved_message:
            logger.debug(
                f"保存累积内容: type={msg_type}, "
                f"db_id={saved_message.id}, content_length={len(accumulated_content)}"
            )

        return saved_message

    async def save_all_accumulated_contents(self) -> None:
        """保存所有类型的累积内容"""
        for msg_type in ["reply", "thinking"]:
            await self.save_accumulated_content(msg_type)

    def reset_accumulated_contents(self) -> None:
        """重置所有累积内容"""
        self.accumulated_contents = {
            "reply": "",
            "thinking": ""
        }
        self.accumulated_datas = {
            "reply": None,
            "thinking": None
        }

    async def handle_message_id_change(self, new_message_id: str) -> None:
        """
        处理消息ID变化

        Args:
            new_message_id: 新的消息ID
        """
        if new_message_id != self.current_message_id:
            # 保存之前的累积内容
            await self.save_all_accumulated_contents()
            # 重置累积内容
            self.reset_accumulated_contents()
            # 更新当前消息ID
            self.current_message_id = new_message_id

    async def handle_object_type_change(self, new_object_type: str) -> None:
        """
        处理消息对象类型变化

        Args:
            new_object_type: 新的对象类型
        """
        if self.last_object_type is not None and new_object_type != self.last_object_type:
            # 保存之前的累积内容
            await self.save_all_accumulated_contents()
            # 重置累积内容
            self.reset_accumulated_contents()

        self.last_object_type = new_object_type

    async def handle_status_message(self, data: Dict) -> Dict:
        """
        处理status消息

        Args:
            data: 消息数据

        Returns:
            更新后的消息数据（包含数据库ID）
        """
        data["user_message_id"] = self.user_message_id

        saved_message = await save_message_to_db(data, self.conversation_id)

        if saved_message:
            data["id"] = saved_message.id
            data["db_message_id"] = saved_message.id
            data["original_stream_id"] = data.get("id")
            logger.debug(f"保存status消息: db_id={saved_message.id}")

        return data

    async def handle_feedback_request_message(self, data: Dict) -> Dict:
        """
        处理用户反馈请求消息

        Args:
            data: 消息数据

        Returns:
            更新后的消息数据（包含数据库ID）
        """
        data["user_message_id"] = self.user_message_id

        saved_message = await save_message_to_db(data, self.conversation_id)

        if saved_message:
            data["id"] = saved_message.id
            data["db_message_id"] = saved_message.message_id
            data["original_stream_id"] = data.get("id")
            logger.debug(f"保存反馈请求消息: db_id={saved_message.message_id}")

        return data

    async def handle_tool_output_message(self, data: Dict) -> Dict:
        """
        处理工具输出消息

        Args:
            data: 消息数据

        Returns:
            更新后的消息数据（包含数据库ID）
        """
        data["user_message_id"] = self.user_message_id

        # 处理patient_details表的数据存储
        try:
            await handle_tool_output_storage(data, self.conversation_id)
        except Exception as e:
            logger.error(f"处理工具输出存储失败: {str(e)}")

        saved_message = await save_message_to_db(data, self.conversation_id)

        if saved_message:
            data["id"] = saved_message.id
            data["db_message_id"] = saved_message.id
            data["original_stream_id"] = data.get("id")
            logger.debug(f"保存工具输出消息: db_id={saved_message.id}")

        return data

    def handle_chunk_message(self, data: Dict) -> None:
        """
        处理流式消息块

        Args:
            data: 消息数据
        """
        chunk_content = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
        if not chunk_content:
            return

        message_type = data.get("type")
        # 确定消息类型，默认为reply
        msg_type = message_type if message_type in ["reply", "thinking"] else "reply"

        # 累积特定类型的内容
        self.accumulated_contents[msg_type] += chunk_content

        # 保存完整的数据包以便后续处理
        if self.accumulated_datas[msg_type] is None:
            self.accumulated_datas[msg_type] = data.copy()

    async def handle_completion_message(self, data: Dict) -> Optional[Dict]:
        """
        处理完整消息

        Args:
            data: 消息数据

        Returns:
            更新后的消息数据（如果保存成功）
        """
        content = ""
        if "choices" in data and len(data["choices"]) > 0 and "message" in data["choices"][0]:
            content = data["choices"][0]["message"].get("content", "")

        # 只有内容非空时才保存
        if not content or not content.strip():
            return None

        data["user_message_id"] = self.user_message_id

        saved_message = await save_message_to_db(data, self.conversation_id)

        if saved_message:
            data["id"] = saved_message.id
            data["db_message_id"] = saved_message.id
            data["original_stream_id"] = data.get("id")
            logger.debug(f"保存完整消息: db_id={saved_message.id}")

        # 更新会话的患者数据（如果存在）
        if "patient_timeline" in data:
            await update_patient_data(
                self.conversation_id,
                data.get("patient_timeline", {})
            )

        # 重置累积变量
        self.reset_accumulated_contents()

        return data

    async def process_chunk(self, response_chunk: str) -> Optional[str]:
        """
        处理单个响应块

        Args:
            response_chunk: 原始响应块

        Returns:
            处理后的响应块（JSON格式）
        """
        # 跳过空行
        if not response_chunk.strip():
            return None

        try:
            # 移除'data: '前缀并解析JSON
            data_str = response_chunk.replace("data: ", "").strip()
            data = json.loads(data_str)

            # 获取消息信息
            message_id = data.get("id")
            message_object = data.get("object")

            # 处理消息ID变化
            if message_id:
                await self.handle_message_id_change(message_id)

            # 如果找不到有效的消息对象类型，直接返回
            if not message_object:
                return f"data: {json.dumps(data)}\n\n"

            # 处理对象类型变化
            await self.handle_object_type_change(message_object)

            # 根据消息对象类型分别处理
            if message_object == "medical.status":
                data = await self.handle_status_message(data)

            elif message_object == "medical.user_feedback_request":
                data = await self.handle_feedback_request_message(data)

            elif message_object == "medical.tool.output":
                data = await self.handle_tool_output_message(data)

            elif message_object == "medical.completion.chunk":
                self.handle_chunk_message(data)

            elif message_object == "medical.completion":
                updated_data = await self.handle_completion_message(data)
                if updated_data:
                    data = updated_data

            # 返回处理后的数据
            return f"data: {json.dumps(data)}\n\n"

        except json.JSONDecodeError as e:
            logger.error(f"Error parsing response chunk: {e}")
            return f"data: {json.dumps({'error': str(e)})}\n\n"
        except Exception as e:
            logger.error(f"Error processing chunk: {e}")
            return None

    async def finalize(self) -> None:
        """流结束时的清理工作"""
        # 保存所有剩余的累积内容
        await self.save_all_accumulated_contents()
