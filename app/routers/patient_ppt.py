"""
患者PPT生成路由 - 基于 patient_id 的新架构（无需认证）
"""
from typing import Any, Dict
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


@router.post("/patients/{patient_id}/chat")
async def chat_with_patient(
    patient_id: str,
    request: Dict[str, Any],
    db: Session = Depends(get_db)
) -> Any:
    """
    对话式患者信息更新接口

    功能：
    - 支持对话式交互更新患者信息
    - 支持文本消息和文件上传
    - 自动提取结构化数据并更新患者记录
    - 流式返回AI响应

    请求参数:
        - message: 用户消息文本（必填）
        - files: 文件列表（可选，每个文件需包含file_name、file_content(base64)）

    返回:
        流式响应（Server-Sent Events格式）
    """
    from fastapi.responses import StreamingResponse
    from app.models.bus_patient_helpers import BusPatientHelper
    from app.models.bus_models import ConversationMessage
    from app.utils.file_processing_manager import FileProcessingManager
    from app.utils.file_metadata_builder import FileMetadataBuilder
    from src.crews.patient_data_crew.patient_data_crew import PatientDataCrew
    import asyncio
    import json
    import time

    try:
        # 1. 验证患者是否存在
        patient = db.query(Patient).filter(
            Patient.patient_id == patient_id,
            Patient.is_deleted == False
        ).first()

        if not patient:
            raise HTTPException(
                status_code=404,
                detail=f"患者不存在: {patient_id}"
            )

        # 2. 获取或创建会话
        user_message = request.get("message", "")
        files = request.get("files", [])

        if not user_message and not files:
            raise HTTPException(
                status_code=400,
                detail="message 和 files 至少需要提供一个"
            )

        # 获取或创建对话会话（conversation）
        # 这里简化处理：每个患者使用固定的conversation_id，或每次创建新的
        # 暂时采用每次创建新conversation的方式
        conversation = BusPatientHelper.create_conversation(
            db=db,
            patient_id=patient_id,
            user_id="system_user",
            title=f"对话 - {user_message[:30]}..." if user_message else "文件更新",
            conversation_type="chat"
        )
        db.commit()
        conversation_id = conversation.id

        logger.info(f"患者 {patient_id} 创建对话会话: {conversation_id}")

        # 3. 定义流式处理函数
        async def generate():
            """流式响应生成器"""
            try:
                start_time = time.time()

                # 步骤1: 保存用户消息
                user_msg = ConversationMessage(
                    conversation_id=conversation_id,
                    message_id=f"user_{int(time.time() * 1000)}",
                    role="user",
                    content=user_message,
                    type="user_message",
                    sequence_number=1
                )
                db.add(user_msg)
                db.commit()
                logger.info(f"保存用户消息: {user_msg.message_id}")

                yield f"data: {json.dumps({'status': 'processing', 'stage': 'message_saved', 'message': '消息已保存', 'progress': 5}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)

                # 步骤2: 处理文件上传
                uploaded_file_ids = []
                raw_files_data = []
                files_to_pass = []

                if files:
                    yield f"data: {json.dumps({'status': 'processing', 'stage': 'file_processing', 'message': f'正在处理 {len(files)} 个文件', 'progress': 10}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0)

                    file_manager = FileProcessingManager()
                    formatted_files, uploaded_file_ids, extracted_file_results = file_manager.process_files(
                        files, conversation_id
                    )

                    if extracted_file_results:
                        raw_files_data = FileMetadataBuilder.build_raw_files_data(extracted_file_results)
                        files_to_pass = FileMetadataBuilder.build_file_info_for_api(extracted_file_results)
                    elif formatted_files:
                        files_to_pass = formatted_files

                    yield f"data: {json.dumps({'status': 'processing', 'stage': 'file_processed', 'message': f'文件处理完成，共 {len(files_to_pass)} 个', 'progress': 30}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0)

                # 步骤3: 获取患者现有数据
                existing_patient_data = BusPatientHelper.get_patient_all_data_for_ppt(db, patient_id)
                patient_timeline_str = json.dumps(existing_patient_data.get("patient_timeline", {}), ensure_ascii=False)
                existing_full_content = existing_patient_data.get("patient_full_content", "")

                yield f"data: {json.dumps({'status': 'processing', 'stage': 'data_updating', 'message': '正在更新患者数据', 'progress': 40}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)

                # 步骤4: 调用patient_data_crew更新数据
                patient_crew = PatientDataCrew()
                result = None

                for progress_data in patient_crew.get_structured_patient_data_stream(
                    patient_info=user_message,
                    patient_timeline=patient_timeline_str,
                    messages=[],
                    files=files_to_pass,
                    agent_session_id=conversation_id,
                    existing_patient_data=existing_full_content
                ):
                    if progress_data.get("type") == "progress":
                        progress_msg = {
                            'status': 'processing',
                            'stage': progress_data.get('stage'),
                            'message': progress_data.get('message'),
                            'progress': 40 + int(progress_data.get('progress', 0) * 0.5)  # 映射到40-90%
                        }
                        yield f"data: {json.dumps(progress_msg, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0)
                    elif progress_data.get("type") == "result":
                        result = progress_data.get("data")

                # 检查结果
                if not result or "error" in result:
                    error_msg = result.get("error", "数据处理失败") if result else "数据处理失败"
                    yield f"data: {json.dumps({'status': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"
                    return

                # 步骤5: 更新数据库（使用 BusPatientHelper 保存到 bus_patient_structured_data）
                # 保存到bus_patient_structured_data表
                BusPatientHelper.save_structured_data(
                    db=db,
                    patient_id=patient_id,
                    conversation_id=conversation_id,
                    user_id="system_user",
                    patient_timeline=result.get("full_structure_data"),
                    patient_journey=result.get("patient_journey"),
                    mdt_simple_report=result.get("mdt_simple_report"),
                    patient_full_content=result.get("patient_content")
                )
                db.commit()
                logger.info(f"患者 {patient_id} 数据已更新")

                yield f"data: {json.dumps({'status': 'processing', 'stage': 'data_saved', 'message': '数据已保存', 'progress': 95}, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0)

                # 步骤6: 保存AI响应消息
                assistant_message = f"✅ 患者信息已更新成功！已处理 {len(uploaded_file_ids)} 个文件，更新了患者的结构化数据。"
                assistant_msg = ConversationMessage(
                    conversation_id=conversation_id,
                    message_id=f"assistant_{int(time.time() * 1000)}",
                    role="assistant",
                    content=assistant_message,
                    type="assistant_message",
                    sequence_number=2
                )
                db.add(assistant_msg)
                db.commit()
                logger.info(f"保存AI响应消息: {assistant_msg.message_id}")

                # 步骤7: 返回完成消息
                duration = time.time() - start_time
                final_msg = {
                    'status': 'completed',
                    'message': assistant_message,
                    'progress': 100,
                    'duration': duration,
                    'data': {
                        'patient_id': patient_id,
                        'conversation_id': conversation_id,
                        'files_count': len(uploaded_file_ids)
                    }
                }
                yield f"data: {json.dumps(final_msg, ensure_ascii=False)}\n\n"

                logger.info(f"chat接口处理完成，耗时: {duration:.2f}秒")

            except Exception as e:
                error_msg = f"处理失败: {str(e)}"
                logger.error(error_msg)
                import traceback
                logger.error(traceback.format_exc())
                yield f"data: {json.dumps({'status': 'error', 'message': error_msg}, ensure_ascii=False)}\n\n"

        # 返回流式响应
        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"chat接口异常: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"处理失败: {str(e)}"
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


