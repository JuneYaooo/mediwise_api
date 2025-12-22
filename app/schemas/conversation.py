from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum
import uuid


class FeedbackTypeEnum(str, Enum):
    like = "like"
    dislike = "dislike"
    comment = "comment"


class FileBase(BaseModel):
    file_name: str
    file_size: int
    file_type: str
    file_path: Optional[str] = None
    file_url: Optional[str] = None
    conversation_id: str
    message_id: Optional[str] = None


class FileCreate(FileBase):
    pass


class FileInDB(FileBase):
    id: str
    conversation_id: str
    message_id: Optional[str] = None
    created_at: datetime

    class Config:
        model_config = {
            "from_attributes": True
        }


class File(FileInDB):
    pass


class FeedbackBase(BaseModel):
    message_id: int
    status_id: Optional[str] = None
    feedback_type: FeedbackTypeEnum
    content: Optional[str] = None


class FeedbackCreate(FeedbackBase):
    user_id: int


class FeedbackInDB(FeedbackBase):
    id: int
    user_id: int
    created_at: datetime

    class Config:
        model_config = {
            "from_attributes": True
        }


class Feedback(FeedbackInDB):
    pass


class MessageBase(BaseModel):
    message_id: Optional[str] = None
    conversation_id: str
    role: str = "user"


class MessageCreate(BaseModel):
    message_id: Optional[str] = None
    conversation_id: str
    role: str = "user"
    content: str
    type: str = "text"


class MessageInDB(MessageBase):
    id: str
    content: Optional[str] = None
    type: Optional[str] = None
    agent_name: Optional[str] = None
    agent_session_id: Optional[str] = None
    parent_id: Optional[str] = None
    sequence_number: Optional[int] = None
    status_data: Optional[Dict[str, Any]] = None
    tool_outputs: Optional[List[Dict[str, Any]]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class Message(BaseModel):
    id: str
    message_id: str
    conversation_id: str
    role: str
    content: Optional[str] = None
    type: Optional[str] = None
    agent_name: Optional[str] = None
    agent_session_id: Optional[str] = None
    parent_id: Optional[str] = None
    sequence_number: Optional[int] = None
    status_data: Optional[Dict[str, Any]] = None
    tool_outputs: Optional[List[Dict[str, Any]]] = None
    created_at: datetime
    updated_at: datetime
    grouped_status_data: Optional[List[Dict[str, Any]]] = None
    user_mid_feedback: Optional[List[Dict[str, Any]]] = None
    thinking_content: Optional[str] = None

    class Config:
        orm_mode = True


class ConversationBase(BaseModel):
    title: Optional[str] = None
    is_active: bool = True


class ConversationCreate(ConversationBase):
    session_id: str
    user_id: Optional[str] = None


class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    is_active: Optional[bool] = None
    patient_data: Optional[Dict[str, Any]] = None


class ConversationInDB(ConversationBase):
    id: str
    session_id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    patient_data: Optional[Dict[str, Any]] = None

    class Config:
        orm_mode = True


class Conversation(ConversationInDB):
    messages: Optional[List[Message]] = None
    files: Optional[List['File']] = None


class StatusMessageCreate(BaseModel):
    conversation_id: str
    message_id: Optional[str] = None
    status: str
    status_msg: str
    agent_name: Optional[str] = None
    agent_session_id: Optional[str] = None
    need_feedback: bool = False


class ToolOutputCreate(BaseModel):
    conversation_id: str
    message_id: Optional[str] = None
    tool_name: str
    tool_type: str
    agent_name: Optional[str] = None
    agent_session_id: Optional[str] = None
    content: Any


class FeedbackCreate(BaseModel):
    message_id: str
    status_id: Optional[str] = None
    feedback_type: str
    content: Optional[str] = None


class Feedback(FeedbackCreate):
    id: str
    user_id: str
    created_at: datetime

    class Config:
        orm_mode = True


class File(BaseModel):
    id: str
    file_id: str
    conversation_id: str
    message_id: Optional[str] = None
    filename: str
    file_path: str
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    created_at: datetime

    class Config:
        orm_mode = True 