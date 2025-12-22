from sqlalchemy import Boolean, Column, DateTime, String, Integer, ForeignKey, Text, JSON, Enum
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
import uuid

from app.db.database import Base
from app.utils.datetime_utils import get_beijing_now_naive

# 导入MEDIUMTEXT类型
from sqlalchemy.dialects.mysql import MEDIUMTEXT

class MessageType(enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"
    
class MessageContentType(enum.Enum):
    text = "text"
    status = "status"
    thinking = "thinking"
    reply = "reply"
    tool_output = "tool_output"
    
class FeedbackType(enum.Enum):
    like = "like"
    dislike = "dislike"
    comment = "comment"

class Conversation(Base):
    """Conversation model for storing chat sessions"""
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(50), unique=True, index=True)
    title = Column(String(255), nullable=True)
    user_id = Column(String(36), ForeignKey("users.id"))
    created_at = Column(DateTime, default=get_beijing_now_naive)
    updated_at = Column(DateTime, default=get_beijing_now_naive, onupdate=get_beijing_now_naive)
    is_active = Column(Boolean, default=True)
    
    # JSON field to store the most recent patient_data
    patient_data = Column(MutableDict.as_mutable(JSON), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    files = relationship("File", back_populates="conversation", cascade="all, delete-orphan")
    patient_detail = relationship("PatientDetail", back_populates="conversation", cascade="all, delete-orphan", uselist=False)


class Message(Base):
    """Message model for storing individual messages in a conversation"""
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey("conversations.id"))
    message_id = Column(String(50), unique=True, index=True)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(MEDIUMTEXT, nullable=True)
    type = Column(String(20), nullable=True)  # status, thinking, reply, tool_output
    agent_name = Column(String(50), nullable=True)
    agent_session_id = Column(String(50), nullable=True)
    parent_id = Column(String(50), nullable=True)  # For linking related messages (e.g. thinking to reply)
    sequence_number = Column(Integer, nullable=True)  # For tracking the chronological order
    
    # JSON fields for tool outputs and status messages
    tool_outputs = Column(MutableList.as_mutable(JSON), nullable=True)
    status_data = Column(MutableDict.as_mutable(JSON), nullable=True)
    
    created_at = Column(DateTime, default=get_beijing_now_naive)
    updated_at = Column(DateTime, default=get_beijing_now_naive, onupdate=get_beijing_now_naive)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    feedbacks = relationship("Feedback", back_populates="message", cascade="all, delete-orphan")


class File(Base):
    """File model for storing uploaded files"""
    __tablename__ = "files"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    file_id = Column(String(50), unique=True, index=True)
    conversation_id = Column(String(36), ForeignKey("conversations.id"))
    message_id = Column(String(36), ForeignKey("messages.id"), nullable=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=True)
    file_size = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=get_beijing_now_naive)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="files")


class PatientDetail(Base):
    """Patient detail model for storing comprehensive patient information"""
    __tablename__ = "patient_details"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey("conversations.id"), unique=True, index=True)
    
    # 原始数据存储
    raw_text_data = Column(MEDIUMTEXT, nullable=True, comment="患者原始文本数据")
    raw_files_data = Column(MEDIUMTEXT, nullable=True, comment="原始文件信息JSON字符串（列表格式），包含文件UUID、上传文件名、文件后缀、云存储位置、提取的文本内容、文件类型等")
    raw_file_ids = Column(MEDIUMTEXT, nullable=True, comment="原始文件UUID列表，以逗号分隔的字符串形式存储")
    
    # 结构化数据存储
    patient_timeline = Column(MEDIUMTEXT, nullable=True, comment="患者时间轴数据JSON字符串")
    patient_journey = Column(MEDIUMTEXT, nullable=True, comment="患者就诊历程数据JSON字符串，包含image_url字段存储图片URL")
    mdt_simple_report = Column(MEDIUMTEXT, nullable=True, comment="MDT简化报告数据JSON字符串")
    ppt_info = Column(MEDIUMTEXT, nullable=True, comment="PPT生成信息JSON字符串，包含file_uuid、file_key、qiniu_url等")

    # 全量内容存储
    patient_full_content = Column(MEDIUMTEXT, nullable=True, comment="患者所有内容拼接的完整文本")

    # 文件提取统计信息
    extraction_statistics = Column(MEDIUMTEXT, nullable=True, comment="文件内容提取统计信息JSON字符串，包含总文件数、成功数、失败数、失败原因等")

    # 时间戳
    created_at = Column(DateTime, default=get_beijing_now_naive)
    updated_at = Column(DateTime, default=get_beijing_now_naive, onupdate=get_beijing_now_naive)
    
    # Relationships
    conversation = relationship("Conversation", back_populates="patient_detail")


class Feedback(Base):
    """Feedback model for storing user feedback on messages"""
    __tablename__ = "feedbacks"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"))
    message_id = Column(String(36), ForeignKey("messages.id"))
    status_id = Column(String(50), nullable=True)  # ID of the status within the message
    feedback_type = Column(Enum(FeedbackType), nullable=False)
    content = Column(MEDIUMTEXT, nullable=True)  # Optional feedback text
    created_at = Column(DateTime, default=get_beijing_now_naive)
    
    # Relationships
    user = relationship("User", back_populates="feedbacks")
    message = relationship("Message", back_populates="feedbacks") 