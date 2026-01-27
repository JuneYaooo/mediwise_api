"""
患者对话聊天接口 - 基于 patient_id 的多轮对话
使用 bus_patient_conversations 和 bus_conversation_messages 表

此接口支持：
1. 普通对话 - 根据用户问题和患者上下文回答
2. 患者数据更新 - 上传新文件或明确要求更新患者信息时，自动调用 PatientDataCrew 更新结构化数据

通过意图识别自动判断用户需求，无需单独调用不同接口。
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status, Header
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Any, List, Dict, Optional
import json
import asyncio
import time
import uuid
import os
from concurrent.futures import ThreadPoolExecutor

from app.db.database import get_db
from app.models.bus_models import (
    Patient,
    PatientConversation,
    ConversationMessage,
    PatientStructuredData
)
from app.models.bus_patient_helpers import BusPatientHelper
from app.models.patient_detail_helpers import PatientDetailHelper
from app.utils.datetime_utils import get_beijing_now_naive
from app.core.security import decode_external_token
from src.utils.logger import BeijingLogger

# 导入 Schema
from app.schemas.patient_chat import (
    PatientChatRequest,
    PatientConversationResponse,
    ConversationMessageResponse
)

# 导入服务层函数
from app.services.intent_detection import detect_intent_with_llm, INTENT_TYPES
from app.services.chat_helpers import (
    get_or_create_conversation,
    save_message,
    get_conversation_history,
    get_patient_context
)

# 初始化 logger
logger = BeijingLogger().get_logger()

router = APIRouter()

# 全局字典存储任务状态（生产环境应使用Redis或数据库）
chat_task_status_store = {}

# 全局字典存储后台任务锁（防止重复执行）
chat_task_locks = {}


# ============================================================================
# 流式处理函数
# ============================================================================

async def stream_chat_processing(
    task_id: str,
    patient_id: str,
    conversation_id: str,
    message: str,
    files: List[Dict],
    user_id: str,
    conversation_history: List[Dict],
    patient_context: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db: Session
):
    """
    流式处理对话请求
    """
    from app.utils.file_processing_manager import FileProcessingManager
    from app.utils.file_metadata_builder import FileMetadataBuilder
    
    try:
        overall_start_time = time.time()
        
        # 第一条消息：确认接收
        yield f"data: {json.dumps({'task_id': task_id, 'status': 'received', 'message': '消息已接收，正在处理...', 'progress': 0}, ensure_ascii=True)}\n\n"
        await asyncio.sleep(0)
        
        logger.info(f"[对话任务 {task_id}] 开始处理，patient_id={patient_id}, conversation_id={conversation_id}")
        
        # ========== 文件处理 ==========
        formatted_files = []
        uploaded_file_ids = []
        extracted_file_results = []
        raw_files_data = []  # 用于保存文件记录
        
        if files:
            progress_msg = {'status': 'processing', 'stage': 'file_processing', 'message': f'正在处理 {len(files)} 个文件', 'progress': 10}
            yield f"data: {json.dumps(progress_msg, ensure_ascii=True)}\n\n"
            await asyncio.sleep(0)
            
            file_manager = FileProcessingManager()
            formatted_files, uploaded_file_ids, extracted_file_results = file_manager.process_files(
                files, conversation_id
            )
            
            # 构建文件元数据（用于保存到 bus_patient_files）
            if extracted_file_results:
                raw_files_data = FileMetadataBuilder.build_raw_files_data(extracted_file_results)
            
            # 保存文件记录到 bus_patient_files 表
            if raw_files_data:
                try:
                    BusPatientHelper.save_patient_files(
                        db=db,
                        patient_id=patient_id,
                        user_id=user_id,
                        files_data=raw_files_data
                    )
                    db.commit()
                    logger.info(f"[对话任务 {task_id}] 已保存 {len(raw_files_data)} 个文件记录到 bus_patient_files")
                except Exception as e:
                    logger.error(f"[对话任务 {task_id}] 保存文件记录失败: {str(e)}")
                    # 不中断流程，继续处理
            
            # 更新患者的 raw_file_ids
            if uploaded_file_ids:
                try:
                    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
                    if patient:
                        # 清理现有数据：移除引号、方括号等脏字符
                        existing_ids = []
                        if patient.raw_file_ids:
                            cleaned = patient.raw_file_ids.replace('"', '').replace('[', '').replace(']', '')
                            existing_ids = [id.strip() for id in cleaned.split(",") if id.strip()]
                        all_file_ids = list(set(existing_ids + uploaded_file_ids))
                        patient.raw_file_ids = ",".join(filter(None, all_file_ids))
                        db.commit()
                        logger.info(f"[对话任务 {task_id}] 更新患者 raw_file_ids: 总共 {len(all_file_ids)} 个文件")
                except Exception as e:
                    logger.error(f"[对话任务 {task_id}] 更新患者 raw_file_ids 失败: {str(e)}")
            
            progress_msg = {'status': 'processing', 'stage': 'file_processing_completed', 'message': f'文件处理完成，已保存 {len(raw_files_data)} 个文件', 'progress': 25}
            yield f"data: {json.dumps(progress_msg, ensure_ascii=True)}\n\n"
            await asyncio.sleep(0)
        
        # 构建文件信息（传递给 AI）
        files_to_pass = []
        if extracted_file_results:
            files_to_pass = FileMetadataBuilder.build_file_info_for_api(extracted_file_results)
        elif formatted_files:
            files_to_pass = formatted_files
        
        # ========== 意图识别（使用大模型） ==========
        intent_result = await detect_intent_with_llm(
            message=message, 
            files=files, 
            patient_context=patient_context,
            conversation_history=conversation_history
        )
        intent = intent_result["intent"]
        intent_reason = intent_result["reason"]
        intent_confidence = intent_result.get("confidence", 0.8)
        user_requirement = intent_result.get("user_requirement", message)
        modify_type = intent_result.get("modify_type")
        
        logger.info(f"[对话任务 {task_id}] 意图识别结果: intent={intent}, confidence={intent_confidence}, reason={intent_reason}, modify_type={modify_type}")

        # ========== 根据意图分支处理 ==========
        if intent in ["update_data", "modify_data"]:
            # 更新/修改患者数据分支 - 调用 PatientDataCrew
            async for chunk in _process_update_data(
                task_id=task_id,
                patient_id=patient_id,
                conversation_id=conversation_id,
                message=message,
                files_to_pass=files_to_pass,
                user_id=user_id,
                patient_context=patient_context,
                db=db,
                user_requirement=user_requirement,
                modify_type=modify_type
            ):
                yield chunk
        else:
            # 普通对话分支（chat）- 使用通用 LLM 回复
            async for chunk in _process_chat(
                task_id=task_id,
                patient_id=patient_id,
                conversation_id=conversation_id,
                message=message,
                files_to_pass=files_to_pass,
                conversation_history=conversation_history,
                patient_context=patient_context,
                db=db
            ):
                yield chunk
        
        # 更新会话的 last_message_at
        conversation = db.query(PatientConversation).filter(
            PatientConversation.id == conversation_id
        ).first()
        if conversation:
            conversation.last_message_at = get_beijing_now_naive()
            conversation.updated_at = get_beijing_now_naive()
            db.commit()
        
        # 处理完成
        overall_duration = time.time() - overall_start_time
        
        final_result = {
            "status": "completed",
            "message": "处理完成",
            "progress": 100,
            "duration": overall_duration,
            "result": {
                "patient_id": patient_id,
                "conversation_id": conversation_id,
                "intent": intent,
                "files_processed": len(uploaded_file_ids)
            }
        }
        
        yield f"data: {json.dumps(final_result, ensure_ascii=True)}\n\n"
        
        logger.info(f"[对话任务 {task_id}] 处理完成，耗时: {overall_duration:.2f}秒")
        
    except Exception as e:
        logger.error(f"[对话任务 {task_id}] 处理失败: {str(e)}")
        import traceback
        traceback.print_exc()
        
        error_msg = {
            "status": "error",
            "message": f"处理失败: {str(e)}",
            "error_type": type(e).__name__
        }
        yield f"data: {json.dumps(error_msg, ensure_ascii=True)}\n\n"


async def _process_update_data(
    task_id: str,
    patient_id: str,
    conversation_id: str,
    message: str,
    files_to_pass: List[Dict],
    user_id: str,
    patient_context: Dict[str, Any],
    db: Session,
    user_requirement: str = None,
    modify_type: str = None
):
    """
    处理更新/修改患者数据的分支
    
    Args:
        modify_type: 修改类型
            - "add_new_data": 新增患者数据（调用 PatientDataCrew）
            - "modify_current_data": 修改已有数据（调用 PatientInfoUpdateCrew）
    """
    from src.crews.patient_data_crew.patient_data_crew import PatientDataCrew
    from src.crews.patient_info_update_crew.patient_info_update_crew import PatientInfoUpdateCrew
    
    # 根据 modify_type 显示不同的进度信息
    if modify_type == "modify_current_data":
        progress_msg = {'status': 'processing', 'stage': 'data_modification', 'message': '正在修改患者数据...', 'progress': 35}
    else:
        progress_msg = {'status': 'processing', 'stage': 'data_extraction', 'message': '正在提取患者数据...', 'progress': 35}
    yield f"data: {json.dumps(progress_msg, ensure_ascii=True)}\n\n"
    
    try:
        # 获取现有患者数据 - 直接按 patient_id 查询所有类型的数据
        existing_patient_data = {
            "patient_timeline": {},
            "patient_journey": {},
            "mdt_simple_report": {},
            "patient_content": ""
        }
        
        # 查询该患者的所有结构化数据（按 data_type 分别查询最新记录）
        from app.models.bus_models import PatientStructuredData
        
        # 1. 查询 timeline
        timeline_record = db.query(PatientStructuredData).filter(
            PatientStructuredData.patient_id == patient_id,
            PatientStructuredData.data_type == "timeline",
            PatientStructuredData.is_deleted == False
        ).order_by(PatientStructuredData.created_at.desc()).first()
        
        if timeline_record:
            existing_patient_data["patient_timeline"] = timeline_record.structuredcontent or {}
            existing_patient_data["patient_content"] = timeline_record.text_content or ""
            logger.info(f"[对话任务 {task_id}] 查询到 timeline 数据，conversation_id={timeline_record.conversation_id}")
        
        # 2. 查询 journey
        journey_record = db.query(PatientStructuredData).filter(
            PatientStructuredData.patient_id == patient_id,
            PatientStructuredData.data_type == "journey",
            PatientStructuredData.is_deleted == False
        ).order_by(PatientStructuredData.created_at.desc()).first()
        
        if journey_record:
            existing_patient_data["patient_journey"] = journey_record.structuredcontent or {}
            logger.info(f"[对话任务 {task_id}] 查询到 journey 数据，conversation_id={journey_record.conversation_id}")
        
        # 3. 查询 mdt_report
        mdt_record = db.query(PatientStructuredData).filter(
            PatientStructuredData.patient_id == patient_id,
            PatientStructuredData.data_type == "mdt_report",
            PatientStructuredData.is_deleted == False
        ).order_by(PatientStructuredData.created_at.desc()).first()
        
        if mdt_record:
            existing_patient_data["mdt_simple_report"] = mdt_record.structuredcontent or {}
            logger.info(f"[对话任务 {task_id}] ✅ 查询到 mdt_report 数据，conversation_id={mdt_record.conversation_id}, 数据长度={len(str(mdt_record.structuredcontent))}")
        else:
            # 确保即使查询不到也设置为空字典
            existing_patient_data["mdt_simple_report"] = {}
            logger.warning(f"[对话任务 {task_id}] ⚠️ 未查询到 mdt_report 数据，已设置为空字典")
        
        # 使用线程池执行同步的 crew 方法
        loop = asyncio.get_event_loop()
        
        # 根据 modify_type 选择不同的处理方式
        if modify_type == "modify_current_data":
            # 修改现有数据，使用 PatientInfoUpdateCrew
            logger.info(f"[对话任务 {task_id}] 使用 PatientInfoUpdateCrew 修改现有患者数据")
            
            update_crew = PatientInfoUpdateCrew()
            
            progress_msg = {'status': 'processing', 'stage': 'crew_processing', 'message': '正在分析并修改患者数据...', 'progress': 40}
            yield f"data: {json.dumps(progress_msg, ensure_ascii=True)}\n\n"
            
            # 构建当前患者数据（包含 patient_content 以便 PatientInfoUpdateCrew 使用）
            # 确保所有必需的键都存在，即使值为空
            current_patient_data = {
                "patient_timeline": existing_patient_data.get("patient_timeline") or {},
                "patient_journey": existing_patient_data.get("patient_journey") or {},
                "mdt_simple_report": existing_patient_data.get("mdt_simple_report") or {},
                "patient_content": existing_patient_data.get("patient_content") or ""
            }
            
            # 二次检查：确保所有值都不是 None
            for key in ["patient_timeline", "patient_journey", "mdt_simple_report"]:
                if current_patient_data[key] is None:
                    current_patient_data[key] = {}
                    logger.warning(f"[对话任务 {task_id}] {key} 为 None，已设置为空字典")
            
            if current_patient_data["patient_content"] is None:
                current_patient_data["patient_content"] = ""
                logger.warning(f"[对话任务 {task_id}] patient_content 为 None，已设置为空字符串")
            
            # 记录数据结构用于调试
            logger.info(f"[对话任务 {task_id}] ========== 数据传递检查 ==========")
            logger.info(f"[对话任务 {task_id}] current_patient_data 的键: {list(current_patient_data.keys())}")
            logger.info(f"[对话任务 {task_id}] 当前患者数据结构:")
            logger.info(f"  - patient_timeline: {'存在' if current_patient_data.get('patient_timeline') else '为空'} (类型: {type(current_patient_data.get('patient_timeline')).__name__})")
            logger.info(f"  - patient_journey: {'存在' if current_patient_data.get('patient_journey') else '为空'} (类型: {type(current_patient_data.get('patient_journey')).__name__})")
            logger.info(f"  - mdt_simple_report: {'存在' if current_patient_data.get('mdt_simple_report') else '为空'} (类型: {type(current_patient_data.get('mdt_simple_report')).__name__}, 长度: {len(str(current_patient_data.get('mdt_simple_report', {})))})")
            logger.info(f"  - patient_content: 长度 {len(current_patient_data.get('patient_content', ''))}")
            logger.info(f"[对话任务 {task_id}] ======================================")
            
            # 使用 task_async 方法执行更新
            result = await update_crew.task_async(
                central_command="执行患者信息修改",
                user_requirement=user_requirement or message,
                current_patient_data=current_patient_data,
                writer=None,  # API 模式不使用 writer
                show_status_realtime=False,
                agent_session_id=conversation_id
            )
        else:
            # 新增患者数据，使用 PatientDataCrew
            logger.info(f"[对话任务 {task_id}] 使用 PatientDataCrew 新增患者数据")
            
            patient_data_crew = PatientDataCrew()
            
            progress_msg = {'status': 'processing', 'stage': 'crew_processing', 'message': '正在分析文件并提取结构化数据（可能需要5-10分钟）...', 'progress': 40}
            yield f"data: {json.dumps(progress_msg, ensure_ascii=True)}\n\n"
            
            def run_crew():
                return patient_data_crew.get_structured_patient_data(
                    patient_info=message,
                    patient_timeline=existing_patient_data.get("patient_timeline", {}),
                    messages=[],  # 不需要历史消息
                    files=files_to_pass,
                    agent_session_id=conversation_id,
                    existing_patient_data=existing_patient_data,
                    patient_id=patient_id  # 传入患者ID
                )
            
            with ThreadPoolExecutor() as executor:
                result = await loop.run_in_executor(executor, run_crew)
        
        if "error" in result:
            error_msg = {'status': 'error', 'stage': 'crew_error', 'message': f'数据处理失败: {result["error"]}'}
            yield f"data: {json.dumps(error_msg, ensure_ascii=True)}\n\n"
            return
        
        progress_msg = {'status': 'processing', 'stage': 'data_extracted', 'message': '数据处理完成，正在保存...', 'progress': 80}
        yield f"data: {json.dumps(progress_msg, ensure_ascii=True)}\n\n"
        
        # 保存/更新结构化数据到数据库
        patient_timeline = result.get('full_structure_data', {})
        patient_journey = result.get('patient_journey', {})
        mdt_simple_report = result.get('mdt_simple_report', {})
        patient_content = result.get('patient_content', '')
        
        # 使用 update_structured_data 方法，它会更新现有记录而不是创建新记录
        updated_records = BusPatientHelper.update_structured_data(
            db=db,
            patient_id=patient_id,
            patient_timeline=patient_timeline,
            patient_journey=patient_journey,
            mdt_simple_report=mdt_simple_report,
            patient_full_content=patient_content,
            user_id=user_id
        )
        db.commit()
        
        logger.info(f"[对话任务 {task_id}] 结构化数据已更新到 bus_patient_structured_data，更新了 {len(updated_records)} 个数据类型")
        
        progress_msg = {'status': 'processing', 'stage': 'data_saved', 'message': '患者数据已更新，正在生成确认消息...', 'progress': 90}
        yield f"data: {json.dumps(progress_msg, ensure_ascii=True)}\n\n"
        
        # 返回工具输出（结构化数据）- 先返回工具输出，再返回流式确认消息
        tool_output = {
            'status': 'tool_output',
            'stage': 'patient_timeline',
            'data': {
                'tool_name': 'patient_timeline',
                'tool_type': 'timeline',
                'agent_name': '患者数据处理专家',
                'content': {
                    'patient_timeline': patient_timeline,
                    'patient_journey': patient_journey,
                    'mdt_simple_report': mdt_simple_report
                }
            }
        }
        yield f"data: {json.dumps(tool_output, ensure_ascii=True)}\n\n"
        
        # 使用 LLM 生成流式确认消息
        full_response = ""
        async for chunk in _generate_streaming_confirmation(
            user_requirement=user_requirement or message,
            modify_type=modify_type,
            patient_timeline=patient_timeline,
            files_count=len(files_to_pass) if files_to_pass else 0
        ):
            full_response += chunk
            stream_msg = {
                'status': 'streaming',
                'stage': 'response',
                'content': chunk,
                'progress': 95
            }
            yield f"data: {json.dumps(stream_msg, ensure_ascii=True)}\n\n"
            await asyncio.sleep(0)  # 确保流式数据及时发送
        
        # 保存助手回复（保存完整的流式内容）
        if full_response:
            save_message(
                db=db,
                conversation_id=conversation_id,
                role="assistant",
                content=full_response,
                message_type="reply",
                agent_name="patient_data_processor"
            )
            db.commit()
            logger.info(f"[对话任务 {task_id}] 助手回复已保存，长度: {len(full_response)}")
        
    except Exception as e:
        logger.error(f"[对话任务 {task_id}] 数据更新失败: {str(e)}")
        import traceback
        traceback.print_exc()
        
        error_msg = {'status': 'error', 'stage': 'update_error', 'message': f'数据更新失败: {str(e)}'}
        yield f"data: {json.dumps(error_msg, ensure_ascii=True)}\n\n"


async def _generate_streaming_confirmation(
    user_requirement: str,
    modify_type: str,
    patient_timeline: Dict,
    files_count: int
):
    """
    使用 LLM 生成流式确认消息
    
    参考 medical_graph_stream.py 中的 generate_modification_confirmation 函数
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage
    
    try:
        # 使用通用对话模型
        model = ChatOpenAI(
            model=os.getenv('GENERAL_CHAT_MODEL_NAME', 'deepseek-chat'),
            api_key=os.getenv('GENERAL_CHAT_API_KEY'),
            base_url=os.getenv('GENERAL_CHAT_BASE_URL'),
            streaming=True,
            timeout=600
        )
        
        # 根据修改类型生成不同的确认消息
        if modify_type == "add_new_data":
            action_description = "新增患者数据"
        else:
            action_description = "修改患者信息"
        
        # 统计时间轴信息
        timeline_entries = 0
        if patient_timeline and isinstance(patient_timeline, dict):
            timeline = patient_timeline.get('timeline', [])
            if isinstance(timeline, list):
                timeline_entries = len(timeline)
        
        # 构建上下文信息
        context_info = []
        if files_count > 0:
            context_info.append(f"已处理 {files_count} 个文件")
        if timeline_entries > 0:
            context_info.append(f"时间轴包含 {timeline_entries} 条记录")
        context_str = "、".join(context_info) if context_info else "数据已更新"
        
        prompt = f"""假设你是医疗AI助手Mediwise，刚刚完成了{action_description}的任务。请用简洁、专业且友好的语言向用户确认操作已完成。

用户的原始需求：{user_requirement}

完成情况：{context_str}

请生成一个简短的确认消息，内容应该包括：
1. 确认{action_description}已经完成
2. 简要说明完成了什么操作（基于上述完成情况）
3. 提醒用户可以查看更新后的患者信息
4. 询问是否还需要其他帮助

语言要求：
- 使用中文
- 语气专业但亲切
- 简洁明了，不要过于冗长（控制在100字以内）
- 体现医疗AI的专业性
- 使用适当的emoji增加友好感"""

        messages = [HumanMessage(content=prompt)]
        
        # 流式输出确认消息
        async for chunk in model.astream(messages):
            if hasattr(chunk, 'content') and chunk.content:
                yield chunk.content
                
    except Exception as e:
        logger.error(f"生成流式确认消息失败: {str(e)}")
        # 回退到简单的确认消息
        action_description = "新增患者数据" if modify_type == "add_new_data" else "修改患者信息"
        yield f"✅ {action_description}已完成！您可以查看更新后的患者信息。如需其他帮助，请随时告诉我。"


def _generate_update_confirmation(patient_timeline: Dict, files: List[Dict]) -> str:
    """生成数据更新确认消息（备用方法，同步版本）"""
    files_count = len(files) if files else 0
    
    # 统计时间轴信息
    timeline_entries = 0
    if patient_timeline and isinstance(patient_timeline, dict):
        timeline = patient_timeline.get('timeline', [])
        if isinstance(timeline, list):
            timeline_entries = len(timeline)
    
    message_parts = ["✅ **患者数据更新成功！**\n"]
    
    if files_count > 0:
        message_parts.append(f"- 已处理 {files_count} 个文件")
    
    if timeline_entries > 0:
        message_parts.append(f"- 时间轴包含 {timeline_entries} 条记录")
    
    message_parts.append("\n您可以继续对话，或查看更新后的患者信息。")
    
    return "\n".join(message_parts)


async def _process_chat(
    task_id: str,
    patient_id: str,
    conversation_id: str,
    message: str,
    files_to_pass: List[Dict],
    conversation_history: List[Dict],
    patient_context: Dict[str, Any],
    db: Session
):
    """
    处理普通对话的分支
    使用通用 LLM 回复
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    
    progress_msg = {'status': 'processing', 'stage': 'ai_processing', 'message': '正在生成回复...', 'progress': 35}
    yield f"data: {json.dumps(progress_msg, ensure_ascii=True)}\n\n"
    
    try:
        # 初始化 LLM
        model = ChatOpenAI(
            model=os.getenv('GENERAL_CHAT_MODEL_NAME', 'deepseek-chat'),
            api_key=os.getenv('GENERAL_CHAT_API_KEY'),
            base_url=os.getenv('GENERAL_CHAT_BASE_URL'),
            streaming=True,
            timeout=600
        )
        
        # 构建系统提示
        patient_info = patient_context.get("patient_info") or {}
        patient_timeline = patient_context.get("patient_timeline") or {}
        
        system_prompt = f"""你是一个专业的医疗AI助手 MediWise。你正在帮助医生处理关于特定患者的问题。

【患者基本信息】
{json.dumps(patient_info, ensure_ascii=False, indent=2) if patient_info else "暂无患者基本信息"}

【患者时间轴数据】
{json.dumps(patient_timeline, ensure_ascii=False, indent=2)[:5000] if patient_timeline else "暂无患者时间轴数据"}

请根据上述患者信息，回答用户的问题。如果用户上传了新的文件或明确要求更新患者数据，请告知用户可以直接说"请更新患者数据"或上传文件来触发数据更新流程。

回答要求：
1. 专业、准确、简洁
2. 结合患者的具体情况给出建议
3. 如果信息不足，请明确指出需要哪些额外信息
4. 使用中文回答
"""
        
        # 构建消息列表
        messages = [SystemMessage(content=system_prompt)]
        
        # 添加历史对话
        for hist in conversation_history[-10:]:  # 只取最近10条历史
            if hist["role"] == "user":
                messages.append(HumanMessage(content=hist["content"]))
            elif hist["role"] == "assistant":
                messages.append(AIMessage(content=hist["content"]))
        
        # 添加当前用户消息
        current_message = message
        if files_to_pass:
            file_info = "\n\n[用户上传的文件]:\n"
            for f in files_to_pass:
                file_info += f"- {f.get('file_name', '未知文件')}\n"
            current_message += file_info
        
        messages.append(HumanMessage(content=current_message))
        
        # 流式生成回复
        full_response = ""
        async for chunk in model.astream(messages):
            if hasattr(chunk, 'content') and chunk.content:
                content = chunk.content
                full_response += content

                stream_msg = {
                    'status': 'streaming',
                    'stage': 'response',
                    'content': content,
                    'progress': 60
                }
                yield f"data: {json.dumps(stream_msg, ensure_ascii=True)}\n\n"
                await asyncio.sleep(0)  # 确保流式数据及时发送
        
        # 保存助手回复
        if full_response:
            # 获取用户消息ID作为parent_id
            user_messages = db.query(ConversationMessage).filter(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.role == "user"
            ).order_by(ConversationMessage.sequence_number.desc()).first()
            
            parent_id = user_messages.message_id if user_messages else None
            
            save_message(
                db=db,
                conversation_id=conversation_id,
                role="assistant",
                content=full_response,
                message_type="reply",
                parent_id=parent_id,
                agent_name="chat_assistant"
            )
            db.commit()
            
            logger.info(f"[对话任务 {task_id}] 助手回复已保存，长度: {len(full_response)}")

    except Exception as e:
        logger.error(f"[对话任务 {task_id}] 对话处理失败: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # 回退到简单回复
        fallback_response = f"抱歉，处理您的请求时遇到了问题。您说：\"{message}\"。请稍后重试或联系管理员。"
        
        stream_msg = {
            'status': 'streaming',
            'stage': 'response',
            'content': fallback_response,
            'progress': 90
        }
        yield f"data: {json.dumps(stream_msg, ensure_ascii=True)}\n\n"
        
        # 保存回退回复
        save_message(
            db=db,
            conversation_id=conversation_id,
            role="assistant",
            content=fallback_response,
            message_type="reply"
        )
        db.commit()


# ============================================================================
# API 接口
# ============================================================================

@router.post("/{patient_id}/chat")
async def chat_with_patient(
    patient_id: str,
    request: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None)
) -> Any:
    """
    患者对话接口 - 基于 patient_id 的多轮对话聊天（混合模式）
    
    功能：
    - 与指定患者进行多轮对话
    - 支持文本消息和文件上传
    - 流式返回 AI 回复
    - 自动保存对话历史到 bus_conversation_messages 表
    - 支持继续已有会话或创建新会话
    - 支持两种历史消息模式（混合模式）
    
    请求参数：
        - message: 用户消息文本（可选）
        - files: 文件列表（可选，每个文件需包含 file_name、file_content(base64)）
        - conversation_id: 会话ID（可选，不传则创建新会话）
        - messages: 对话历史（可选，类似 OpenAI 格式）
            格式: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
        - 注意：message 和 files 至少需要提供一个
    
    历史消息模式说明：
        1. 只传 conversation_id：从数据库自动加载历史消息
        2. 只传 messages：使用传入的消息作为上下文（无状态模式）
        3. 两者都传：messages 优先作为上下文，但消息仍保存到 conversation_id 对应的会话
        4. 都不传：创建新会话，无历史上下文
    
    返回：
        流式响应（Server-Sent Events 格式）
    """
    try:
        # 1. 获取请求参数
        message = request.get("message", "").strip()
        files = request.get("files", [])
        conversation_id = request.get("conversation_id")
        client_messages = request.get("messages", [])  # 客户端传入的历史消息（类似 OpenAI）
        
        # 2. 验证输入
        if not message and not files:
            raise HTTPException(
                status_code=400,
                detail="message 和 files 至少需要提供一个"
            )
        
        # 验证 messages 格式
        if client_messages:
            if not isinstance(client_messages, list):
                raise HTTPException(
                    status_code=400,
                    detail="messages 必须是数组格式"
                )
            for msg in client_messages:
                if not isinstance(msg, dict) or "role" not in msg or "content" not in msg:
                    raise HTTPException(
                        status_code=400,
                        detail="messages 中每条消息必须包含 role 和 content 字段"
                    )
                if msg["role"] not in ["user", "assistant", "system"]:
                    raise HTTPException(
                        status_code=400,
                        detail="messages 中 role 必须是 user、assistant 或 system"
                    )
        
        # 3. 验证患者是否存在
        patient = db.query(Patient).filter(
            Patient.patient_id == patient_id,
            Patient.is_deleted == False
        ).first()
        
        if not patient:
            raise HTTPException(
                status_code=404,
                detail=f"患者不存在: {patient_id}"
            )
        
        # 4. 生成任务ID
        task_id = str(uuid.uuid4())

        # 5. 获取 user_id（优先从 token，其次从请求体）
        user_id = None

        # 尝试从 Authorization header 中解析 token
        if authorization:
            token = authorization.replace("Bearer ", "").strip()
            if token:
                token_data = decode_external_token(token)
                if token_data:
                    user_id = token_data.get("user_id")
                    logger.info(f"从 token 中解析出 user_id: {user_id}")

        # 如果 token 中没有获取到 user_id，尝试从请求体获取
        if not user_id:
            user_id = request.get("user_id", "").strip() if request.get("user_id") else ""
            if user_id:
                logger.info(f"从请求体中获取 user_id: {user_id}")

        # 验证 user_id
        if not user_id:
            raise HTTPException(
                status_code=400,
                detail="缺少 user_id：请在 Authorization header 中提供有效的 token，或在请求体中提供 user_id"
            )

        # 6. 获取或创建会话
        # 生成会话标题（如果没有文本消息但有文件，使用文件信息）
        conversation_title = None
        if message:
            conversation_title = message[:30] + "..." if len(message) > 30 else message
        elif files:
            conversation_title = f"上传了 {len(files)} 个文件"

        conversation = get_or_create_conversation(
            db=db,
            patient_id=patient_id,
            user_id=user_id,
            conversation_id=conversation_id,
            title=conversation_title
        )
        conversation_id = conversation.id
        
        # 6. 保存用户消息
        # 如果没有文本消息但有文件，生成默认消息
        user_message_content = message
        if not message and files:
            user_message_content = f"[上传了 {len(files)} 个文件]"

        user_msg = save_message(
            db=db,
            conversation_id=conversation_id,
            role="user",
            content=user_message_content,
            message_type="text"
        )
        db.commit()
        
        # 7. 获取会话历史（混合模式）
        # 优先使用客户端传入的 messages，否则从数据库加载
        if client_messages:
            # 客户端传入的历史消息（类似 OpenAI 模式）
            conversation_history = [
                {"role": msg["role"], "content": msg["content"]}
                for msg in client_messages
                if msg["role"] in ["user", "assistant"]  # 过滤掉 system 消息
            ]
            logger.info(f"[对话任务 {task_id}] 使用客户端传入的历史消息，共 {len(conversation_history)} 条")
        else:
            # 从数据库加载历史消息（conversation_id 模式）
            conversation_history = get_conversation_history(db, conversation_id)
            logger.info(f"[对话任务 {task_id}] 从数据库加载历史消息，共 {len(conversation_history)} 条")
        
        # 8. 获取患者上下文
        patient_context = get_patient_context(db, patient_id)
        
        # 9. 初始化任务状态
        chat_task_status_store[task_id] = {
            "status": "pending",
            "progress": 0,
            "message": "任务已创建",
            "start_time": time.time(),
            "patient_id": patient_id,
            "conversation_id": conversation_id,
            "user_id": user_id
        }
        
        chat_task_locks[task_id] = False
        
        logger.info(f"用户 {user_id} 创建对话任务 {task_id}，patient_id={patient_id}，conversation_id={conversation_id}")
        
        # 10. 返回流式响应
        response = StreamingResponse(
            stream_chat_processing(
                task_id=task_id,
                patient_id=patient_id,
                conversation_id=conversation_id,
                message=message,
                files=files,
                user_id=user_id,
                conversation_history=conversation_history,
                patient_context=patient_context,
                background_tasks=background_tasks,
                db=db
            ),
            media_type="text/event-stream"
        )
        
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


@router.get("/{patient_id}/chats")
def list_patient_chats(
    patient_id: str,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
) -> Any:
    """
    获取患者的所有聊天会话列表
    """
    # 验证患者是否存在
    patient = db.query(Patient).filter(
        Patient.patient_id == patient_id,
        Patient.is_deleted == False
    ).first()
    
    if not patient:
        raise HTTPException(
            status_code=404,
            detail=f"患者不存在: {patient_id}"
        )
    
    # 查询会话列表
    conversations = db.query(PatientConversation).filter(
        PatientConversation.patient_id == patient_id
    ).order_by(PatientConversation.updated_at.desc()).offset(skip).limit(limit).all()
    
    return {
        "status": "success",
        "patient_id": patient_id,
        "total": len(conversations),
        "conversations": [
            {
                "id": conv.id,
                "session_id": conv.session_id,
                "title": conv.title,
                "conversation_type": conv.conversation_type,
                "status": conv.status,
                "created_at": conv.created_at.isoformat() if conv.created_at else None,
                "updated_at": conv.updated_at.isoformat() if conv.updated_at else None,
                "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None
            }
            for conv in conversations
        ]
    }


@router.get("/{patient_id}/chats/{chat_id}/messages")
def get_chat_messages(
    patient_id: str,
    chat_id: str,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> Any:
    """
    获取指定聊天的消息列表
    """
    # 验证患者是否存在
    patient = db.query(Patient).filter(
        Patient.patient_id == patient_id,
        Patient.is_deleted == False
    ).first()
    
    if not patient:
        raise HTTPException(
            status_code=404,
            detail=f"患者不存在: {patient_id}"
        )
    
    # 验证聊天是否属于该患者
    conversation = db.query(PatientConversation).filter(
        PatientConversation.id == chat_id,
        PatientConversation.patient_id == patient_id
    ).first()
    
    if not conversation:
        raise HTTPException(
            status_code=404,
            detail=f"聊天不存在: {chat_id}"
        )
    
    # 查询消息列表
    messages = db.query(ConversationMessage).filter(
        ConversationMessage.conversation_id == chat_id
    ).order_by(ConversationMessage.sequence_number.asc()).offset(skip).limit(limit).all()
    
    return {
        "status": "success",
        "patient_id": patient_id,
        "chat_id": chat_id,
        "total": len(messages),
        "messages": [
            {
                "id": msg.id,
                "message_id": msg.message_id,
                "role": msg.role,
                "content": msg.content,
                "type": msg.type,
                "agent_name": msg.agent_name,
                "parent_id": msg.parent_id,
                "sequence_number": msg.sequence_number,
                "tool_outputs": msg.tooloutputs,
                "status_data": msg.statusdata,
                "created_at": msg.created_at.isoformat() if msg.created_at else None
            }
            for msg in messages
        ]
    }


@router.get("/chat_task_status/{task_id}")
async def get_chat_task_status(
    task_id: str,
) -> Any:
    """
    查询对话任务状态
    """
    if task_id not in chat_task_status_store:
        raise HTTPException(
            status_code=404,
            detail="任务不存在"
        )
    
    return chat_task_status_store[task_id]


@router.delete("/{patient_id}/chats/{chat_id}")
def delete_chat(
    patient_id: str,
    chat_id: str,
    db: Session = Depends(get_db),
) -> Any:
    """
    删除指定聊天及其所有消息
    """
    # 验证患者是否存在
    patient = db.query(Patient).filter(
        Patient.patient_id == patient_id,
        Patient.is_deleted == False
    ).first()
    
    if not patient:
        raise HTTPException(
            status_code=404,
            detail=f"患者不存在: {patient_id}"
        )
    
    # 验证聊天是否属于该患者
    conversation = db.query(PatientConversation).filter(
        PatientConversation.id == chat_id,
        PatientConversation.patient_id == patient_id
    ).first()
    
    if not conversation:
        raise HTTPException(
            status_code=404,
            detail=f"聊天不存在: {chat_id}"
        )
    
    try:
        # 删除所有消息
        db.query(ConversationMessage).filter(
            ConversationMessage.conversation_id == chat_id
        ).delete(synchronize_session=False)
        
        # 删除聊天
        db.delete(conversation)
        db.commit()
        
        return {
            "status": "success",
            "message": "聊天已删除",
            "chat_id": chat_id
        }
        
    except Exception as e:
        db.rollback()
        logger.error(f"删除聊天失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"删除聊天失败: {str(e)}"
        )

