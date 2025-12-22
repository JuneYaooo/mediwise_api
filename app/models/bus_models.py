"""
业务数据库模型 - 映射到 bus_* 和 sys_* 表
"""
from sqlalchemy import Boolean, Column, DateTime, String, Integer, BigInteger, ForeignKey, Text, JSON, TIMESTAMP
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from app.db.database import Base
from app.utils.datetime_utils import get_beijing_now_naive


class Patient(Base):
    """患者信息表 - 映射到 bus_patient"""
    __tablename__ = "bus_patient"

    patient_id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    patient_no = Column(String(50), nullable=True)
    name = Column(String(50), nullable=False)
    gender = Column(String(50), nullable=True)
    birth_date = Column(TIMESTAMP, nullable=True)
    id_card = Column(String(50), nullable=True)
    phone = Column(String(50), nullable=True)
    emergency_contact = Column(String(50), nullable=True)
    emergency_phone = Column(String(50), nullable=True)
    address = Column(String(150), nullable=True)
    blood_type = Column(String(50), nullable=True)
    allergies = Column(Text, nullable=True)
    medical_history = Column(Text, nullable=True)
    status = Column(String(50), nullable=True)
    admission_date = Column(TIMESTAMP, nullable=True)
    discharge_date = Column(TIMESTAMP, nullable=True)
    raw_file_ids = Column(Text, nullable=True, comment="原始上传文件ID列表（JSON数组格式）")
    created_by = Column(String(50), nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, default=get_beijing_now_naive)
    updated_at = Column(TIMESTAMP, nullable=False, default=get_beijing_now_naive, onupdate=get_beijing_now_naive)
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(TIMESTAMP, nullable=True)

    # Relationships
    conversations = relationship("PatientConversation", back_populates="patient")
    files = relationship("PatientFile", back_populates="patient")
    structured_data = relationship("PatientStructuredData", back_populates="patient")


class PatientConversation(Base):
    """患者会话表 - 映射到 bus_patient_conversations"""
    __tablename__ = "bus_patient_conversations"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(50), nullable=True)
    patient_id = Column(String(36), ForeignKey("bus_patient.patient_id"), nullable=False)
    user_id = Column(String(36), nullable=False)  # 注意：这里暂时不做外键，因为user_id是字符串，但sys_user表的主键是bigint
    title = Column(String(255), nullable=True)
    conversation_type = Column(String(20), nullable=True)
    status = Column(String(255), nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=get_beijing_now_naive)
    updated_at = Column(TIMESTAMP, nullable=False, default=get_beijing_now_naive, onupdate=get_beijing_now_naive)
    last_message_at = Column(TIMESTAMP, nullable=True)
    closed_at = Column(TIMESTAMP, nullable=True)
    meta_data = Column("metadata", JSON, nullable=False, default=dict)  # 使用meta_data但映射到metadata列

    # Relationships
    patient = relationship("Patient", back_populates="conversations")
    messages = relationship("ConversationMessage", back_populates="conversation")
    structured_data = relationship("PatientStructuredData", back_populates="conversation")


class ConversationMessage(Base):
    """会话消息表 - 映射到 bus_conversation_messages"""
    __tablename__ = "bus_conversation_messages"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String(36), ForeignKey("bus_patient_conversations.id"), nullable=False)
    message_id = Column(String(50), nullable=True)
    role = Column(String(50), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=True)
    type = Column(String(20), nullable=True)
    agent_name = Column(String(50), nullable=True)
    agent_session_id = Column(String(50), nullable=True)
    parent_id = Column(String(50), nullable=True)
    sequence_number = Column(Integer, nullable=True)
    tooloutputs = Column(JSON, nullable=False, default=list)
    statusdata = Column(JSON, nullable=False, default=dict)
    created_at = Column(TIMESTAMP, nullable=False, default=get_beijing_now_naive)
    updated_at = Column(TIMESTAMP, nullable=False, default=get_beijing_now_naive, onupdate=get_beijing_now_naive)

    # Relationships
    conversation = relationship("PatientConversation", back_populates="messages")


class PatientStructuredData(Base):
    """患者结构化数据表 - 映射到 bus_patient_structured_data"""
    __tablename__ = "bus_patient_structured_data"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    patient_id = Column(String(36), ForeignKey("bus_patient.patient_id"), nullable=False)
    data_type = Column(String(20), nullable=False)  # timeline, journey, mdt_report等
    data_category = Column(String(100), nullable=True)
    title = Column(String(255), nullable=True)
    structuredcontent = Column(JSON, nullable=False, default=dict)
    text_content = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    conversation_id = Column(String(36), ForeignKey("bus_patient_conversations.id"), nullable=True)
    version = Column(Integer, nullable=True)
    parent_version_id = Column(String(36), nullable=True)
    created_by = Column(String(36), nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, default=get_beijing_now_naive)
    updated_at = Column(TIMESTAMP, nullable=False, default=get_beijing_now_naive, onupdate=get_beijing_now_naive)
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(TIMESTAMP, nullable=True)

    # Relationships
    patient = relationship("Patient", back_populates="structured_data")
    conversation = relationship("PatientConversation", back_populates="structured_data")


class PatientFile(Base):
    """患者文件表 - 映射到 bus_patient_files"""
    __tablename__ = "bus_patient_files"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    patient_id = Column(String(36), ForeignKey("bus_patient.patient_id"), nullable=False)
    conversation_id = Column(String(36), nullable=True, comment="关联的对话ID（如果通过对话上传）")

    # 基本文件信息
    file_name = Column(String(255), nullable=False)
    upload_filename = Column(String(255), nullable=True, comment="上传后的文件名（包含UUID和扩展名）")
    file_extension = Column(String(20), nullable=True, comment="文件扩展名（如pdf, jpg, zip）")
    file_path = Column(String(500), nullable=False)
    file_url = Column(String(500), nullable=True)
    file_type = Column(String(50), nullable=True)
    file_size = Column(BigInteger, nullable=True)
    file_category = Column(String(20), nullable=True)
    file_hash = Column(String(64), nullable=True)

    # 文件来源信息
    source_type = Column(String(30), nullable=True, default="uploaded", comment="文件来源类型：uploaded, extracted_from_pdf, extracted_from_zip, rendered_pdf_page")
    parent_pdf_uuid = Column(String(36), nullable=True, comment="父PDF文件UUID（如果是从PDF提取的图片）")
    parent_pdf_filename = Column(String(255), nullable=True, comment="父PDF文件名")
    parent_zip_uuid = Column(String(36), nullable=True, comment="父ZIP文件UUID（如果是从ZIP解压的）")
    parent_zip_filename = Column(String(255), nullable=True, comment="父ZIP文件名")
    is_from_zip = Column(Boolean, nullable=False, default=False, comment="是否来自ZIP文件")
    is_from_pdf = Column(Boolean, nullable=False, default=False, comment="是否来自PDF文件")

    # PDF相关字段
    extraction_mode = Column(String(50), nullable=True, comment="PDF提取模式（text_only, with_images等）")
    extracted_image_count = Column(Integer, nullable=True, comment="PDF提取的图片数量")
    page_number = Column(Integer, nullable=True, comment="在PDF中的页码（如果是PDF提取的图片）")
    image_index_in_page = Column(Integer, nullable=True, comment="在页面中的图片索引")

    # 医学影像相关
    has_medical_image = Column(Boolean, nullable=False, default=False, comment="是否包含医学影像")
    image_bbox = Column(JSON, nullable=True, comment="医学影像边界框（归一化坐标0-1，用于裁剪）")
    cropped_image_uuid = Column(String(36), nullable=True, comment="裁剪后的医学影像UUID")
    cropped_image_url = Column(String(500), nullable=True, comment="裁剪后的医学影像URL")
    cropped_image_available = Column(Boolean, nullable=False, default=False, comment="是否有裁剪后的医学影像")

    # 文件元数据
    exam_date = Column(TIMESTAMP, nullable=True)
    exam_type = Column(String(100), nullable=True)
    department = Column(String(100), nullable=True)
    doctor = Column(String(100), nullable=True)

    # 提取的内容
    extracted_text = Column(Text, nullable=True)
    extractedmetadata = Column(JSON, nullable=False, default=dict)
    extraction_failed = Column(Boolean, nullable=False, default=False, comment="内容提取是否失败")
    extraction_success = Column(Boolean, nullable=True, comment="内容提取是否成功")
    extraction_error = Column(Text, nullable=True, comment="提取失败的错误信息")

    # 上传信息
    uploaded_by = Column(String(50), nullable=False)
    uploaded_at = Column(TIMESTAMP, nullable=False, default=get_beijing_now_naive)
    upload_timestamp = Column(TIMESTAMP, nullable=True, comment="上传时间戳")
    created_at = Column(TIMESTAMP, nullable=False, default=get_beijing_now_naive)
    updated_at = Column(TIMESTAMP, nullable=False, default=get_beijing_now_naive, onupdate=get_beijing_now_naive)
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(TIMESTAMP, nullable=True)

    # Relationships
    patient = relationship("Patient", back_populates="files")


class SysUser(Base):
    """系统用户表 - 映射到 sys_user"""
    __tablename__ = "sys_user"

    user_id = Column(BigInteger, primary_key=True, index=True)  # 使用自增序列
    user_name = Column(String(50), nullable=False)
    real_name = Column(String(50), nullable=False)
    password = Column(String(150), nullable=False)
    gender = Column(Integer, nullable=True)
    activated = Column(Boolean, nullable=False, default=True)
    email = Column(String(50), nullable=True)
    phone = Column(String(50), nullable=True)
    dept_id = Column(BigInteger, nullable=False)
    avatar = Column(String(255), nullable=True)
    status = Column(Boolean, nullable=False, default=True)
    is_super_admin = Column(Boolean, nullable=False, default=False)
    last_login_time = Column(TIMESTAMP, nullable=True)
    last_login_ip = Column(String(50), nullable=True)
    created_by = Column(BigInteger, nullable=False)
    created_at = Column(TIMESTAMP, nullable=False, default=get_beijing_now_naive)
    updated_by = Column(BigInteger, nullable=False)
    updated_at = Column(TIMESTAMP, nullable=False, default=get_beijing_now_naive, onupdate=get_beijing_now_naive)
    is_deleted = Column(Boolean, nullable=False, default=False)
