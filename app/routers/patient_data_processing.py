from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Any, Dict
import json
import time
from datetime import datetime
import uuid

from app.db.database import get_db
from app.core.deps import get_current_user
from app.models.user import User as UserModel
from src.utils.logger import BeijingLogger

# 初始化 logger
logger = BeijingLogger().get_logger()

# 全局字典存储任务状态（生产环境应使用Redis或数据库）
task_status_store = {}

# 全局字典存储后台任务锁（防止重复执行）
task_locks = {}

router = APIRouter()

# 全局字典存储对话历史（生产环境应使用Redis或数据库）
conversation_messages_store = {}


# ============================================================================
# 后台任务异步处理接口（即使客户端断开也会继续执行）
# ============================================================================

def process_patient_data_background(
    task_id: str,
    patient_description: str,
    consultation_purpose: str,
    files: list,
    user_id: str
):
    """
    后台任务：处理患者数据
    即使客户端断开连接，任务也会继续执行
    """
    from src.crews.patient_data_crew.patient_data_crew import PatientDataCrew
    from app.utils.file_processing_manager import FileProcessingManager
    from app.utils.file_metadata_builder import FileMetadataBuilder
    from app.models.bus_patient_helpers import BusPatientHelper
    from app.models.bus_models import PatientConversation
    from app.db.database import SessionLocal

    # 创建新的数据库会话
    db = SessionLocal()
    conversation = None
    try:
        # 更新任务状态为处理中
        task_status_store[task_id] = {
            "status": "processing",
            "progress": 0,
            "message": "开始处理患者数据",
            "start_time": time.time(),
            "user_id": user_id
        }

        logger.info(f"[后台任务 {task_id}] 开始处理患者数据")

        overall_start_time = time.time()

        # 1. 从patient_description提取患者姓名（简化处理：使用"患者"作为默认名称）
        # TODO: 如果有更好的方式提取患者姓名，应该在这里实现
        patient_name = "患者"  # 或从patient_description中提取

        # 2. 创建患者记录
        patient = BusPatientHelper.create_or_get_patient(
            db=db,
            name=patient_name,
            user_id=user_id,
            status="active"
        )

        # 3. 创建会话记录
        session_id = f"patient_{task_id}"
        conversation = BusPatientHelper.create_conversation(
            db=db,
            patient_id=patient.patient_id,
            user_id=user_id,
            title=f"患者数据处理 - {patient_description[:50]}..." if len(patient_description) > 50 else patient_description,
            session_id=session_id,
            conversation_type="extraction"
        )
        db.commit()
        conversation_id = conversation.id

        logger.info(f"[后台任务 {task_id}] 创建患者记录: {patient.patient_id}, 会话记录: {conversation_id}")

        # ========== 文件处理 ==========
        formatted_files = []
        uploaded_file_ids = []
        extracted_file_results = []

        if files:
            task_status_store[task_id].update({
                "status": "processing",
                "progress": 10,
                "message": f"正在处理 {len(files)} 个文件"
            })

            file_manager = FileProcessingManager()
            formatted_files, uploaded_file_ids, extracted_file_results = file_manager.process_files(
                files, conversation_id
            )

            task_status_store[task_id].update({
                "progress": 25,
                "message": f"文件处理完成，共提取 {len(extracted_file_results)} 个文件"
            })

            # 注意：文件记录将在 PatientDetailHelper.create_patient_detail 中统一保存
            # 避免重复保存导致数据冗余

        # 构建文件元数据和提取统计信息
        raw_files_data = []
        extraction_statistics = None
        if extracted_file_results:
            raw_files_data = FileMetadataBuilder.build_raw_files_data(extracted_file_results)
            extraction_statistics = FileMetadataBuilder.collect_extraction_statistics(extracted_file_results)

        # 准备传递给patient_data_crew的文件信息
        files_to_pass = []
        if extracted_file_results:
            files_to_pass = FileMetadataBuilder.build_file_info_for_api(extracted_file_results)
        elif formatted_files:
            files_to_pass = formatted_files

        # 构建用户文本
        user_text = f"""患者说明：
{patient_description}

会诊目的：
{consultation_purpose}
"""

        # ========== 患者数据结构化处理 ==========
        task_status_store[task_id].update({
            "progress": 30,
            "message": "正在进行患者数据结构化处理"
        })

        patient_crew = PatientDataCrew()
        patient_info = user_text if user_text else ""

        result = None
        for progress_data in patient_crew.get_structured_patient_data_stream(
            patient_info=patient_info,
            patient_timeline="",
            messages=[],
            files=files_to_pass,
            agent_session_id=conversation_id,
            existing_patient_data=None
        ):
            if progress_data.get("type") == "progress":
                # 更新任务进度
                task_status_store[task_id].update({
                    "progress": progress_data.get("progress"),
                    "message": progress_data.get("message"),
                    "stage": progress_data.get("stage")
                })
            elif progress_data.get("type") == "result":
                result = progress_data.get("data")

        # 检查结果
        if "error" in result:
            # 软删除创建的Conversation记录
            if conversation:
                try:
                    conversation.status = "deleted"
                    db.commit()
                    logger.info(f"[后台任务 {task_id}] 处理失败，已标记会话记录为删除: {conversation_id}")
                except Exception as del_error:
                    logger.error(f"[后台任务 {task_id}] 删除会话记录失败: {str(del_error)}")
                    db.rollback()

            task_status_store[task_id] = {
                "status": "error",
                "message": f"处理失败: {result['error']}",
                "error": result['error'],
                "duration": time.time() - overall_start_time
            }
            logger.error(f"[后台任务 {task_id}] 处理失败: {result['error']}")
            return

        # 构建文件元数据和提取统计信息
        raw_files_data = []
        extraction_statistics = None
        if extracted_file_results:
            raw_files_data = FileMetadataBuilder.build_raw_files_data(extracted_file_results)
            extraction_statistics = FileMetadataBuilder.collect_extraction_statistics(extracted_file_results)

        # 保存到 PatientDetail
        from app.models.patient_detail_helpers import PatientDetailHelper
        PatientDetailHelper.create_patient_detail(
            db=db,
            conversation_id=conversation_id,
            raw_text_data=user_text,
            raw_files_data=raw_files_data,
            raw_file_ids=uploaded_file_ids,
            patient_timeline=result.get("full_structure_data"),
            patient_journey=result.get("patient_journey"),
            mdt_simple_report=result.get("mdt_simple_report"),
            patient_full_content=result.get("patient_content"),
            extraction_statistics=extraction_statistics
        )
        logger.info(f"[后台任务 {task_id}] 患者数据已保存到数据库")

        # 处理成功
        overall_duration = time.time() - overall_start_time
        task_status_store[task_id] = {
            "status": "completed",
            "progress": 100,
            "message": "患者数据处理完成",
            "duration": overall_duration,
            "result": {
                "patient_id": patient.patient_id,
                "conversation_id": conversation_id,
                "uploaded_files_count": len(uploaded_file_ids),
                "uploaded_file_ids": uploaded_file_ids,
                "patient_timeline": result.get("full_structure_data", {}),
                "patient_journey": result.get("patient_journey", {}),
                "mdt_simple_report": result.get("mdt_simple_report", {}),
                "patient_full_content": result.get("patient_content", "")
            }
        }

        logger.info(f"[后台任务 {task_id}] 处理完成，总耗时: {overall_duration:.2f} 秒")

    except Exception as e:
        # 软删除创建的Conversation记录
        if conversation:
            try:
                conversation.is_deleted = True
                db.commit()
                logger.info(f"[后台任务 {task_id}] 处理异常，已标记会话记录为删除")
            except Exception as del_error:
                logger.error(f"[后台任务 {task_id}] 删除会话记录失败: {str(del_error)}")
                db.rollback()

        logger.error(f"[后台任务 {task_id}] 处理异常: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

        task_status_store[task_id] = {
            "status": "error",
            "message": f"处理失败: {str(e)}",
            "error": str(e),
            "duration": time.time() - overall_start_time if 'overall_start_time' in locals() else 0
        }
    finally:
        # 关闭数据库会话
        db.close()


@router.post("/process_patient_data_async")
async def process_patient_data_async(
    request: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> Any:
    """
    后台异步处理患者数据接口

    与流式接口不同，此接口会立即返回任务ID，即使客户端断开连接，后端也会继续处理。
    客户端可以通过任务ID轮询任务状态。

    请求参数:
        - patient_description: 患者说明文本（必填）
        - consultation_purpose: 会诊目的（必填）
        - files: 文件列表（必填，每个文件需包含file_name、file_content(base64)）

    返回:
        {
            "task_id": "任务ID",
            "status": "pending",
            "message": "任务已创建，正在后台处理"
        }
    """
    try:
        # 获取用户输入
        patient_description = request.get("patient_description", "")
        consultation_purpose = request.get("consultation_purpose", "")
        files = request.get("files", [])

        # 验证输入
        if not patient_description or not consultation_purpose:
            raise HTTPException(
                status_code=400,
                detail="patient_description 和 consultation_purpose 是必填项",
            )

        if not files:
            raise HTTPException(
                status_code=400,
                detail="files 不能为空，必须上传至少一个文件",
            )

        # 生成任务ID
        task_id = str(uuid.uuid4())

        # 初始化任务状态
        task_status_store[task_id] = {
            "status": "pending",
            "progress": 0,
            "message": "任务已创建，等待处理",
            "create_time": time.time(),
            "user_id": str(current_user.id)
        }

        # 添加后台任务
        background_tasks.add_task(
            process_patient_data_background,
            task_id=task_id,
            patient_description=patient_description,
            consultation_purpose=consultation_purpose,
            files=files,
            user_id=str(current_user.id)
        )

        logger.info(f"用户 {current_user.id} 创建后台任务 {task_id}，包含 {len(files)} 个文件")

        return {
            "task_id": task_id,
            "status": "pending",
            "message": "任务已创建，正在后台处理"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建后台任务时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"创建后台任务失败: {str(e)}"
        )


@router.get("/task_status/{task_id}")
async def get_task_status(
    task_id: str,
) -> Any:
    """
    查询任务状态

    返回:
        {
            "status": "pending/processing/completed/error",
            "progress": 0-100,
            "message": "状态消息",
            "result": {...}  // 仅在completed状态时包含
        }
    """
    if task_id not in task_status_store:
        raise HTTPException(
            status_code=404,
            detail="任务不存在"
        )

    return task_status_store[task_id]


# ============================================================================
# 混合智能接口（既实时流式，又能后台执行）
# ============================================================================

def process_patient_data_background_from_task(task_id: str):
    """
    从任务状态恢复并在后台执行
    当客户端断开后，这个函数会被调用来继续执行任务
    """
    from src.crews.patient_data_crew.patient_data_crew import PatientDataCrew
    from app.utils.file_processing_manager import FileProcessingManager
    from app.utils.file_metadata_builder import FileMetadataBuilder
    from app.models.bus_patient_helpers import BusPatientHelper
    from app.models.bus_models import PatientConversation
    from app.db.database import SessionLocal

    # 检查任务锁，防止重复执行
    if task_id in task_locks and task_locks[task_id]:
        logger.warning(f"[后台任务 {task_id}] 已经在执行中，跳过")
        return

    # 设置锁
    task_locks[task_id] = True

    # 创建新的数据库会话
    db = SessionLocal()
    conversation = None
    try:
        task_data = task_status_store.get(task_id)
        if not task_data:
            logger.error(f"[后台任务 {task_id}] 任务数据不存在")
            return

        # 如果已经完成，不再执行
        if task_data.get("status") in ["completed", "error"]:
            logger.info(f"[后台任务 {task_id}] 任务已完成，无需继续执行")
            return

        logger.info(f"[后台任务 {task_id}] 客户端断开，后台继续执行")

        # 获取原始请求数据
        patient_description = task_data.get("patient_description")
        consultation_purpose = task_data.get("consultation_purpose")
        files = task_data.get("files")
        user_id = task_data.get("user_id")

        overall_start_time = task_data.get("start_time", time.time())

        # 获取或创建conversation_id
        conversation_id = task_data.get("conversation_id")
        if not conversation_id:
            # 如果还没有创建Conversation，现在创建
            # 1. 从patient_description提取患者姓名
            patient_name = "患者"

            # 2. 创建患者记录
            patient = BusPatientHelper.create_or_get_patient(
                db=db,
                name=patient_name,
                user_id=user_id,
                status="active"
            )

            # 3. 创建会话记录
            session_id = f"patient_{task_id}"
            conversation = BusPatientHelper.create_conversation(
                db=db,
                patient_id=patient.patient_id,
                user_id=user_id,
                title=f"患者数据处理 - {patient_description[:50]}..." if len(patient_description) > 50 else patient_description,
                session_id=session_id,
                conversation_type="extraction"
            )
            db.commit()
            conversation_id = conversation.id
            task_status_store[task_id]["conversation_id"] = conversation_id
            logger.info(f"[后台任务 {task_id}] 创建患者记录: {patient.patient_id}, 会话记录: {conversation_id}")
        else:
            # 如果已经有conversation_id，加载它
            conversation = db.query(PatientConversation).filter(
                PatientConversation.id == conversation_id
            ).first()
            # 获取patient对象
            from app.models.bus_models import Patient
            patient = db.query(Patient).filter_by(patient_id=conversation.patient_id).first()
            logger.info(f"[后台任务 {task_id}] 使用现有会话记录: {conversation_id}")

        # ========== 文件处理 ==========
        formatted_files = []
        uploaded_file_ids = []
        extracted_file_results = []

        if files:
            task_status_store[task_id].update({
                "status": "processing",
                "progress": 10,
                "message": f"正在处理 {len(files)} 个文件"
            })

            file_manager = FileProcessingManager()
            formatted_files, uploaded_file_ids, extracted_file_results = file_manager.process_files(
                files, conversation_id
            )

            task_status_store[task_id].update({
                "progress": 25,
                "message": f"文件处理完成，共提取 {len(extracted_file_results)} 个文件"
            })

            # 注意：文件记录将在 PatientDetailHelper.create_patient_detail 中统一保存
            # 避免重复保存导致数据冗余

        # 构建文件元数据和提取统计信息
        raw_files_data = []
        extraction_statistics = None
        if extracted_file_results:
            raw_files_data = FileMetadataBuilder.build_raw_files_data(extracted_file_results)
            extraction_statistics = FileMetadataBuilder.collect_extraction_statistics(extracted_file_results)

        # 准备传递给patient_data_crew的文件信息
        files_to_pass = []
        if extracted_file_results:
            files_to_pass = FileMetadataBuilder.build_file_info_for_api(extracted_file_results)
        elif formatted_files:
            files_to_pass = formatted_files

        # 构建用户文本
        user_text = f"""患者说明：
{patient_description}

会诊目的：
{consultation_purpose}
"""

        # ========== 患者数据结构化处理 ==========
        task_status_store[task_id].update({
            "progress": 30,
            "message": "正在进行患者数据结构化处理"
        })

        patient_crew = PatientDataCrew()
        patient_info = user_text if user_text else ""

        result = None
        for progress_data in patient_crew.get_structured_patient_data_stream(
            patient_info=patient_info,
            patient_timeline="",
            messages=[],
            files=files_to_pass,
            agent_session_id=conversation_id,
            existing_patient_data=None
        ):
            if progress_data.get("type") == "progress":
                # 更新任务进度
                task_status_store[task_id].update({
                    "progress": progress_data.get("progress"),
                    "message": progress_data.get("message"),
                    "stage": progress_data.get("stage")
                })
            elif progress_data.get("type") == "result":
                result = progress_data.get("data")

        # 检查结果
        if result and "error" in result:
            # 删除创建的Conversation记录
            if conversation:
                try:
                    db.delete(conversation)
                    db.commit()
                    logger.info(f"[后台任务 {task_id}] 处理失败，已删除会话记录: {conversation_id}")
                except Exception as del_error:
                    logger.error(f"[后台任务 {task_id}] 删除会话记录失败: {str(del_error)}")
                    db.rollback()

            task_status_store[task_id] = {
                "status": "error",
                "message": f"处理失败: {result['error']}",
                "error": result['error'],
                "duration": time.time() - overall_start_time
            }
            logger.error(f"[后台任务 {task_id}] 处理失败: {result['error']}")
            return

        # 保存到 PatientDetail
        from app.models.patient_detail_helpers import PatientDetailHelper
        PatientDetailHelper.create_patient_detail(
            db=db,
            conversation_id=conversation_id,
            raw_text_data=user_text,
            raw_files_data=raw_files_data,
            raw_file_ids=uploaded_file_ids,
            patient_timeline=result.get("full_structure_data"),
            patient_journey=result.get("patient_journey"),
            mdt_simple_report=result.get("mdt_simple_report"),
            patient_full_content=result.get("patient_content"),
            extraction_statistics=extraction_statistics
        )
        logger.info(f"[后台任务 {task_id}] 患者数据已保存到数据库")

        # 处理成功
        overall_duration = time.time() - overall_start_time
        task_status_store[task_id] = {
            "status": "completed",
            "progress": 100,
            "message": "患者数据处理完成",
            "duration": overall_duration,
            "result": {
                "patient_id": patient.patient_id,
                "conversation_id": conversation_id,
                "uploaded_files_count": len(uploaded_file_ids),
                "uploaded_file_ids": uploaded_file_ids,
                "patient_timeline": result.get("full_structure_data", {}),
                "patient_journey": result.get("patient_journey", {}),
                "mdt_simple_report": result.get("mdt_simple_report", {}),
                "patient_full_content": result.get("patient_content", "")
            }
        }

        logger.info(f"[后台任务 {task_id}] 处理完成，总耗时: {overall_duration:.2f} 秒")

    except Exception as e:
        # 软删除创建的Conversation记录
        if conversation:
            try:
                conversation.is_deleted = True
                db.commit()
                logger.info(f"[后台任务 {task_id}] 处理异常，已标记会话记录为删除")
            except Exception as del_error:
                logger.error(f"[后台任务 {task_id}] 删除会话记录失败: {str(del_error)}")
                db.rollback()

        logger.error(f"[后台任务 {task_id}] 处理异常: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

        task_status_store[task_id] = {
            "status": "error",
            "message": f"处理失败: {str(e)}",
            "error": str(e),
            "duration": time.time() - task_data.get("start_time", time.time())
        }
    finally:
        # 关闭数据库会话
        db.close()
        # 释放锁
        task_locks[task_id] = False


async def smart_stream_patient_data_processing(
    task_id: str,
    patient_description: str,
    consultation_purpose: str,
    files: list,
    user_id: str,
    background_tasks: BackgroundTasks,
    db: Session
):
    """
    混合智能处理：既流式返回，又能在断开后继续执行
    """
    from src.crews.patient_data_crew.patient_data_crew import PatientDataCrew
    from app.utils.file_processing_manager import FileProcessingManager
    from app.utils.file_metadata_builder import FileMetadataBuilder
    from app.models.bus_patient_helpers import BusPatientHelper
    from app.models.bus_models import PatientConversation
    import asyncio

    conversation = None
    try:
        # 第一条消息：返回task_id（非常重要！客户端要保存这个ID）
        yield f"data: {json.dumps({'task_id': task_id, 'status': 'started', 'message': '开始处理患者数据', 'progress': 0}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0)

        logger.info(f"[混合任务 {task_id}] 开始流式处理")

        overall_start_time = time.time()

        # 1. 从patient_description提取患者姓名（简化处理：使用"患者"作为默认名称）
        # TODO: 如果有更好的方式提取患者姓名，应该在这里实现
        patient_name = "患者"  # 或从patient_description中提取

        # 2. 创建患者记录
        patient = BusPatientHelper.create_or_get_patient(
            db=db,
            name=patient_name,
            user_id=user_id,
            status="active"
        )

        # 3. 创建会话记录
        session_id = f"patient_{task_id}"
        conversation = BusPatientHelper.create_conversation(
            db=db,
            patient_id=patient.patient_id,
            user_id=user_id,
            title=f"患者数据处理 - {patient_description[:50]}..." if len(patient_description) > 50 else patient_description,
            session_id=session_id,
            conversation_type="extraction"
        )
        db.commit()
        conversation_id = conversation.id

        logger.info(f"[混合任务 {task_id}] 创建患者记录: {patient.patient_id}, 会话记录: {conversation_id}")

        # 保存到任务状态中（断开后需要用到）
        task_status_store[task_id].update({
            "conversation_id": conversation_id
        })

        # ========== 文件处理 ==========
        formatted_files = []
        uploaded_file_ids = []
        extracted_file_results = []

        if files:
            logger.info(f"[混合任务 {task_id}] 开始处理 {len(files)} 个文件")

            progress_msg = {'status': 'processing', 'stage': 'file_processing', 'message': f'正在处理 {len(files)} 个文件', 'progress': 10}
            yield f"data: {json.dumps(progress_msg, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
            task_status_store[task_id].update(progress_msg)

            file_processing_start_time = time.time()

            file_manager = FileProcessingManager()
            formatted_files, uploaded_file_ids, extracted_file_results = file_manager.process_files(
                files, conversation_id
            )

            file_processing_duration = time.time() - file_processing_start_time

            progress_msg = {'status': 'processing', 'stage': 'file_processing_completed', 'message': f'文件处理完成，共提取 {len(extracted_file_results)} 个文件', 'progress': 25}
            yield f"data: {json.dumps(progress_msg, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
            task_status_store[task_id].update(progress_msg)

            # 注意：文件记录将在 PatientDetailHelper.create_patient_detail 中统一保存
            # 避免重复保存导致数据冗余

        # 构建文件元数据和提取统计信息
        raw_files_data = []
        extraction_statistics = None
        if extracted_file_results:
            raw_files_data = FileMetadataBuilder.build_raw_files_data(extracted_file_results)
            extraction_statistics = FileMetadataBuilder.collect_extraction_statistics(extracted_file_results)

        # 准备传递给patient_data_crew的文件信息
        files_to_pass = []
        if extracted_file_results:
            files_to_pass = FileMetadataBuilder.build_file_info_for_api(extracted_file_results)
        elif formatted_files:
            files_to_pass = formatted_files

        # 构建用户文本
        user_text = f"""患者说明：
{patient_description}

会诊目的：
{consultation_purpose}
"""

        # ========== 患者数据结构化处理 ==========
        progress_msg = {'status': 'processing', 'stage': 'patient_data_structuring', 'message': '正在进行患者数据结构化处理', 'progress': 30}
        yield f"data: {json.dumps(progress_msg)}\n\n"
        await asyncio.sleep(0)
        task_status_store[task_id].update(progress_msg)

        patient_crew = PatientDataCrew()
        patient_info = user_text if user_text else ""

        result = None
        for progress_data in patient_crew.get_structured_patient_data_stream(
            patient_info=patient_info,
            patient_timeline="",
            messages=[],
            files=files_to_pass,
            agent_session_id=conversation_id,
            existing_patient_data=None
        ):
            if progress_data.get("type") == "progress":
                # 同时做两件事：
                # 1. 流式返回给客户端
                progress_msg = {
                    'status': 'processing',
                    'stage': progress_data.get('stage'),
                    'message': progress_data.get('message'),
                    'progress': progress_data.get('progress')
                }
                yield f"data: {json.dumps(progress_msg, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)

                # 2. 更新任务状态存储
                task_status_store[task_id].update(progress_msg)

            elif progress_data.get("type") == "result":
                result = progress_data.get("data")

        # 检查处理结果
        if "error" in result:
            # 删除创建的Conversation记录
            if conversation:
                try:
                    db.delete(conversation)
                    db.commit()
                    logger.info(f"[混合任务 {task_id}] 处理失败，已删除会话记录: {conversation_id}")
                except Exception as del_error:
                    logger.error(f"[混合任务 {task_id}] 删除会话记录失败: {str(del_error)}")
                    db.rollback()

            error_msg = f"患者数据处理失败: {result['error']}"
            logger.error(f"[混合任务 {task_id}] {error_msg}")

            error_response = {'status': 'error', 'message': error_msg, 'error': result['error']}
            yield f"data: {json.dumps(error_response, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
            task_status_store[task_id].update(error_response)
            return

        # 保存到 PatientDetail
        from app.models.patient_detail_helpers import PatientDetailHelper
        PatientDetailHelper.create_patient_detail(
            db=db,
            conversation_id=conversation_id,
            raw_text_data=user_text,
            raw_files_data=raw_files_data,
            raw_file_ids=uploaded_file_ids,
            patient_timeline=result.get("full_structure_data"),
            patient_journey=result.get("patient_journey"),
            mdt_simple_report=result.get("mdt_simple_report"),
            patient_full_content=result.get("patient_content"),
            extraction_statistics=extraction_statistics
        )
        logger.info(f"[混合任务 {task_id}] 患者数据已保存到数据库")

        # 处理成功
        overall_duration = time.time() - overall_start_time

        final_result = {
            "status": "completed",
            "message": "患者数据处理完成",
            "progress": 100,
            "duration": overall_duration,
            "result": {
                "patient_id": patient.patient_id,
                "conversation_id": conversation_id,
                "uploaded_files_count": len(uploaded_file_ids),
                "uploaded_file_ids": uploaded_file_ids,
                "patient_timeline": result.get("full_structure_data", {}),
                "patient_journey": result.get("patient_journey", {}),
                "mdt_simple_report": result.get("mdt_simple_report", {}),
                "patient_full_content": result.get("patient_content", "")
            }
        }

        yield f"data: {json.dumps(final_result, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0)
        task_status_store[task_id].update(final_result)

        logger.info(f"[混合任务 {task_id}] 流式处理完成")

    except asyncio.CancelledError:
        # 客户端断开了！
        logger.warning(f"[混合任务 {task_id}] 检测到客户端断开，启动后台任务继续执行")

        # 在后台继续执行
        background_tasks.add_task(process_patient_data_background_from_task, task_id)

        # 重新抛出异常，让FastAPI知道连接已断开
        raise

    except Exception as e:
        # 删除创建的Conversation记录
        if conversation:
            try:
                db.delete(conversation)
                db.commit()
                logger.info(f"[混合任务 {task_id}] 处理异常，已删除会话记录")
            except Exception as del_error:
                logger.error(f"[混合任务 {task_id}] 删除会话记录失败: {str(del_error)}")
                db.rollback()

        logger.error(f"[混合任务 {task_id}] 处理异常: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

        error_response = {
            "status": "error",
            "message": f"处理失败: {str(e)}",
            "error": str(e)
        }
        yield f"data: {json.dumps(error_response, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0)
        task_status_store[task_id].update(error_response)


@router.post("/process_patient_data_smart")
async def process_patient_data_smart(
    request: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> Any:
    """
    混合智能接口：既能实时流式返回，又能在客户端断开后继续执行

    这个接口结合了流式接口和异步接口的优点：
    - 客户端在线时：实时返回处理进度（类似流式接口）
    - 客户端断开时：自动转为后台执行（类似异步接口）
    - 客户端重连时：可以通过task_id查询状态

    请求参数:
        - patient_description: 患者说明文本（必填）
        - consultation_purpose: 会诊目的（必填）
        - files: 文件列表（必填，每个文件需包含file_name、file_content(base64)）

    返回:
        流式响应（Server-Sent Events格式），第一条消息包含task_id

    客户端使用示例:
        1. 发起请求并接收流式响应
        2. 从第一条消息中提取task_id并保存
        3. 如果断开连接，可以通过 GET /task_status/{task_id} 查询状态
    """
    try:
        # 获取用户输入
        patient_description = request.get("patient_description", "")
        consultation_purpose = request.get("consultation_purpose", "")
        files = request.get("files", [])

        # 验证输入
        if not patient_description or not consultation_purpose:
            raise HTTPException(
                status_code=400,
                detail="patient_description 和 consultation_purpose 是必填项",
            )

        if not files:
            raise HTTPException(
                status_code=400,
                detail="files 不能为空，必须上传至少一个文件",
            )

        # 生成任务ID
        task_id = str(uuid.uuid4())

        # 使用固定用户ID（暂无认证）
        user_id = "system_user"

        # 初始化任务状态
        task_status_store[task_id] = {
            "status": "pending",
            "progress": 0,
            "message": "任务已创建",
            "start_time": time.time(),
            "user_id": user_id,
            "patient_description": patient_description,
            "consultation_purpose": consultation_purpose,
            "files": files
        }

        # 初始化任务锁
        task_locks[task_id] = False

        logger.info(f"用户 {user_id} 创建混合任务 {task_id}，包含 {len(files)} 个文件")

        # 返回流式响应
        response = StreamingResponse(
            smart_stream_patient_data_processing(
                task_id=task_id,
                patient_description=patient_description,
                consultation_purpose=consultation_purpose,
                files=files,
                user_id=user_id,
                background_tasks=background_tasks,
                db=db
            ),
            media_type="text/event-stream"
        )

        # 关键：禁用缓冲，确保实时流式传输
        response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Accel-Buffering"] = "no"

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建混合任务时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"创建混合任务失败: {str(e)}"
        )


# ============================================================================
# 对话式患者数据追问/调整接口（针对已生成的患者数据）
# ============================================================================

def process_patient_followup_background_from_task(task_id: str):
    """
    从任务状态恢复并在后台执行对话式追问
    当客户端断开后，这个函数会被调用来继续执行任务
    """
    from src.crews.patient_data_crew.patient_data_crew import PatientDataCrew
    from app.models.bus_models import PatientConversation, ConversationMessage
    from app.db.database import SessionLocal

    # 检查任务锁，防止重复执行
    if task_id in task_locks and task_locks[task_id]:
        logger.warning(f"[对话任务 {task_id}] 已经在执行中，跳过")
        return

    # 设置锁
    task_locks[task_id] = True

    # 创建新的数据库会话
    db = SessionLocal()
    try:
        task_data = task_status_store.get(task_id)
        if not task_data:
            logger.error(f"[对话任务 {task_id}] 任务数据不存在")
            return

        # 如果已经完成，不再执行
        if task_data.get("status") in ["completed", "error"]:
            logger.info(f"[对话任务 {task_id}] 任务已完成，无需继续执行")
            return

        logger.info(f"[对话任务 {task_id}] 客户端断开，后台继续执行")

        # 获取原始请求数据
        conversation_id = task_data.get("conversation_id")
        user_message = task_data.get("user_message")
        user_id = task_data.get("user_id")

        overall_start_time = task_data.get("start_time", time.time())

        # 验证conversation是否存在
        conversation = db.query(PatientConversation).filter(
            PatientConversation.id == conversation_id
        ).first()

        if not conversation:
            task_status_store[task_id] = {
                "status": "error",
                "message": f"会话不存在: {conversation_id}",
                "error": "conversation_not_found",
                "duration": time.time() - overall_start_time
            }
            logger.error(f"[对话任务 {task_id}] 会话不存在: {conversation_id}")
            return

        # 获取现有患者数据
        from app.models.patient_detail_helpers import PatientDetailHelper
        patient_detail = PatientDetailHelper.get_patient_detail_by_conversation_id(
            db, conversation_id
        )

        if not patient_detail:
            task_status_store[task_id] = {
                "status": "error",
                "message": "该会话没有患者数据，请先进行初始数据处理",
                "error": "no_patient_data",
                "duration": time.time() - overall_start_time
            }
            logger.error(f"[对话任务 {task_id}] 该会话没有患者数据")
            return

        # 获取患者时间轴和完整内容
        patient_timeline = PatientDetailHelper.get_patient_timeline(patient_detail) or {}
        patient_full_content = PatientDetailHelper.get_patient_full_content(patient_detail) or ""

        # 获取会话历史
        messages_history = conversation_messages_store.get(conversation_id, [])

        task_status_store[task_id].update({
            "progress": 30,
            "message": "正在处理您的追问"
        })

        # 调用patient_data_crew处理追问
        patient_crew = PatientDataCrew()

        result = None
        for progress_data in patient_crew.get_structured_patient_data_stream(
            patient_info=user_message,
            patient_timeline=json.dumps(patient_timeline, ensure_ascii=False),
            messages=messages_history,
            files=[],
            agent_session_id=conversation_id,
            existing_patient_data=patient_full_content
        ):
            if progress_data.get("type") == "progress":
                task_status_store[task_id].update({
                    "progress": progress_data.get("progress"),
                    "message": progress_data.get("message"),
                    "stage": progress_data.get("stage")
                })
            elif progress_data.get("type") == "result":
                result = progress_data.get("data")

        # 检查结果
        if result and "error" in result:
            task_status_store[task_id] = {
                "status": "error",
                "message": f"处理失败: {result['error']}",
                "error": result['error'],
                "duration": time.time() - overall_start_time
            }
            logger.error(f"[对话任务 {task_id}] 处理失败: {result['error']}")
            return

        # 更新患者数据
        PatientDetailHelper.update_patient_detail(
            db=db,
            patient_detail=patient_detail,
            patient_timeline=result.get("full_structure_data"),
            patient_journey=result.get("patient_journey"),
            mdt_simple_report=result.get("mdt_simple_report"),
            patient_full_content=result.get("patient_content")
        )

        logger.info(f"[对话任务 {task_id}] 患者数据已更新到数据库")

        # 处理成功
        overall_duration = time.time() - overall_start_time
        task_status_store[task_id] = {
            "status": "completed",
            "progress": 100,
            "message": "追问处理完成",
            "duration": overall_duration,
            "result": {
                "conversation_id": conversation_id,
                "patient_timeline": result.get("full_structure_data", {}),
                "patient_journey": result.get("patient_journey", {}),
                "mdt_simple_report": result.get("mdt_simple_report", {}),
                "patient_full_content": result.get("patient_content", "")
            }
        }

        logger.info(f"[对话任务 {task_id}] 处理完成，总耗时: {overall_duration:.2f} 秒")

    except Exception as e:
        logger.error(f"[对话任务 {task_id}] 处理异常: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

        task_status_store[task_id] = {
            "status": "error",
            "message": f"处理失败: {str(e)}",
            "error": str(e),
            "duration": time.time() - task_data.get("start_time", time.time())
        }
    finally:
        # 关闭数据库会话
        db.close()
        # 释放锁
        task_locks[task_id] = False


async def smart_stream_patient_followup(
    task_id: str,
    conversation_id: str,
    user_message: str,
    files: list,
    user_id: str,
    background_tasks: BackgroundTasks,
    db: Session
):
    """
    混合智能对话处理：既流式返回，又能在断开后继续执行
    针对已有患者数据的追问和调整
    """
    from src.crews.patient_data_crew.patient_data_crew import PatientDataCrew
    from app.utils.file_processing_manager import FileProcessingManager
    from app.utils.file_metadata_builder import FileMetadataBuilder
    from app.models.bus_models import PatientConversation, ConversationMessage
    import asyncio

    try:
        # 第一条消息：返回task_id
        yield f"data: {json.dumps({'task_id': task_id, 'status': 'started', 'message': '开始处理您的追问', 'progress': 0}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0)

        logger.info(f"[对话任务 {task_id}] 开始流式处理")

        overall_start_time = time.time()

        # 验证conversation是否存在
        conversation = db.query(PatientConversation).filter(
            PatientConversation.id == conversation_id,
            PatientConversation.user_id == user_id
        ).first()

        if not conversation:
            error_msg = f"会话不存在: {conversation_id}"
            logger.error(f"[对话任务 {task_id}] {error_msg}")
            error_response = {'status': 'error', 'message': error_msg, 'error': 'conversation_not_found'}
            yield f"data: {json.dumps(error_response, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
            task_status_store[task_id].update(error_response)
            return

        # 获取现有患者数据
        from app.models.patient_detail_helpers import PatientDetailHelper
        patient_detail = PatientDetailHelper.get_patient_detail_by_conversation_id(
            db, conversation_id
        )

        if not patient_detail:
            error_msg = "该会话没有患者数据，请先进行初始数据处理"
            logger.error(f"[对话任务 {task_id}] {error_msg}")
            error_response = {'status': 'error', 'message': error_msg, 'error': 'no_patient_data'}
            yield f"data: {json.dumps(error_response, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
            task_status_store[task_id].update(error_response)
            return

        # 保存用户消息到对话历史
        if conversation_id not in conversation_messages_store:
            conversation_messages_store[conversation_id] = []

        conversation_messages_store[conversation_id].append({
            "role": "user",
            "content": user_message
        })

        # 保存用户消息到数据库
        last_message = db.query(ConversationMessage).filter(
            ConversationMessage.conversation_id == conversation_id
        ).order_by(ConversationMessage.sequence_number.desc()).first()

        next_sequence = 1
        if last_message and last_message.sequence_number is not None:
            next_sequence = last_message.sequence_number + 1

        current_time = datetime.now()
        user_msg_id = f"user_{task_id}"
        user_msg = ConversationMessage(
            message_id=user_msg_id,
            conversation_id=conversation_id,
            role="user",
            content=user_message,
            type="user_followup",
            sequence_number=next_sequence,
            created_at=current_time,
            updated_at=current_time
        )
        db.add(user_msg)
        db.commit()

        # ========== 文件处理 ==========
        formatted_files = []
        uploaded_file_ids = []
        extracted_file_results = []

        if files:
            logger.info(f"[对话任务 {task_id}] 开始处理 {len(files)} 个文件")

            progress_msg = {'status': 'processing', 'stage': 'file_processing', 'message': f'正在处理 {len(files)} 个文件', 'progress': 10}
            yield f"data: {json.dumps(progress_msg, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
            task_status_store[task_id].update(progress_msg)

            file_manager = FileProcessingManager()
            formatted_files, uploaded_file_ids, extracted_file_results = file_manager.process_files(
                files, conversation_id
            )

            progress_msg = {'status': 'processing', 'stage': 'file_processing_completed', 'message': f'文件处理完成，共提取 {len(extracted_file_results)} 个文件', 'progress': 25}
            yield f"data: {json.dumps(progress_msg, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
            task_status_store[task_id].update(progress_msg)

        # 准备传递给patient_data_crew的文件信息
        files_to_pass = []
        if extracted_file_results:
            files_to_pass = FileMetadataBuilder.build_file_info_for_api(extracted_file_results)
        elif formatted_files:
            files_to_pass = formatted_files

        # 获取患者时间轴和完整内容
        patient_timeline = PatientDetailHelper.get_patient_timeline(patient_detail) or {}
        patient_full_content = PatientDetailHelper.get_patient_full_content(patient_detail) or ""

        # 获取会话历史
        messages_history = conversation_messages_store.get(conversation_id, [])

        # ========== 患者数据追问处理 ==========
        progress_msg = {'status': 'processing', 'stage': 'patient_followup', 'message': '正在处理您的追问', 'progress': 30}
        yield f"data: {json.dumps(progress_msg)}\n\n"
        await asyncio.sleep(0)
        task_status_store[task_id].update(progress_msg)

        patient_crew = PatientDataCrew()

        result = None
        for progress_data in patient_crew.get_structured_patient_data_stream(
            patient_info=user_message,
            patient_timeline=json.dumps(patient_timeline, ensure_ascii=False),
            messages=messages_history,
            files=files_to_pass,
            agent_session_id=conversation_id,
            existing_patient_data=patient_full_content
        ):
            if progress_data.get("type") == "progress":
                # 流式返回进度
                progress_msg = {
                    'status': 'processing',
                    'stage': progress_data.get('stage'),
                    'message': progress_data.get('message'),
                    'progress': progress_data.get('progress')
                }
                yield f"data: {json.dumps(progress_msg, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)

                # 更新任务状态存储
                task_status_store[task_id].update(progress_msg)

            elif progress_data.get("type") == "result":
                result = progress_data.get("data")

        # 检查处理结果
        if "error" in result:
            error_msg = f"患者数据处理失败: {result['error']}"
            logger.error(f"[对话任务 {task_id}] {error_msg}")

            error_response = {'status': 'error', 'message': error_msg, 'error': result['error']}
            yield f"data: {json.dumps(error_response, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0)
            task_status_store[task_id].update(error_response)
            return

        # 更新患者数据到数据库
        raw_files_data = []
        extraction_statistics = None
        if extracted_file_results:
            raw_files_data = FileMetadataBuilder.build_raw_files_data(extracted_file_results)
            extraction_statistics = FileMetadataBuilder.collect_extraction_statistics(extracted_file_results)

            # 合并原有文件数据
            existing_raw_files = PatientDetailHelper.get_raw_files_data(patient_detail) or []
            raw_files_data = existing_raw_files + raw_files_data

        PatientDetailHelper.update_patient_detail(
            db=db,
            patient_detail=patient_detail,
            raw_files_data=raw_files_data if extracted_file_results else None,
            patient_timeline=result.get("full_structure_data"),
            patient_journey=result.get("patient_journey"),
            mdt_simple_report=result.get("mdt_simple_report"),
            patient_full_content=result.get("patient_content"),
            extraction_statistics=extraction_statistics
        )

        logger.info(f"[对话任务 {task_id}] 患者数据已更新到数据库")

        # 保存助手回复到对话历史
        assistant_response = result.get("patient_content", "")
        conversation_messages_store[conversation_id].append({
            "role": "assistant",
            "content": assistant_response
        })

        # 保存助手回复到数据库
        assistant_msg = MessageModel(
            message_id=f"assistant_{task_id}",
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_response,
            type="assistant_followup",
            parent_id=user_msg_id,
            sequence_number=next_sequence + 1,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        db.add(assistant_msg)
        db.commit()

        # 处理成功
        overall_duration = time.time() - overall_start_time

        final_result = {
            "status": "completed",
            "message": "追问处理完成",
            "progress": 100,
            "duration": overall_duration,
            "result": {
                "patient_id": patient.patient_id,
                "conversation_id": conversation_id,
                "uploaded_files_count": len(uploaded_file_ids),
                "uploaded_file_ids": uploaded_file_ids,
                "patient_timeline": result.get("full_structure_data", {}),
                "patient_journey": result.get("patient_journey", {}),
                "mdt_simple_report": result.get("mdt_simple_report", {}),
                "patient_full_content": result.get("patient_content", ""),
                "assistant_response": assistant_response
            }
        }

        yield f"data: {json.dumps(final_result, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0)
        task_status_store[task_id].update(final_result)

        logger.info(f"[对话任务 {task_id}] 流式处理完成")

    except asyncio.CancelledError:
        # 客户端断开了！
        logger.warning(f"[对话任务 {task_id}] 检测到客户端断开，启动后台任务继续执行")

        # 在后台继续执行
        background_tasks.add_task(process_patient_followup_background_from_task, task_id)

        # 重新抛出异常，让FastAPI知道连接已断开
        raise

    except Exception as e:
        logger.error(f"[对话任务 {task_id}] 处理异常: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

        error_response = {
            "status": "error",
            "message": f"处理失败: {str(e)}",
            "error": str(e)
        }
        yield f"data: {json.dumps(error_response, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0)
        task_status_store[task_id].update(error_response)


@router.post("/chat_patient_data")
async def chat_patient_data(
    request: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> Any:
    """
    对话式患者数据追问/调整接口

    针对已生成的患者数据进行多轮对话式追问、补充和调整
    支持混合智能模式：客户端在线时流式返回，断开后继续执行

    请求参数:
        - conversation_id: 会话ID（必填，必须是已有患者数据的会话）
        - message: 用户追问的内容（必填）
        - files: 补充文件列表（可选）

    返回:
        流式响应（Server-Sent Events格式），第一条消息包含task_id

    使用场景:
        1. 追问患者某个时间段的详细信息
        2. 补充新的检查报告或病历资料
        3. 修正或调整已提取的患者数据
        4. 询问关于患者数据的问题
    """
    try:
        # 获取用户输入
        conversation_id = request.get("conversation_id", "")
        user_message = request.get("message", "")
        files = request.get("files", [])

        # 验证输入
        if not conversation_id:
            raise HTTPException(
                status_code=400,
                detail="conversation_id 是必填项",
            )

        if not user_message:
            raise HTTPException(
                status_code=400,
                detail="message 是必填项",
            )

        # 验证会话是否存在且属于当前用户
        from app.models.conversation import Conversation as ConversationModel
        conversation = db.query(ConversationModel).filter(
            ConversationModel.id == conversation_id,
            ConversationModel.user_id == current_user.id
        ).first()

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail="会话不存在或无权访问",
            )

        # 验证是否有患者数据
        from app.models.patient_detail_helpers import PatientDetailHelper
        patient_detail = PatientDetailHelper.get_patient_detail_by_conversation_id(
            db, conversation_id
        )

        if not patient_detail:
            raise HTTPException(
                status_code=400,
                detail="该会话还没有患者数据，请先使用 /process_patient_data_smart 接口生成初始数据",
            )

        # 生成任务ID
        task_id = str(uuid.uuid4())

        # 初始化任务状态
        task_status_store[task_id] = {
            "status": "pending",
            "progress": 0,
            "message": "任务已创建",
            "start_time": time.time(),
            "user_id": str(current_user.id),
            "conversation_id": conversation_id,
            "user_message": user_message,
            "files": files
        }

        # 初始化任务锁
        task_locks[task_id] = False

        logger.info(f"用户 {current_user.id} 创建对话任务 {task_id}，会话: {conversation_id}")

        # 返回流式响应
        response = StreamingResponse(
            smart_stream_patient_followup(
                task_id=task_id,
                conversation_id=conversation_id,
                user_message=user_message,
                files=files,
                user_id=str(current_user.id),
                background_tasks=background_tasks,
                db=db
            ),
            media_type="text/event-stream"
        )

        # 关键：禁用缓冲，确保实时流式传输
        response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Accel-Buffering"] = "no"

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建对话任务时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"创建对话任务失败: {str(e)}"
        )


@router.get("/conversation_history/{conversation_id}")
async def get_conversation_history(
    conversation_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Any:
    """
    获取对话历史（从内存存储中获取）

    用于查看当前会话的对话历史记录
    """
    if conversation_id not in conversation_messages_store:
        return {
            "conversation_id": conversation_id,
            "messages": [],
            "message": "该会话暂无对话历史"
        }

    messages = conversation_messages_store[conversation_id]

    return {
        "conversation_id": conversation_id,
        "messages": messages,
        "total_count": len(messages)
    }


@router.delete("/conversation_history/{conversation_id}")
async def clear_conversation_history(
    conversation_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Any:
    """
    清除对话历史（从内存存储中删除）

    用于重置会话的对话历史
    """
    if conversation_id in conversation_messages_store:
        del conversation_messages_store[conversation_id]
        logger.info(f"已清除会话 {conversation_id} 的对话历史")
        return {
            "status": "success",
            "message": "对话历史已清除"
        }

    return {
        "status": "not_found",
        "message": "该会话没有对话历史"
    }

