from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Any, Dict
import time
import uuid

from app.db.database import get_db
from app.core.deps import get_current_user
from app.models.user import User as UserModel
from app.models.bus_models import PatientConversation
from app.models.patient_detail_helpers import PatientDetailHelper
from app.utils.datetime_utils import get_beijing_now_naive
from src.utils.logger import BeijingLogger

# 初始化 logger
logger = BeijingLogger().get_logger()

router = APIRouter()


@router.post("/extract_patient_data")
def extract_patient_data(
    request: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> Any:
    """
    直接提取患者信息接口，不涉及多轮对话
    接收文件和文本输入，通过patient_data_crew处理后返回患者信息结果
    """
    from src.crews.patient_data_crew.patient_data_crew import PatientDataCrew
    from app.utils.file_processing_manager import FileProcessingManager
    from app.utils.file_metadata_builder import FileMetadataBuilder

    try:
        # ========== 整体开始时间 ==========
        overall_start_time = time.time()
        logger.info("=" * 80)
        logger.info("开始直接提取患者数据")
        logger.info("=" * 80)

        # 1. 获取用户输入
        user_text = request.get("text", "")
        files = request.get("files", [])

        if not user_text and not files:
            raise HTTPException(
                status_code=400,
                detail="至少需要提供文本内容或文件",
            )

        # 2. 生成临时会话ID用于文件处理
        temp_conversation_id = f"temp_{uuid.uuid4()}"

        # ========== 阶段1: 文件处理与提取 ==========
        file_processing_start_time = time.time()
        logger.info("-" * 80)
        logger.info("【阶段1】开始文件处理与提取")
        logger.info("-" * 80)

        # 3. 处理文件上传和提取
        formatted_files = []
        uploaded_file_ids = []
        extracted_file_results = []
        raw_files_data = []

        if files:
            logger.info(f"开始处理 {len(files)} 个文件")
            file_manager = FileProcessingManager()
            formatted_files, uploaded_file_ids, extracted_file_results = file_manager.process_files(
                files, temp_conversation_id
            )

            # 构建文件元数据
            if extracted_file_results:
                raw_files_data = FileMetadataBuilder.build_raw_files_data(extracted_file_results)
                logger.info(f"成功提取 {len(extracted_file_results)} 个文件内容")

        file_processing_duration = time.time() - file_processing_start_time
        logger.info("-" * 80)
        logger.info(f"【阶段1】文件处理与提取完成，耗时: {file_processing_duration:.2f} 秒 ({file_processing_duration/60:.2f} 分钟)")
        logger.info("-" * 80)

        # 4. 准备传递给patient_data_crew的文件信息
        files_to_pass = []
        if extracted_file_results:
            files_to_pass = FileMetadataBuilder.build_file_info_for_api(extracted_file_results)
        elif formatted_files:
            files_to_pass = formatted_files

        # ========== 阶段2: 患者数据结构化处理 ==========
        patient_data_crew_start_time = time.time()
        logger.info("-" * 80)
        logger.info("【阶段2】开始患者数据结构化处理（调用patient_data_crew）")
        logger.info("-" * 80)

        # 5. 调用patient_data_crew处理患者数据
        patient_crew = PatientDataCrew()

        # 准备输入参数
        patient_info = user_text if user_text else ""

        # 调用get_structured_patient_data方法
        result = patient_crew.get_structured_patient_data(
            patient_info=patient_info,
            patient_timeline="",  # 新数据，无历史时间轴
            messages=[],  # 单次提取，无对话历史
            files=files_to_pass,
            agent_session_id=temp_conversation_id,
            existing_patient_data=None  # 新提取，无现有数据
        )

        patient_data_crew_duration = time.time() - patient_data_crew_start_time
        logger.info("-" * 80)
        logger.info(f"【阶段2】患者数据结构化处理完成，耗时: {patient_data_crew_duration:.2f} 秒 ({patient_data_crew_duration/60:.2f} 分钟)")
        logger.info("-" * 80)

        # 6. 检查处理结果
        if "error" in result:
            raise HTTPException(
                status_code=500,
                detail=f"患者数据处理失败: {result['error']}"
            )

        # ========== 总体耗时统计 ==========
        overall_duration = time.time() - overall_start_time
        logger.info("=" * 80)
        logger.info("直接提取患者数据完成 - 耗时统计")
        logger.info("=" * 80)
        logger.info(f"【阶段1】文件处理与提取:          {file_processing_duration:.2f} 秒 ({file_processing_duration/60:.2f} 分钟) - {(file_processing_duration/overall_duration*100):.1f}%")
        logger.info(f"【阶段2】患者数据结构化处理:      {patient_data_crew_duration:.2f} 秒 ({patient_data_crew_duration/60:.2f} 分钟) - {(patient_data_crew_duration/overall_duration*100):.1f}%")
        logger.info("-" * 80)
        logger.info(f"【总计】整体处理时间:             {overall_duration:.2f} 秒 ({overall_duration/60:.2f} 分钟)")
        logger.info("=" * 80)

        # 7. 返回结果
        return {
            "status": "success",
            "user_id": str(current_user.id),
            "temp_session_id": temp_conversation_id,
            "uploaded_files_count": len(uploaded_file_ids),
            "uploaded_file_ids": uploaded_file_ids,
            "patient_timeline": result.get("full_structure_data", {}),
            "patient_journey": result.get("patient_journey", {}),
            "mdt_simple_report": result.get("mdt_simple_report", {}),
            "patient_full_content": result.get("patient_content", "")
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"提取患者数据时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"提取患者数据失败: {str(e)}"
        )
