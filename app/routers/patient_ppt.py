"""
患者PPT生成路由 - 基于 patient_id 的新架构（无需认证）
"""
from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.bus_patient_helpers import BusPatientHelper
from app.models.bus_models import Patient
from src.utils.logger import BeijingLogger

logger = BeijingLogger().get_logger()

router = APIRouter()


@router.post("/patients/{patient_id}/generate_ppt")
async def generate_ppt_for_patient(
    patient_id: str,
    db: Session = Depends(get_db)
) -> Any:
    """
    为指定患者生成PPT（基于患者的所有数据）

    新架构特点：
    1. 基于 patient_id，而不是 conversation_id
    2. 自动聚合患者的所有结构化数据（timeline/journey/mdt_report）
    3. 从 bus_patient.raw_file_ids 获取所有原始文件
    4. 生成包含患者完整病历的PPT

    Args:
        patient_id: 患者ID
        db: 数据库会话
        current_user: 当前登录用户

    Returns:
        {
            "success": bool,
            "ppt_url": str,          # Suvalue API模式
            "local_path": str,       # 本地模式
            "file_uuid": str,        # 本地模式
            "qiniu_url": str,        # 本地模式七牛云URL
            "message": str
        }
    """
    from src.crews.ppt_generation_crew.ppt_generation_crew import PPTGenerationCrew

    try:
        logger.info(f"开始为患者 {patient_id} 生成PPT")

        # 1. 检查患者是否存在
        patient = db.query(Patient).filter(
            Patient.patient_id == patient_id,
            Patient.is_deleted == False
        ).first()

        if not patient:
            raise HTTPException(
                status_code=404,
                detail=f"患者不存在: {patient_id}"
            )

        # 2. 获取患者的所有数据（timeline, journey, files）
        patient_data = BusPatientHelper.get_patient_all_data_for_ppt(db, patient_id)

        if not patient_data.get("patient_timeline"):
            raise HTTPException(
                status_code=400,
                detail="患者时间轴数据为空，无法生成PPT。请先处理患者数据。"
            )

        # 3. 准备PPT生成所需数据
        patient_timeline = patient_data["patient_timeline"]
        patient_journey = patient_data.get("patient_journey", {})
        raw_files_data = patient_data.get("raw_files_data", [])
        patient_info = patient_data.get("patient_info", {})

        logger.info(f"患者 {patient_id} 数据准备完成: "
                   f"timeline={'有' if patient_timeline else '无'}, "
                   f"journey={'有' if patient_journey else '无'}, "
                   f"文件数={len(raw_files_data)}")

        # 4. 初始化PPT生成crew
        ppt_crew = PPTGenerationCrew()

        # 5. 生成PPT（使用 patient_id 作为 session_id）
        logger.info(f"开始为患者 {patient_id} 生成PPT...")
        result = ppt_crew.generate_ppt(
            patient_timeline=patient_timeline,
            patient_journey=patient_journey,
            raw_files_data=raw_files_data,
            agent_session_id=patient_id,  # 使用 patient_id 作为 session_id
            template_id="medical",
            filter_no_cropped_image=True
        )

        # 6. 检查生成结果
        if not result or not result.get("success"):
            error_msg = result.get("error", "PPT生成失败") if result else "PPT生成失败"
            logger.error(f"PPT生成失败: {error_msg}")
            raise HTTPException(
                status_code=500,
                detail=f"PPT生成失败: {error_msg}"
            )

        logger.info(f"✅ 患者 {patient_id} 的PPT生成成功")

        # 7. 分别保存 PPT 流程数据和最终成果到数据库
        try:
            import time

            # 7.1 保存 PPT 流程数据（ppt_data）
            ppt_data = result.get("ppt_data")
            treatment_gantt_data = result.get("treatment_gantt_data")

            if ppt_data:
                BusPatientHelper.save_ppt_data(
                    db=db,
                    patient_id=patient_id,
                    ppt_data=ppt_data,
                    treatment_gantt_data=treatment_gantt_data,
                    user_id="system"
                )
                logger.info(f"已保存PPT流程数据: patient_id={patient_id}")

            # 7.2 保存 PPT 最终成果（ppt_final）
            BusPatientHelper.save_ppt_final(
                db=db,
                patient_id=patient_id,
                ppt_url=result.get("ppt_url"),
                local_path=result.get("local_path"),
                qiniu_url=result.get("qiniu_url"),
                file_uuid=result.get("file_uuid"),
                template_id="medical",
                generated_at=time.strftime('%Y-%m-%d %H:%M:%S'),
                success=result.get("success"),
                message=result.get("message"),
                user_id="system"
            )
            logger.info(f"已保存PPT最终成果: patient_id={patient_id}, ppt_url={result.get('ppt_url')}")

            db.commit()

        except Exception as e:
            logger.error(f"保存PPT数据失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            # 不影响返回结果，继续执行

        # 8. 返回结果（包含患者基本信息）
        result["patient_info"] = patient_info
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"为患者 {patient_id} 生成PPT时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"生成PPT失败: {str(e)}"
        )


@router.get("/patients/{patient_id}/ppt_data")
async def get_patient_ppt_data(
    patient_id: str,
    db: Session = Depends(get_db)
) -> Any:
    """
    获取患者的PPT数据（用于预览或调试）

    Args:
        patient_id: 患者ID

    Returns:
        {
            "patient_info": {...},
            "patient_timeline": {...},
            "patient_journey": {...},
            "mdt_reports": [...],
            "raw_files_data": [...]
        }
    """
    try:
        logger.info(f"获取患者 {patient_id} 的PPT数据")

        # 检查患者是否存在
        patient = db.query(Patient).filter(
            Patient.patient_id == patient_id,
            Patient.is_deleted == False
        ).first()

        if not patient:
            raise HTTPException(
                status_code=404,
                detail=f"患者不存在: {patient_id}"
            )

        # 获取患者数据
        patient_data = BusPatientHelper.get_patient_all_data_for_ppt(db, patient_id)

        return {
            "success": True,
            "data": patient_data
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取患者 {patient_id} 的PPT数据时出错: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"获取数据失败: {str(e)}"
        )


