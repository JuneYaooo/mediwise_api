"""
会话工具
处理会话相关的辅助功能，如生成会话标题等
"""

import os
import asyncio
from typing import List

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.conversation import Conversation as ConversationModel, Message as MessageModel
from src.utils.logger import BeijingLogger

logger = BeijingLogger().get_logger()


async def generate_conversation_title(conversation_id: str, messages: List[MessageModel]) -> None:
    """
    使用ChatOpenAI模型生成会话标题

    Args:
        conversation_id: 会话ID
        messages: 消息列表（可以为空，会从数据库查询）
    """
    try:
        # 等待一小段时间，让助手的回复被保存
        await asyncio.sleep(2)

        # 从数据库查询最新消息
        db = SessionLocal()
        try:
            # 获取数据库中的最新消息
            latest_messages = db.query(MessageModel).filter(
                MessageModel.conversation_id == conversation_id
            ).order_by(MessageModel.created_at).all()

            # 使用传入的消息作为后备
            if latest_messages:
                messages = latest_messages
        finally:
            db.close()

        # 只有至少2条消息时才生成标题
        if len(messages) < 2:
            return

        # 获取前几条消息作为上下文
        context_messages = messages[:min(6, len(messages))]
        messages_text = "\n".join([f"{msg.role}: {msg.content}" for msg in context_messages if msg.content])

        # 创建生成标题的提示词
        prompt = f"""请你是一个AI助手，根据以下医疗咨询对话，生成一个简短、具体的对话标题。
标题应该：
1. 不超过10个汉字
2. 能够准确反映用户的主要问题或咨询内容
3. 使用中文，简洁明了
4. 不要使用引号或其他标点符号

对话内容：
{messages_text}

请直接返回标题，不要包含任何解释或引导词。"""

        # 使用环境变量初始化模型
        model = ChatOpenAI(
            model=os.getenv("QWEN_MODEL_NAME", "Qwen/Qwen2.5-72B-Instruct-128K"),
            api_key=os.getenv("SILICONFLOW_API_KEY", ""),
            base_url=os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1")
        )

        # 生成标题
        model_messages = [HumanMessage(content=prompt)]
        response = model.invoke(model_messages)
        title = response.content.strip()

        # 限制标题长度
        if len(title) > 255:
            title = title[:252] + "..."

        # 更新数据库中的会话标题
        db = SessionLocal()
        try:
            conversation = db.query(ConversationModel).filter(
                ConversationModel.id == conversation_id
            ).first()

            if conversation:
                conversation.title = title
                db.add(conversation)
                db.commit()
                logger.info(f"Updated conversation title to: {title}")
        finally:
            db.close()

    except Exception as e:
        logger.error(f"Error generating conversation title: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
