"""
Patient Detail Model Helpers
桥接到业务表（bus_*）的Helper类
"""
import json
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from src.utils.logger import BeijingLogger

from app.models.bus_patient_helpers import BusPatientHelper
from app.models.bus_models import PatientStructuredData
from app.utils.datetime_utils import get_beijing_now_naive

logger = BeijingLogger().get_logger()


class PatientDetailHelper:
    """
    PatientDetail 模型的辅助类
    现在桥接到 bus_patient_structured_data 表
    """

    @staticmethod
    def create_patient_detail(
        db: Session,
        conversation_id: str,
        raw_text_data: Optional[str] = None,
        raw_files_data: Optional[List[Dict[str, Any]]] = None,
        raw_file_ids: Optional[List[str]] = None,
        patient_timeline: Optional[Dict[str, Any]] = None,
        patient_journey: Optional[Dict[str, Any]] = None,
        mdt_simple_report: Optional[Dict[str, Any]] = None,
        patient_full_content: Optional[str] = None,
        extraction_statistics: Optional[Dict[str, Any]] = None
    ):
        """
        创建新的患者详情记录（写入bus_*表）

        流程:
        1. 从conversation_id查询patient_id和user_id
        2. 更新patient的raw_file_ids字段
        3. 保存文件记录到bus_patient_files表
        4. 保存结构化数据到bus_patient_structured_data表
        """
        logger.info(f"开始保存患者详情数据, conversation_id: {conversation_id}")

        try:
            # 1. 查询会话记录
            from app.models.bus_models import PatientConversation, Patient
            conversation = db.query(PatientConversation).filter(
                PatientConversation.id == conversation_id
            ).first()

            if not conversation:
                raise ValueError(f"找不到会话记录: {conversation_id}")

            patient_id = conversation.patient_id
            user_id = conversation.user_id

            # 2. 更新患者的raw_file_ids
            if raw_file_ids:
                patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
                if patient:
                    patient.raw_file_ids = json.dumps(raw_file_ids)
                    patient.updated_at = get_beijing_now_naive()
                    logger.info(f"更新患者文件ID列表: {patient_id}, 文件数: {len(raw_file_ids)}")

            # 3. 保存文件记录到bus_patient_files
            if raw_files_data:
                logger.info(f"准备保存 {len(raw_files_data)} 个文件到 bus_patient_files")
                BusPatientHelper.save_patient_files(
                    db=db,
                    patient_id=patient_id,
                    user_id=user_id,
                    files_data=raw_files_data
                )
            else:
                logger.warning(f"raw_files_data 为空，跳过保存文件到 bus_patient_files")

            # 4. 保存结构化数据（timeline, journey, mdt_report）
            BusPatientHelper.save_structured_data(
                db=db,
                patient_id=patient_id,
                conversation_id=conversation_id,
                user_id=user_id,
                patient_timeline=patient_timeline,
                patient_journey=patient_journey,
                mdt_simple_report=mdt_simple_report,
                patient_full_content=patient_full_content
            )

            db.commit()
            logger.info(f"患者详情数据保存成功 - conversation_id: {conversation_id}")

        except Exception as e:
            db.rollback()
            logger.error(f"保存患者详情数据失败: {str(e)}")
            raise

    @staticmethod
    def get_patient_detail_by_conversation_id(
        db: Session,
        conversation_id: str
    ):
        """根据conversation_id获取患者详情"""
        # 查询该会话的timeline数据（作为主记录）
        structured_data = db.query(PatientStructuredData).filter(
            PatientStructuredData.conversation_id == conversation_id,
            PatientStructuredData.data_type == "timeline",
            PatientStructuredData.is_deleted == False
        ).first()

        return structured_data

    @staticmethod
    def get_patient_timeline(patient_detail: PatientStructuredData) -> Optional[Dict[str, Any]]:
        """获取患者时间轴数据"""
        if not patient_detail:
            return None

        # 查询timeline类型的数据
        if patient_detail.data_type == "timeline":
            return patient_detail.structuredcontent

        # 如果传入的不是timeline，从同一会话中查找
        from sqlalchemy.orm import Session
        db = Session.object_session(patient_detail)
        timeline = db.query(PatientStructuredData).filter(
            PatientStructuredData.conversation_id == patient_detail.conversation_id,
            PatientStructuredData.data_type == "timeline",
            PatientStructuredData.is_deleted == False
        ).first()

        return timeline.structuredcontent if timeline else None

    @staticmethod
    def get_patient_journey(patient_detail: PatientStructuredData) -> Optional[Dict[str, Any]]:
        """获取患者就诊历程数据"""
        if not patient_detail:
            return None

        from sqlalchemy.orm import Session
        db = Session.object_session(patient_detail)
        journey = db.query(PatientStructuredData).filter(
            PatientStructuredData.conversation_id == patient_detail.conversation_id,
            PatientStructuredData.data_type == "journey",
            PatientStructuredData.is_deleted == False
        ).first()

        return journey.structuredcontent if journey else None

    @staticmethod
    def get_patient_full_content(patient_detail: PatientStructuredData) -> Optional[str]:
        """获取患者完整内容"""
        if not patient_detail:
            return None
        return patient_detail.text_content

    @staticmethod
    def get_raw_files_data(patient_detail: PatientStructuredData) -> Optional[List[Dict[str, Any]]]:
        """获取原始文件数据"""
        if not patient_detail:
            return None

        try:
            # 从patient关系查询文件
            files = patient_detail.patient.files
            return [
                {
                    "file_uuid": f.id,
                    "file_name": f.file_name,
                    "file_url": f.file_url,
                    "file_type": f.file_type,
                    "extracted_text": f.extracted_text,
                }
                for f in files if not f.is_deleted
            ]
        except Exception as e:
            logger.error(f"获取文件数据失败: {str(e)}")
            return None

    @staticmethod
    def update_patient_detail(
        db: Session,
        patient_detail: PatientStructuredData,
        raw_text_data: Optional[str] = None,
        raw_files_data: Optional[List[Dict[str, Any]]] = None,
        raw_file_ids: Optional[List[str]] = None,
        patient_timeline: Optional[Dict[str, Any]] = None,
        patient_journey: Optional[Dict[str, Any]] = None,
        mdt_simple_report: Optional[Dict[str, Any]] = None,
        patient_full_content: Optional[str] = None,
        ppt_info: Optional[Dict[str, Any]] = None,
        extraction_statistics: Optional[Dict[str, Any]] = None
    ):
        """更新患者详情记录"""
        try:
            conversation_id = patient_detail.conversation_id

            # 更新timeline数据
            if patient_timeline is not None:
                timeline = db.query(PatientStructuredData).filter(
                    PatientStructuredData.conversation_id == conversation_id,
                    PatientStructuredData.data_type == "timeline",
                    PatientStructuredData.is_deleted == False
                ).first()

                if timeline:
                    timeline.structuredcontent = patient_timeline
                    if patient_full_content:
                        timeline.text_content = patient_full_content

            # 更新journey数据
            if patient_journey is not None:
                journey = db.query(PatientStructuredData).filter(
                    PatientStructuredData.conversation_id == conversation_id,
                    PatientStructuredData.data_type == "journey",
                    PatientStructuredData.is_deleted == False
                ).first()

                if journey:
                    journey.structuredcontent = patient_journey

            # 更新mdt_report数据
            if mdt_simple_report is not None:
                mdt = db.query(PatientStructuredData).filter(
                    PatientStructuredData.conversation_id == conversation_id,
                    PatientStructuredData.data_type == "mdt_report",
                    PatientStructuredData.is_deleted == False
                ).first()

                if mdt:
                    mdt.structuredcontent = mdt_simple_report

            # 更新PPT信息（添加到timeline的structuredcontent中）
            if ppt_info is not None:
                timeline = db.query(PatientStructuredData).filter(
                    PatientStructuredData.conversation_id == conversation_id,
                    PatientStructuredData.data_type == "timeline",
                    PatientStructuredData.is_deleted == False
                ).first()

                if timeline and isinstance(timeline.structuredcontent, dict):
                    timeline.structuredcontent["ppt_info"] = ppt_info

            db.commit()
            logger.info(f"患者详情数据更新成功 - conversation_id: {conversation_id}")

        except Exception as e:
            db.rollback()
            logger.error(f"更新患者详情数据失败: {str(e)}")
            raise
