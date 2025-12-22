from sqlalchemy import Boolean, Column, DateTime, String, Integer, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.db.database import Base
from app.utils.datetime_utils import get_beijing_now_naive

class User(Base):
    """User model for storing user related information"""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    phone = Column(String(20), unique=True, index=True)
    email = Column(String(255), nullable=True)
    full_name = Column(String(100), nullable=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime, default=get_beijing_now_naive)
    updated_at = Column(DateTime, default=get_beijing_now_naive, onupdate=get_beijing_now_naive)
    
    # Relationships
    conversations = relationship("Conversation", back_populates="user")
    feedbacks = relationship("Feedback", back_populates="user")


class InvitationCode(Base):
    """Invitation code model for user registration"""
    __tablename__ = "invitation_codes"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(50), unique=True, index=True, nullable=False)
    is_used = Column(Boolean, default=False)
    used_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    used_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=get_beijing_now_naive)
    
    # Relationship - User who used this code
    user = relationship("User", foreign_keys=[used_by]) 