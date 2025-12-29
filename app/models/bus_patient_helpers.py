"""
业务患者数据Helper - 处理 bus_* 表的数据操作
"""
import json
import uuid
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.bus_models import (
    Patient,
    PatientConversation,
    ConversationMessage,
    PatientStructuredData,
    PatientFile,
    UserPatientAccess
)
from app.utils.datetime_utils import get_beijing_now_naive
from src.utils.logger import BeijingLogger

logger = BeijingLogger().get_logger()


class BusPatientHelper:
    """处理业务患者数据的Helper类"""

    @staticmethod
    def create_or_get_patient(
        db: Session,
        name: str,
        user_id: str,
        patient_no: Optional[str] = None,
        gender: Optional[str] = None,
        phone: Optional[str] = None,
        raw_file_ids: Optional[List[str]] = None,
        **kwargs
    ) -> Patient:
        """创建或获取患者记录"""

        # 检查是否已存在同名患者（简化逻辑，实际可能需要更复杂的匹配）
        # 这里先创建新患者
        patient = Patient(
            patient_id=str(uuid.uuid4()),
            patient_no=patient_no or f"P{datetime.now().strftime('%Y%m%d%H%M%S')}",
            name=name,
            gender=gender,
            phone=phone,
            status="active",
            raw_file_ids=",".join(raw_file_ids) if raw_file_ids else None,
            created_by=user_id,
            created_at=get_beijing_now_naive(),
            updated_at=get_beijing_now_naive(),
            is_deleted=False
        )

        # 更新其他字段
        for key, value in kwargs.items():
            if hasattr(patient, key):
                setattr(patient, key, value)

        db.add(patient)
        db.flush()  # 获取patient_id但不提交

        logger.info(f"创建患者记录: {patient.patient_id} - {name}, 文件数: {len(raw_file_ids) if raw_file_ids else 0}")
        return patient

    @staticmethod
    def create_user_patient_access(
        db: Session,
        user_id: str,
        patient_id: str,
        role: str = "owner",
        can_edit: bool = True,
        can_delete: bool = False,
        can_share: bool = False,
        granted_by: Optional[str] = None
    ) -> UserPatientAccess:
        """
        创建用户患者访问权限记录

        Args:
            db: 数据库会话
            user_id: 用户ID
            patient_id: 患者ID
            role: 角色 (owner: 所有者, editor: 编辑者, viewer: 查看者)，默认 owner
            can_edit: 是否可以编辑
            can_delete: 是否可以删除
            can_share: 是否可以分享
            granted_by: 授权人ID，如果为None则使用user_id

        Returns:
            UserPatientAccess: 访问权限记录
        """
        # 检查是否已存在权限记录
        existing_access = db.query(UserPatientAccess).filter(
            UserPatientAccess.user_id == user_id,
            UserPatientAccess.patient_id == patient_id,
            UserPatientAccess.is_active == True
        ).first()

        if existing_access:
            # 如果已存在，更新权限
            existing_access.role = role
            existing_access.can_edit = can_edit
            existing_access.can_delete = can_delete
            existing_access.can_share = can_share
            db.flush()
            logger.info(f"更新用户患者访问权限: user_id={user_id}, patient_id={patient_id}, role={role}")
            return existing_access

        # 创建新的权限记录
        access_record = UserPatientAccess(
            id=str(uuid.uuid4()),
            user_id=user_id,
            patient_id=patient_id,
            role=role,
            can_edit=can_edit,
            can_delete=can_delete,
            can_share=can_share,
            granted_by=granted_by or user_id,
            granted_at=get_beijing_now_naive(),
            is_active=True,
            created_at=get_beijing_now_naive()
        )

        db.add(access_record)
        db.flush()

        logger.info(f"创建用户患者访问权限: user_id={user_id}, patient_id={patient_id}, role={role}")
        return access_record

    @staticmethod
    def create_conversation(
        db: Session,
        patient_id: str,
        user_id: str,
        title: str,
        session_id: Optional[str] = None,
        conversation_type: str = "patient_data_extraction"
    ) -> PatientConversation:
        """创建患者会话记录"""

        conversation = PatientConversation(
            id=str(uuid.uuid4()),
            session_id=session_id or f"session_{uuid.uuid4()}",
            patient_id=patient_id,
            user_id=user_id,
            title=title,
            conversation_type=conversation_type,
            status="active",
            created_at=get_beijing_now_naive(),
            updated_at=get_beijing_now_naive(),
            meta_data={}
        )

        db.add(conversation)
        db.flush()

        logger.info(f"创建会话记录: {conversation.id} for 患者 {patient_id}")
        return conversation

    @staticmethod
    def save_structured_data(
        db: Session,
        patient_id: str,
        conversation_id: str,
        user_id: str,
        patient_timeline: Optional[Dict[str, Any]] = None,
        patient_journey: Optional[Dict[str, Any]] = None,
        mdt_simple_report: Optional[Dict[str, Any]] = None,
        patient_full_content: Optional[str] = None
    ) -> List[PatientStructuredData]:
        """保存结构化患者数据到 bus_patient_structured_data 表

        注意：文件ID应该存储在 bus_patient.raw_file_ids 中，而不是这里
        """

        structured_data_records = []

        # 1. 保存患者时间轴 (timeline)
        if patient_timeline:
            timeline_record = PatientStructuredData(
                id=str(uuid.uuid4()),
                patient_id=patient_id,
                data_type="timeline",
                data_category="patient_timeline",
                title="患者时间轴",
                structuredcontent=patient_timeline,
                text_content=patient_full_content,
                conversation_id=conversation_id,
                version=1,
                created_by=user_id,
                created_at=get_beijing_now_naive(),
                updated_at=get_beijing_now_naive(),
                is_deleted=False
            )
            db.add(timeline_record)
            structured_data_records.append(timeline_record)
            logger.info(f"保存患者时间轴数据: {timeline_record.id}")

        # 2. 保存患者就诊历程 (journey)
        if patient_journey:
            journey_record = PatientStructuredData(
                id=str(uuid.uuid4()),
                patient_id=patient_id,
                data_type="journey",
                data_category="patient_journey",
                title="患者就诊历程",
                structuredcontent=patient_journey,
                conversation_id=conversation_id,
                version=1,
                created_by=user_id,
                created_at=get_beijing_now_naive(),
                updated_at=get_beijing_now_naive(),
                is_deleted=False
            )
            db.add(journey_record)
            structured_data_records.append(journey_record)
            logger.info(f"保存患者就诊历程数据: {journey_record.id}")

        # 3. 保存MDT简化报告 (mdt_report)
        if mdt_simple_report:
            mdt_record = PatientStructuredData(
                id=str(uuid.uuid4()),
                patient_id=patient_id,
                data_type="mdt_report",
                data_category="mdt_simple_report",
                title="MDT简化报告",
                structuredcontent=mdt_simple_report,
                conversation_id=conversation_id,
                version=1,
                created_by=user_id,
                created_at=get_beijing_now_naive(),
                updated_at=get_beijing_now_naive(),
                is_deleted=False
            )
            db.add(mdt_record)
            structured_data_records.append(mdt_record)
            logger.info(f"保存MDT简化报告数据: {mdt_record.id}")

        db.flush()
        return structured_data_records

    @staticmethod
    def save_ppt_data(
        db: Session,
        patient_id: str,
        ppt_data: Dict[str, Any],
        treatment_gantt_data: list = None,
        user_id: Optional[str] = None
    ) -> PatientStructuredData:
        """
        保存 PPT 流程数据（LLM生成的结构化数据）到 bus_patient_structured_data 表

        ⚠️ 替换策略：同一患者多次生成PPT时，会更新现有记录而不是新增

        data_type: "ppt_data"

        Args:
            db: 数据库会话
            patient_id: 患者ID
            ppt_data: LLM生成的PPT结构化数据（pptTemplate2Vm）
            treatment_gantt_data: 治疗甘特图数据列表（可选）
            user_id: 创建用户ID（可选）

        Returns:
            PatientStructuredData 记录
        """
        import uuid
        from app.utils.datetime_utils import get_beijing_now_naive

        content = {
            "ppt_data": ppt_data,
            "treatment_gantt_data": treatment_gantt_data or []
        }

        # 查找是否已存在该患者的 ppt_data 记录
        existing_record = db.query(PatientStructuredData).filter(
            PatientStructuredData.patient_id == patient_id,
            PatientStructuredData.data_type == "ppt_data",
            PatientStructuredData.is_deleted == False
        ).first()

        if existing_record:
            # 更新现有记录
            existing_record.structuredcontent = content
            existing_record.updated_at = get_beijing_now_naive()
            existing_record.updated_by = user_id or "system"
            db.flush()
            logger.info(f"更新患者PPT流程数据: patient_id={patient_id}, record_id={existing_record.id}")
            return existing_record
        else:
            # 创建新记录
            ppt_data_record = PatientStructuredData(
                id=str(uuid.uuid4()),
                patient_id=patient_id,
                data_type="ppt_data",
                data_category="ppt_generation",
                title="PPT生成流程数据",
                structuredcontent=content,
                version=1,
                created_by=user_id or "system",
                created_at=get_beijing_now_naive(),
                updated_at=get_beijing_now_naive(),
                is_deleted=False
            )

            db.add(ppt_data_record)
            db.flush()

            logger.info(f"创建患者PPT流程数据: patient_id={patient_id}, record_id={ppt_data_record.id}")
            return ppt_data_record

    @staticmethod
    def save_ppt_final(
        db: Session,
        patient_id: str,
        ppt_url: str = None,
        local_path: str = None,
        qiniu_url: str = None,
        file_uuid: str = None,
        template_id: str = None,
        generated_at: str = None,
        user_id: Optional[str] = None,
        **kwargs
    ) -> PatientStructuredData:
        """
        保存 PPT 最终成果（PPT文件信息）到 bus_patient_structured_data 表

        ⚠️ 替换策略：同一患者多次生成PPT时，会更新现有记录而不是新增

        data_type: "ppt_final"

        Args:
            db: 数据库会话
            patient_id: 患者ID
            ppt_url: PPT下载链接
            local_path: 本地路径
            qiniu_url: 七牛云URL
            file_uuid: 文件UUID
            template_id: 模板ID
            generated_at: 生成时间
            user_id: 创建用户ID（可选）
            **kwargs: 其他额外字段

        Returns:
            PatientStructuredData 记录
        """
        import uuid
        from app.utils.datetime_utils import get_beijing_now_naive

        content = {
            "ppt_url": ppt_url,
            "local_path": local_path,
            "qiniu_url": qiniu_url,
            "file_uuid": file_uuid,
            "template_id": template_id,
            "generated_at": generated_at,
            **kwargs  # 允许额外字段
        }

        # 查找是否已存在该患者的 ppt_final 记录
        existing_record = db.query(PatientStructuredData).filter(
            PatientStructuredData.patient_id == patient_id,
            PatientStructuredData.data_type == "ppt_final",
            PatientStructuredData.is_deleted == False
        ).first()

        if existing_record:
            # 更新现有记录
            existing_record.structuredcontent = content
            existing_record.updated_at = get_beijing_now_naive()
            existing_record.updated_by = user_id or "system"
            db.flush()
            logger.info(f"更新患者PPT最终成果: patient_id={patient_id}, record_id={existing_record.id}, ppt_url={ppt_url}")
            return existing_record
        else:
            # 创建新记录
            ppt_final_record = PatientStructuredData(
                id=str(uuid.uuid4()),
                patient_id=patient_id,
                data_type="ppt_final",
                data_category="ppt_generation",
                title="PPT最终成果",
                structuredcontent=content,
                version=1,
                created_by=user_id or "system",
                created_at=get_beijing_now_naive(),
                updated_at=get_beijing_now_naive(),
                is_deleted=False
            )

            db.add(ppt_final_record)
            db.flush()

            logger.info(f"创建患者PPT最终成果: patient_id={patient_id}, record_id={ppt_final_record.id}, ppt_url={ppt_url}")
            return ppt_final_record

    @staticmethod
    def save_patient_files(
        db: Session,
        patient_id: str,
        user_id: str,
        files_data: List[Dict[str, Any]]
    ) -> List[PatientFile]:
        """保存患者文件记录到 bus_patient_files 表（自动去重）"""

        file_records = []
        skipped_count = 0

        for file_data in files_data:
            file_hash = file_data.get("file_hash")
            file_name = file_data.get("file_name", "未命名文件")

            # 检查文件是否已存在（基于 file_hash 或 file_name）
            existing_file = None
            if file_hash:
                # 优先使用 file_hash 去重（更准确）
                existing_file = db.query(PatientFile).filter(
                    PatientFile.patient_id == patient_id,
                    PatientFile.file_hash == file_hash,
                    PatientFile.is_deleted == False
                ).first()

            if not existing_file and file_name != "未命名文件":
                # 如果没有 hash，使用 file_name 去重
                existing_file = db.query(PatientFile).filter(
                    PatientFile.patient_id == patient_id,
                    PatientFile.file_name == file_name,
                    PatientFile.is_deleted == False
                ).first()

            if existing_file:
                # 文件已存在，跳过
                skipped_count += 1
                logger.debug(f"文件已存在，跳过: {file_name} (hash: {file_hash})")
                file_records.append(existing_file)
                continue

            # 文件不存在，创建新记录
            file_record = PatientFile(
                # 主键和关联
                id=str(uuid.uuid4()),
                patient_id=patient_id,
                conversation_id=file_data.get("conversation_id"),

                # 基本文件信息
                file_uuid=file_data.get("file_uuid"),
                file_name=file_name,
                upload_filename=file_data.get("upload_filename"),
                file_extension=file_data.get("file_extension"),
                file_path=file_data.get("file_path", ""),
                file_url=file_data.get("file_url"),
                file_type=file_data.get("file_type"),
                file_size=file_data.get("file_size"),
                file_category=file_data.get("file_category", "medical_record"),
                file_hash=file_hash,

                # 文件来源信息
                source_type=file_data.get("source_type", "uploaded"),
                parent_pdf_uuid=file_data.get("parent_pdf_uuid"),
                parent_pdf_filename=file_data.get("parent_pdf_filename"),
                parent_zip_uuid=file_data.get("parent_zip_uuid"),
                parent_zip_filename=file_data.get("parent_zip_filename"),
                is_from_zip=file_data.get("is_from_zip", False),
                is_from_pdf=file_data.get("is_from_pdf", False),

                # PDF相关字段
                extraction_mode=file_data.get("extraction_mode"),
                extracted_image_count=file_data.get("extracted_image_count"),
                page_number=file_data.get("page_number"),
                image_index_in_page=file_data.get("image_index_in_page"),

                # 医学影像相关
                has_medical_image=file_data.get("has_medical_image", False),
                image_bbox=file_data.get("image_bbox"),
                cropped_image_uuid=file_data.get("cropped_image_uuid"),
                cropped_image_url=file_data.get("cropped_image_url"),
                cropped_image_available=file_data.get("cropped_image_available", False),

                # 文件元数据
                exam_date=file_data.get("exam_date"),
                exam_type=file_data.get("exam_type"),
                department=file_data.get("department"),
                doctor=file_data.get("doctor"),

                # 提取内容
                extracted_text=file_data.get("extracted_text"),
                extractedmetadata=file_data.get("metadata", {}),
                extraction_failed=file_data.get("extraction_failed", False),
                extraction_success=file_data.get("extraction_success"),
                extraction_error=file_data.get("extraction_error"),

                # 上传信息
                uploaded_by=user_id,
                uploaded_at=get_beijing_now_naive(),
                upload_timestamp=file_data.get("upload_timestamp"),
                created_at=get_beijing_now_naive(),
                updated_at=get_beijing_now_naive(),
                is_deleted=False
            )
            db.add(file_record)
            file_records.append(file_record)

        if file_records:
            db.flush()
            new_count = len(file_records) - skipped_count
            if skipped_count > 0:
                logger.info(f"保存患者文件记录: 新增 {new_count} 个, 跳过重复 {skipped_count} 个")
            else:
                logger.info(f"保存 {len(file_records)} 个患者文件记录")

        return file_records

    @staticmethod
    def get_patient_structured_data(
        db: Session,
        patient_id: str,
        data_type: Optional[str] = None,
        conversation_id: Optional[str] = None
    ) -> List[PatientStructuredData]:
        """获取患者的结构化数据"""

        query = db.query(PatientStructuredData).filter(
            PatientStructuredData.patient_id == patient_id,
            PatientStructuredData.is_deleted == False
        )

        if data_type:
            query = query.filter(PatientStructuredData.data_type == data_type)

        if conversation_id:
            query = query.filter(PatientStructuredData.conversation_id == conversation_id)

        return query.order_by(PatientStructuredData.updated_at.desc()).all()

    @staticmethod
    def update_structured_data_with_ppt_info(
        db: Session,
        patient_id: str,
        conversation_id: str,
        ppt_info: Dict[str, Any]
    ):
        """更新患者时间轴数据，添加PPT信息"""

        # 查找该会话的timeline数据
        timeline_data = db.query(PatientStructuredData).filter(
            PatientStructuredData.patient_id == patient_id,
            PatientStructuredData.conversation_id == conversation_id,
            PatientStructuredData.data_type == "timeline",
            PatientStructuredData.is_deleted == False
        ).first()

        if timeline_data:
            # 更新structuredcontent，添加ppt_info
            content = timeline_data.structuredcontent
            if isinstance(content, dict):
                content["ppt_info"] = ppt_info
                timeline_data.structuredcontent = content
                timeline_data.updated_at = get_beijing_now_naive()
                db.flush()
                logger.info(f"更新患者时间轴数据，添加PPT信息: {timeline_data.id}")

    @staticmethod
    def get_patient_all_data_for_ppt(
        db: Session,
        patient_id: str
    ) -> Dict[str, Any]:
        """
        获取患者的所有数据用于生成PPT

        返回:
        {
            "patient_info": {...},           # 患者基本信息
            "patient_timeline": {...},       # 聚合的时间轴数据
            "patient_journey": {...},        # 聚合的就诊历程
            "mdt_reports": [...],            # 所有MDT报告
            "raw_files_data": [...]          # 所有原始文件信息
        }
        """
        from app.models.bus_models import Patient, PatientFile

        result = {
            "patient_info": None,
            "patient_timeline": {},
            "patient_journey": {},
            "mdt_reports": [],
            "raw_files_data": []
        }

        # 1. 查询患者基本信息
        patient = db.query(Patient).filter(
            Patient.patient_id == patient_id,
            Patient.is_deleted == False
        ).first()

        if not patient:
            logger.error(f"患者不存在: {patient_id}")
            return result

        result["patient_info"] = {
            "patient_id": patient.patient_id,
            "patient_no": patient.patient_no,
            "name": patient.name,
            "gender": patient.gender,
            "birth_date": patient.birth_date.isoformat() if patient.birth_date else None,
            "phone": patient.phone,
            "blood_type": patient.blood_type,
            "allergies": patient.allergies,
            "medical_history": patient.medical_history,
        }

        # 2. 获取患者的所有文件（直接从 bus_patient_files 表查询）
        files = db.query(PatientFile).filter(
            PatientFile.patient_id == patient_id,
            PatientFile.is_deleted == False
        ).order_by(PatientFile.uploaded_at.desc()).all()

        result["raw_files_data"] = [
            {
                "file_uuid": f.file_uuid,
                "file_name": f.file_name,
                "file_url": f.file_url,
                "file_type": f.file_type,
                "file_category": f.file_category,
                "extracted_text": f.extracted_text,
                "exam_date": f.exam_date.isoformat() if f.exam_date else None,
                "exam_type": f.exam_type,
                "has_medical_image": f.has_medical_image,
                "cropped_image_url": f.cropped_image_url,
                "cropped_image_available": f.cropped_image_available,
                # 新增：来源信息
                "source_type": f.source_type,
                "is_from_pdf": f.is_from_pdf,
                "is_from_zip": f.is_from_zip,
                "parent_pdf_filename": f.parent_pdf_filename,
                "parent_zip_filename": f.parent_zip_filename,
            }
            for f in files
        ]

        # 3. 获取所有结构化数据
        structured_data_list = db.query(PatientStructuredData).filter(
            PatientStructuredData.patient_id == patient_id,
            PatientStructuredData.is_deleted == False
        ).order_by(PatientStructuredData.created_at.desc()).all()

        # 4. 聚合 timeline 数据（取最新的）
        timelines = [d for d in structured_data_list if d.data_type == "timeline"]
        if timelines:
            result["patient_timeline"] = timelines[0].structuredcontent

        # 5. 聚合 journey 数据（取最新的）
        journeys = [d for d in structured_data_list if d.data_type == "journey"]
        if journeys:
            result["patient_journey"] = journeys[0].structuredcontent

        # 6. 获取所有 MDT 报告
        mdt_reports = [d for d in structured_data_list if d.data_type == "mdt_report"]
        result["mdt_reports"] = [
            {
                "id": r.id,
                "title": r.title,
                "content": r.structuredcontent,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in mdt_reports
        ]

        logger.info(f"获取患者 {patient_id} 的PPT数据: "
                   f"文件数={len(result['raw_files_data'])}, "
                   f"timeline={'有' if result['patient_timeline'] else '无'}, "
                   f"journey={'有' if result['patient_journey'] else '无'}, "
                   f"MDT报告数={len(result['mdt_reports'])}")

        return result
