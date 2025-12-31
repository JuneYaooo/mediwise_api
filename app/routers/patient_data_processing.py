from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Any, Dict, Optional
import json
import time
from datetime import datetime
import uuid
import os
import asyncio

from app.db.database import get_db
from app.core.deps import get_current_user
from app.models.user import User as UserModel
from app.core.security import decode_external_token
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
    从任务状态恢复并在后台执行（首次创建患者）
    当客户端断开后，这个函数会被调用来继续执行任务
    仅支持创建新患者，不支持更新现有患者
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
        patient_id = task_data.get("patient_id", "").strip()
        patient_description = task_data.get("patient_description")
        consultation_purpose = task_data.get("consultation_purpose")
        files = task_data.get("files")
        user_id = task_data.get("user_id")

        overall_start_time = task_data.get("start_time", time.time())

        patient = None
        patient_timeline_str = ""

        # 获取或创建conversation_id
        conversation_id = task_data.get("conversation_id")
        if not conversation_id:
            # 创建新患者记录
            patient_name = "患者"  # 临时默认名称
            patient = BusPatientHelper.create_or_get_patient(
                db=db,
                name=patient_name,
                user_id=user_id,
                status="active"
            )
            patient_timeline_str = ""
            logger.info(f"[后台任务 {task_id}] 创建新患者 {patient.patient_id}")

            # 创建用户患者访问权限（上传用户自动授权查看和修改）
            BusPatientHelper.create_user_patient_access(
                db=db,
                user_id=user_id,
                patient_id=patient.patient_id,
                role="owner",
                can_edit=True,
                can_delete=False,
                can_share=False,
                granted_by=user_id
            )
            logger.info(f"[后台任务 {task_id}] 创建用户患者访问权限: user_id={user_id}, patient_id={patient.patient_id}, role=owner")

            # 创建会话记录
            session_id = f"patient_{task_id}"
            title_desc = patient_description[:50] if patient_description else "首次数据处理"
            title_suffix = '...' if len(title_desc) >= 50 else ''
            conversation = BusPatientHelper.create_conversation(
                db=db,
                patient_id=patient.patient_id,
                user_id=user_id,
                title=f"创建 - {title_desc}{title_suffix}",
                session_id=session_id,
                conversation_type="extraction"
            )
            db.commit()
            conversation_id = conversation.id
            task_status_store[task_id]["conversation_id"] = conversation_id
            logger.info(f"[后台任务 {task_id}] 会话记录: {conversation_id}")
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
            patient_timeline=patient_timeline_str,
            messages=[],
            files=files_to_pass,
            agent_session_id=conversation_id,
            existing_patient_data=None  # 首次创建，无现有数据
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

        # 保存 PatientDetail
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

        # 从结构化数据中提取患者姓名、年龄、性别等信息，并更新 bus_patient 表
        # 注意：根据 process_patient_data_task 的返回格式，患者基本信息在 patient_info.basic 中
        full_structure_data = result.get("full_structure_data", {})
        patient_info = full_structure_data.get("patient_info", {})
        basic_info = patient_info.get("basic", {})

        # 提取姓名
        extracted_name = basic_info.get("name")
        if extracted_name and extracted_name != "患者":
            patient.name = extracted_name
            logger.info(f"[后台任务 {task_id}] 从结构化数据中提取患者姓名: {extracted_name}")

        # 提取年龄（可以用来推算出生日期）
        age = basic_info.get("age")
        if age:
            try:
                from datetime import datetime
                # 尝试从年龄推算出生年份
                age_int = int(str(age).replace("岁", "").replace("周岁", "").strip())
                birth_year = datetime.now().year - age_int
                patient.birth_date = datetime(birth_year, 1, 1)  # 使用1月1日作为默认日期
                logger.info(f"[后台任务 {task_id}] 从年龄推算出生年份: {age} -> {birth_year}-01-01")
            except Exception as e:
                logger.warning(f"[后台任务 {task_id}] 从年龄推算出生日期失败: {age}, 错误: {e}")

        # 提取性别
        gender = basic_info.get("gender")
        if gender:
            patient.gender = gender
            logger.info(f"[后台任务 {task_id}] 从结构化数据中提取性别: {gender}")

        # 更新 raw_file_ids（用逗号分隔）
        if uploaded_file_ids:
            patient.raw_file_ids = ",".join(uploaded_file_ids)
            logger.info(f"[后台任务 {task_id}] 更新 raw_file_ids: {len(uploaded_file_ids)} 个文件")

        # 提交更新
        db.commit()
        logger.info(f"[后台任务 {task_id}] bus_patient 表已更新: 姓名={patient.name}, 性别={patient.gender}, 出生日期={patient.birth_date}, raw_file_ids={len(uploaded_file_ids) if uploaded_file_ids else 0}个文件")

        # 处理成功
        overall_duration = time.time() - overall_start_time

        task_status_store[task_id] = {
            "status": "completed",
            "progress": 100,
            "message": "患者数据处理完成",
            "duration": overall_duration,
            "patient_id": patient.patient_id,
            "conversation_id": conversation_id,
            "uploaded_files_count": len(uploaded_file_ids),
            "uploaded_file_ids": uploaded_file_ids
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
    patient_id: str,
    patient_description: str,
    consultation_purpose: str,
    files: list,
    user_id: str,
    background_tasks: BackgroundTasks,
    db: Session
):
    """
    首次患者数据处理：流式返回处理进度，支持断开后继续执行
    仅用于创建新患者，不支持更新现有患者
    """
    from src.crews.patient_data_crew.patient_data_crew import PatientDataCrew
    from app.utils.file_processing_manager import FileProcessingManager
    from app.utils.file_metadata_builder import FileMetadataBuilder
    from app.models.bus_patient_helpers import BusPatientHelper
    from app.models.bus_models import PatientConversation
    import asyncio

    conversation = None
    try:
        # 第一条消息：明确告知接收成功
        yield f"data: {json.dumps({'task_id': task_id, 'status': 'received', 'message': '✅ 保存成功，系统会在后台进行自动解析并添加到患者列表中，预计10~20分钟，您可以先关闭对话框，耐心等待。', 'progress': 0}, ensure_ascii=True)}\n\n"
        await asyncio.sleep(0)

        logger.info(f"[混合任务 {task_id}] 开始流式处理，patient_id={patient_id or '新建'}")

        overall_start_time = time.time()

        # 创建新患者记录
        patient_name = "患者"  # 临时默认名称，后续从结构化数据中提取真实姓名
        patient = BusPatientHelper.create_or_get_patient(
            db=db,
            name=patient_name,
            user_id=user_id,
            status="active"
        )
        patient_timeline_str = ""
        logger.info(f"[首次处理任务 {task_id}] 创建新患者 {patient.patient_id}")

        # 创建用户患者访问权限（上传用户自动授权查看和修改）
        BusPatientHelper.create_user_patient_access(
            db=db,
            user_id=user_id,
            patient_id=patient.patient_id,
            role="owner",
            can_edit=True,
            can_delete=False,
            can_share=False,
            granted_by=user_id
        )
        logger.info(f"[首次处理任务 {task_id}] 创建用户患者访问权限: user_id={user_id}, patient_id={patient.patient_id}, role=owner")

        # 创建会话记录
        session_id = f"patient_{task_id}"
        title_desc = patient_description[:50] if patient_description else "首次数据处理"
        title_suffix = '...' if len(title_desc) >= 50 else ''
        conversation = BusPatientHelper.create_conversation(
            db=db,
            patient_id=patient.patient_id,
            user_id=user_id,
            title=f"创建 - {title_desc}{title_suffix}",
            session_id=session_id,
            conversation_type="extraction"
        )
        db.commit()
        conversation_id = conversation.id

        logger.info(f"[混合任务 {task_id}] 会话记录: {conversation_id}")

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

            file_processing_start_time = time.time()

            # 创建一个队列来实时传递进度消息
            import queue
            progress_queue = queue.Queue()

            # 定义进度回调函数（在文件处理线程中调用）
            def file_progress_callback(current, total, message, file_info, stage):
                """文件上传进度回调 - 实时发送进度消息"""
                # 计算进度：文件接收阶段占 5-25%
                if stage == 'uploading':
                    progress = 5 + int((current - 0.5) / total * 20)  # 5-25%
                elif stage == 'uploaded':
                    progress = 5 + int(current / total * 20)  # 5-25%
                elif stage == 'upload_complete':
                    progress = 25
                else:
                    progress = 10

                progress_msg = {
                    'status': 'processing',
                    'stage': 'file_upload',
                    'message': message,
                    'progress': progress,
                    'file_info': {
                        'current': current,
                        'total': total,
                        'file_name': file_info.get('file_name') if file_info else None
                    }
                }
                # 放入队列，供异步发送
                progress_queue.put(progress_msg)

            # 在单独的线程中处理文件
            import threading
            result_container = {'files': None, 'ids': None, 'results': None, 'error': None}

            def process_files_thread():
                try:
                    file_manager = FileProcessingManager()
                    formatted, ids, results = file_manager.process_files(
                        files, conversation_id, progress_callback=file_progress_callback
                    )
                    result_container['files'] = formatted
                    result_container['ids'] = ids
                    result_container['results'] = results
                except Exception as e:
                    result_container['error'] = str(e)
                finally:
                    # 放入结束标记
                    progress_queue.put(None)

            # 启动文件处理线程
            thread = threading.Thread(target=process_files_thread)
            thread.start()

            # 实时从队列中读取并发送进度消息
            while True:
                try:
                    progress_msg = progress_queue.get(timeout=0.1)
                    if progress_msg is None:  # 结束标记
                        break

                    # 实时发送进度消息
                    yield f"data: {json.dumps(progress_msg, ensure_ascii=True)}\n\n"
                    await asyncio.sleep(0)
                    task_status_store[task_id].update(progress_msg)

                except queue.Empty:
                    # 队列为空，继续等待
                    await asyncio.sleep(0.1)
                    continue

            # 等待线程完成
            thread.join()

            # 检查是否有错误
            if result_container['error']:
                error_msg = {'status': 'error', 'message': f"文件处理失败: {result_container['error']}", 'error': result_container['error']}
                yield f"data: {json.dumps(error_msg, ensure_ascii=True)}\n\n"
                await asyncio.sleep(0)
                task_status_store[task_id].update(error_msg)
                return

            # 获取结果
            formatted_files = result_container['files']
            uploaded_file_ids = result_container['ids']
            extracted_file_results = result_container['results']

            file_processing_duration = time.time() - file_processing_start_time

            progress_msg = {'status': 'processing', 'stage': 'file_processing_completed', 'message': f'文件处理完成，共提取 {len(extracted_file_results)} 个文件', 'progress': 25}
            yield f"data: {json.dumps(progress_msg, ensure_ascii=True)}\n\n"
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
            patient_timeline=patient_timeline_str,
            messages=[],
            files=files_to_pass,
            agent_session_id=conversation_id,
            existing_patient_data=None  # 首次创建，无现有数据
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
                yield f"data: {json.dumps(progress_msg, ensure_ascii=True)}\n\n"
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
            yield f"data: {json.dumps(error_response, ensure_ascii=True)}\n\n"
            await asyncio.sleep(0)
            task_status_store[task_id].update(error_response)
            return

        # 保存 PatientDetail
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
        logger.info(f"[首次处理任务 {task_id}] 患者数据已保存到数据库")

        # 从结构化数据中提取患者姓名、年龄、性别等信息，并更新 bus_patient 表
        # 注意：full_structure_data 的格式是 { "patient_info": { "basic": { "name", "age", "gender" } }, "timeline": [...] }
        full_structure_data = result.get("full_structure_data", {})
        if full_structure_data and isinstance(full_structure_data, dict):
            patient_info = full_structure_data.get("patient_info", {})
            basic_info = patient_info.get("basic", {})

            # 提取姓名
            extracted_name = basic_info.get("name") or basic_info.get("姓名") or basic_info.get("患者姓名")
            if extracted_name and extracted_name != "患者":
                patient.name = extracted_name
                logger.info(f"[混合任务 {task_id}] 从结构化数据中提取患者姓名: {extracted_name}")

            # 提取年龄（可以用来推算出生日期）
            age = basic_info.get("age") or basic_info.get("年龄")
            if age:
                try:
                    from datetime import datetime
                    # 尝试从年龄推算出生年份
                    age_int = int(str(age).replace("岁", "").replace("周岁", "").strip())
                    birth_year = datetime.now().year - age_int
                    patient.birth_date = datetime(birth_year, 1, 1)  # 使用1月1日作为默认日期
                    logger.info(f"[混合任务 {task_id}] 从年龄推算出生年份: {age} -> {birth_year}-01-01")
                except Exception as e:
                    logger.warning(f"[混合任务 {task_id}] 从年龄推算出生日期失败: {age}, 错误: {e}")

            # 提取性别
            gender = basic_info.get("gender") or basic_info.get("性别")
            if gender:
                patient.gender = gender
                logger.info(f"[混合任务 {task_id}] 从结构化数据中提取性别: {gender}")

        # 更新 raw_file_ids（用逗号分隔）
        if uploaded_file_ids:
            # 合并现有文件ID和新文件ID，清理脏数据
            existing_ids = []
            if patient.raw_file_ids:
                # 清理现有数据：移除引号、方括号等脏字符
                cleaned = patient.raw_file_ids.replace('"', '').replace('[', '').replace(']', '')
                existing_ids = [id.strip() for id in cleaned.split(",") if id.strip()]
            all_file_ids = list(set(existing_ids + uploaded_file_ids))
            patient.raw_file_ids = ",".join(filter(None, all_file_ids))
            logger.info(f"[混合任务 {task_id}] 更新 raw_file_ids: 总共 {len(all_file_ids)} 个文件")

        # 提交更新
        db.commit()
        logger.info(f"[首次处理任务 {task_id}] bus_patient 表已更新: 姓名={patient.name}, 出生日期={patient.birth_date}, raw_file_ids={len(uploaded_file_ids) if uploaded_file_ids else 0}个文件")

        # 处理成功
        overall_duration = time.time() - overall_start_time

        final_result = {
            "status": "completed",
            "message": "患者数据处理完成",
            "progress": 100,
            "duration": overall_duration,
            "is_update": False,  # 首次创建
            "patient_id": patient.patient_id,
            "conversation_id": conversation_id,
            "uploaded_files_count": len(uploaded_file_ids),
            "uploaded_file_ids": uploaded_file_ids
        }

        yield f"data: {json.dumps(final_result, ensure_ascii=True)}\n\n"
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
        yield f"data: {json.dumps(error_response, ensure_ascii=True)}\n\n"
        await asyncio.sleep(0)
        task_status_store[task_id].update(error_response)


@router.post("/process_patient_data_smart")
async def process_patient_data_smart(
    request: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None)
) -> Any:
    """
    患者首次数据处理接口：用于创建新患者并处理其病历数据

    功能：
    - 创建新患者记录
    - 处理上传的文件和文本
    - 提取结构化患者数据（时间轴、诊疗历程、MDT报告等）
    - 支持流式进度返回
    - 支持客户端断开后后台继续执行

    请求参数:
        - user_id: 用户ID（可选，优先从 token 中获取）
        - patient_description: 患者说明文本（可选）
        - consultation_purpose: 会诊目的（可选）
        - files: 文件列表（可选，每个文件需包含file_name、file_content(base64)）
        - 注意：patient_description 和 files 至少需要提供一个

    认证方式：
        - 优先使用 Authorization header 中的 JWT token
        - 如果没有 token，使用请求体中的 user_id
        - 两者都没有则返回错误

    返回:
        流式响应（Server-Sent Events格式），第一条消息包含task_id

    注意：
        - 此接口仅用于首次创建患者
        - 如需更新现有患者数据，请使用 POST /api/patients/{patient_id}/chat 接口
    """
    try:
        # 1. 获取 user_id（优先从 token，其次从请求体）
        user_id = None

        # 尝试从 Authorization header 中解析 token
        if authorization:
            # 支持 "Bearer <token>" 和直接 "<token>" 两种格式
            token = authorization.replace("Bearer ", "").strip()
            if token:
                token_data = decode_external_token(token)
                if token_data:
                    user_id = token_data.get("user_id")
                    logger.info(f"从 token 中解析出 user_id: {user_id}")

        # 如果 token 中没有获取到 user_id，尝试从请求体获取
        if not user_id:
            user_id = request.get("user_id", "").strip()
            if user_id:
                logger.info(f"从请求体中获取 user_id: {user_id}")

        # 验证 user_id
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="缺少 user_id：请在 Authorization header 中提供有效的 token，或在请求体中提供 user_id",
            )

        # 2. 获取其他参数
        patient_description = request.get("patient_description", "")
        consultation_purpose = request.get("consultation_purpose", "")
        files = request.get("files", [])

        # 验证输入：至少 patient_description 或 files 有一个必须有值
        if not patient_description and not files:
            raise HTTPException(
                status_code=400,
                detail="patient_description 和 files 至少需要提供一个",
            )

        # 生成任务ID
        task_id = str(uuid.uuid4())

        # 初始化任务状态
        task_status_store[task_id] = {
            "status": "pending",
            "progress": 0,
            "message": "任务已创建",
            "start_time": time.time(),
            "user_id": user_id,
            "patient_id": "",  # 首次创建，无patient_id
            "patient_description": patient_description,
            "consultation_purpose": consultation_purpose,
            "files": files
        }

        # 初始化任务锁
        task_locks[task_id] = False

        logger.info(f"用户 {user_id} 创建首次处理任务 {task_id}，包含 {len(files)} 个文件")

        # 返回流式响应
        response = StreamingResponse(
            smart_stream_patient_data_processing(
                task_id=task_id,
                patient_id="",  # 首次创建，传空字符串
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
        logger.error(f"创建首次处理任务时出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"创建首次处理任务失败: {str(e)}"
        )
