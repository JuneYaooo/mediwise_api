"""
患者对话聊天接口 - 基于 patient_id 的多轮对话
使用 bus_patient_conversations 和 bus_conversation_messages 表

此接口支持：
1. 普通对话 - 根据用户问题和患者上下文回答
2. 患者数据更新 - 上传新文件或明确要求更新患者信息时，自动调用 PatientDataCrew 更新结构化数据

通过意图识别自动判断用户需求，无需单独调用不同接口。
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
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
from src.utils.logger import BeijingLogger

# 初始化 logger
logger = BeijingLogger().get_logger()


# ============================================================================
# 意图识别相关 - 使用大模型识别
# ============================================================================

async def detect_intent_with_llm(
    message: str, 
    files: List[Dict] = None,
    patient_context: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    使用大模型进行意图识别
    
    意图类型:
    - update_data: 用户要更新患者数据（上传文件、补充信息、修改记录等）
    - chat: 普通对话（咨询问题、询问建议等）
    
    返回:
        {
            "intent": "update_data" | "chat",
            "reason": str,
            "confidence": float
        }
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage, SystemMessage
    
    try:
        # 如果有文件上传，直接判定为更新数据（不需要调用LLM）
        if files and len(files) > 0:
            return {
                "intent": "update_data",
                "reason": f"用户上传了 {len(files)} 个文件，需要提取并更新患者数据",
                "confidence": 1.0
            }
        
        # 使用大模型进行意图识别
        model = ChatOpenAI(
            model=os.getenv('GENERAL_CHAT_MODEL_NAME', 'deepseek-chat'),
            api_key=os.getenv('GENERAL_CHAT_API_KEY'),
            base_url=os.getenv('GENERAL_CHAT_BASE_URL'),
            temperature=0.1,  # 低温度以获得更一致的结果
            timeout=30
        )
        
        # 构建患者上下文信息
        patient_info_str = ""
        if patient_context:
            patient_info = patient_context.get("patient_info") or {}
            if patient_info:
                patient_info_str = f"当前患者: {patient_info.get('name', '未知')}"
        
        system_prompt = """你是一个医疗AI助手的意图识别模块。你需要判断用户消息的意图类型。

意图类型只有两种：
1. **update_data** - 用户想要更新/补充/修改患者数据
   - 例如：要录入新的检查报告、补充病历信息、更新诊断结果、添加用药记录等
   - 关键特征：涉及到"录入"、"补充"、"更新"、"添加"、"修改"患者的医疗数据

2. **chat** - 用户想要咨询/对话/提问
   - 例如：询问治疗建议、咨询病情分析、请求诊断意见、问关于患者的问题等
   - 关键特征：用户在询问、请求分析、寻求建议

请严格按照以下JSON格式回复（不要输出其他内容）：
{"intent": "update_data或chat", "reason": "简短说明判断理由", "confidence": 0.0到1.0之间的置信度}"""

        user_prompt = f"""{patient_info_str}

用户消息：{message}

请判断用户意图："""

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]
        
        response = await model.ainvoke(messages)
        response_text = response.content.strip()
        
        # 解析JSON响应
        try:
            # 尝试直接解析
            result = json.loads(response_text)
        except json.JSONDecodeError:
            # 尝试提取JSON部分
            import re
            json_match = re.search(r'\{[^}]+\}', response_text)
            if json_match:
                result = json.loads(json_match.group())
            else:
                # 解析失败，默认为chat
                logger.warning(f"意图识别响应解析失败: {response_text}")
                return {
                    "intent": "chat",
                    "reason": "意图识别响应解析失败，默认为对话",
                    "confidence": 0.5
                }
        
        # 验证意图类型
        intent = result.get("intent", "chat")
        if intent not in ["update_data", "chat"]:
            intent = "chat"
        
        return {
            "intent": intent,
            "reason": result.get("reason", ""),
            "confidence": float(result.get("confidence", 0.8))
        }
        
    except Exception as e:
        logger.error(f"意图识别失败: {str(e)}")
        # 出错时默认为chat
        return {
            "intent": "chat",
            "reason": f"意图识别出错，默认为对话: {str(e)}",
            "confidence": 0.5
        }


def detect_intent_sync(message: str, files: List[Dict] = None) -> Dict[str, Any]:
    """
    同步版本的意图识别（用于不支持异步的场景）
    简单规则判断作为后备
    """
    # 如果有文件上传，直接判定为更新数据
    if files and len(files) > 0:
        return {
            "intent": "update_data",
            "reason": f"用户上传了 {len(files)} 个文件",
            "confidence": 1.0
        }
    
    # 默认为chat
    return {
        "intent": "chat",
        "reason": "默认为对话模式",
        "confidence": 0.5
    }

router = APIRouter()

# 全局字典存储任务状态（生产环境应使用Redis或数据库）
chat_task_status_store = {}

# 全局字典存储后台任务锁（防止重复执行）
chat_task_locks = {}


# ============================================================================
# Schema 定义
# ============================================================================

from pydantic import BaseModel


class PatientChatRequest(BaseModel):
    """患者对话请求"""
    message: Optional[str] = None
    files: Optional[List[Dict[str, Any]]] = None
    conversation_id: Optional[str] = None  # 可选，指定继续哪个会话


class PatientConversationResponse(BaseModel):
    """患者会话响应"""
    id: str
    patient_id: str
    session_id: Optional[str] = None
    title: Optional[str] = None
    conversation_type: Optional[str] = None
    status: Optional[str] = None
    created_at: str
    updated_at: str
    
    class Config:
        from_attributes = True


class ConversationMessageResponse(BaseModel):
    """会话消息响应"""
    id: str
    conversation_id: str
    message_id: Optional[str] = None
    role: str
    content: Optional[str] = None
    type: Optional[str] = None
    agent_name: Optional[str] = None
    sequence_number: Optional[int] = None
    created_at: str
    
    class Config:
        from_attributes = True


# ============================================================================
# 辅助函数
# ============================================================================

def get_or_create_conversation(
    db: Session,
    patient_id: str,
    user_id: str,
    conversation_id: Optional[str] = None,
    title: Optional[str] = None
) -> PatientConversation:
    """获取或创建患者会话"""
    
    # 如果指定了 conversation_id，尝试获取现有会话
    if conversation_id:
        conversation = db.query(PatientConversation).filter(
            PatientConversation.id == conversation_id,
            PatientConversation.patient_id == patient_id
        ).first()
        
        if conversation:
            logger.info(f"使用现有会话: {conversation_id}")
            return conversation
        else:
            logger.warning(f"指定的会话不存在: {conversation_id}，将创建新会话")
    
    # 创建新会话
    session_id = f"chat_{uuid.uuid4()}"
    conversation_title = title or f"对话 - {get_beijing_now_naive().strftime('%Y-%m-%d %H:%M')}"
    
    conversation = BusPatientHelper.create_conversation(
        db=db,
        patient_id=patient_id,
        user_id=user_id,
        title=conversation_title,
        session_id=session_id,
        conversation_type="chat"
    )
    db.commit()
    
    logger.info(f"创建新会话: {conversation.id}")
    return conversation


def save_message(
    db: Session,
    conversation_id: str,
    role: str,
    content: str,
    message_type: str = "text",
    parent_id: Optional[str] = None,
    agent_name: Optional[str] = None,
    tool_outputs: Optional[List[Dict]] = None,
    status_data: Optional[Dict] = None
) -> ConversationMessage:
    """保存消息到 bus_conversation_messages 表"""
    
    # 获取下一个序列号
    last_message = db.query(ConversationMessage).filter(
        ConversationMessage.conversation_id == conversation_id
    ).order_by(ConversationMessage.sequence_number.desc()).first()
    
    next_sequence = 1
    if last_message and last_message.sequence_number:
        next_sequence = last_message.sequence_number + 1
    
    current_time = get_beijing_now_naive()
    message_id = f"msg_{uuid.uuid4().hex[:12]}_{int(current_time.timestamp())}"
    
    message = ConversationMessage(
        id=str(uuid.uuid4()),
        conversation_id=conversation_id,
        message_id=message_id,
        role=role,
        content=content,
        type=message_type,
        parent_id=parent_id,
        agent_name=agent_name,
        sequence_number=next_sequence,
        tooloutputs=tool_outputs or [],
        statusdata=status_data or {},
        created_at=current_time,
        updated_at=current_time
    )
    
    db.add(message)
    db.flush()
    
    logger.debug(f"保存消息: {message_id}, role={role}, type={message_type}")
    return message


def get_conversation_history(
    db: Session,
    conversation_id: str,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """获取会话历史消息"""
    
    messages = db.query(ConversationMessage).filter(
        ConversationMessage.conversation_id == conversation_id
    ).order_by(ConversationMessage.sequence_number.asc()).limit(limit).all()
    
    history = []
    for msg in messages:
        # 只包含用户和助手的文本消息
        if msg.role in ["user", "assistant"] and msg.content:
            history.append({
                "role": msg.role,
                "content": msg.content
            })
    
    return history


def get_patient_context(
    db: Session,
    patient_id: str
) -> Dict[str, Any]:
    """获取患者上下文信息（用于对话）"""
    
    context = {
        "patient_info": None,
        "patient_timeline": None,
        "recent_files": []
    }
    
    # 获取患者基本信息
    patient = db.query(Patient).filter(
        Patient.patient_id == patient_id,
        Patient.is_deleted == False
    ).first()
    
    if patient:
        context["patient_info"] = {
            "name": patient.name,
            "gender": patient.gender,
            "phone": patient.phone,
            "allergies": patient.allergies,
            "medical_history": patient.medical_history
        }
    
    # 获取最新的患者时间轴数据
    patient_detail = PatientDetailHelper.get_latest_patient_detail_by_patient_id(db, patient_id)
    if patient_detail:
        context["patient_timeline"] = PatientDetailHelper.get_patient_timeline(patient_detail)
    
    return context


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
        yield f"data: {json.dumps({'task_id': task_id, 'status': 'received', 'message': '消息已接收，正在处理...', 'progress': 0}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0)
        
        logger.info(f"[对话任务 {task_id}] 开始处理，patient_id={patient_id}, conversation_id={conversation_id}")
        
        # ========== 文件处理 ==========
        formatted_files = []
        uploaded_file_ids = []
        extracted_file_results = []
        raw_files_data = []  # 用于保存文件记录
        
        if files:
            progress_msg = {'status': 'processing', 'stage': 'file_processing', 'message': f'正在处理 {len(files)} 个文件', 'progress': 10}
            yield f"data: {json.dumps(progress_msg, ensure_ascii=False)}\n\n"
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
                        existing_ids = patient.raw_file_ids.split(",") if patient.raw_file_ids else []
                        all_file_ids = list(set(existing_ids + uploaded_file_ids))
                        patient.raw_file_ids = ",".join(filter(None, all_file_ids))
                        db.commit()
                        logger.info(f"[对话任务 {task_id}] 更新患者 raw_file_ids: 总共 {len(all_file_ids)} 个文件")
                except Exception as e:
                    logger.error(f"[对话任务 {task_id}] 更新患者 raw_file_ids 失败: {str(e)}")
            
            progress_msg = {'status': 'processing', 'stage': 'file_processing_completed', 'message': f'文件处理完成，已保存 {len(raw_files_data)} 个文件', 'progress': 25}
            yield f"data: {json.dumps(progress_msg, ensure_ascii=False)}\n\n"
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
            patient_context=patient_context
        )
        intent = intent_result["intent"]
        intent_reason = intent_result["reason"]
        intent_confidence = intent_result.get("confidence", 0.8)
        
        logger.info(f"[对话任务 {task_id}] 意图识别结果: {intent}, 置信度: {intent_confidence}, 原因: {intent_reason}")
        
        progress_msg = {
            'status': 'processing', 
            'stage': 'intent_detected', 
            'message': f'意图识别: {intent} (置信度: {intent_confidence:.0%})', 
            'intent': intent,
            'intent_reason': intent_reason,
            'intent_confidence': intent_confidence,
            'progress': 28
        }
        yield f"data: {json.dumps(progress_msg, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0)
        
        # ========== 根据意图分支处理 ==========
        if intent == "update_data":
            # 更新患者数据分支 - 调用 PatientDataCrew
            async for chunk in _process_update_data(
                task_id=task_id,
                patient_id=patient_id,
                conversation_id=conversation_id,
                message=message,
                files_to_pass=files_to_pass,
                user_id=user_id,
                patient_context=patient_context,
                db=db
            ):
                yield chunk
        else:
            # 普通对话分支 - 使用通用 LLM 回复
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
        
        yield f"data: {json.dumps(final_result, ensure_ascii=False)}\n\n"
        
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
        yield f"data: {json.dumps(error_msg, ensure_ascii=False)}\n\n"


async def _process_update_data(
    task_id: str,
    patient_id: str,
    conversation_id: str,
    message: str,
    files_to_pass: List[Dict],
    user_id: str,
    patient_context: Dict[str, Any],
    db: Session
):
    """
    处理更新患者数据的分支
    调用 PatientDataCrew 提取并更新结构化数据
    """
    from src.crews.patient_data_crew.patient_data_crew import PatientDataCrew
    
    progress_msg = {'status': 'processing', 'stage': 'data_extraction', 'message': '正在提取患者数据...', 'progress': 35}
    yield f"data: {json.dumps(progress_msg, ensure_ascii=False)}\n\n"
    
    try:
        # 获取现有患者数据
        existing_patient_data = {
            "patient_timeline": patient_context.get("patient_timeline") or {},
            "patient_journey": {},
            "mdt_simple_report": {}
        }
        
        # 获取更完整的现有数据
        patient_detail = PatientDetailHelper.get_latest_patient_detail_by_patient_id(db, patient_id)
        if patient_detail:
            existing_patient_data["patient_journey"] = PatientDetailHelper.get_patient_journey(patient_detail) or {}
            existing_patient_data["mdt_simple_report"] = PatientDetailHelper.get_mdt_simple_report(patient_detail) or {}
        
        # 初始化 PatientDataCrew
        patient_data_crew = PatientDataCrew()
        
        progress_msg = {'status': 'processing', 'stage': 'crew_processing', 'message': '正在分析文件并提取结构化数据（可能需要5-10分钟）...', 'progress': 40}
        yield f"data: {json.dumps(progress_msg, ensure_ascii=False)}\n\n"
        
        # 使用线程池执行同步的 crew 方法
        loop = asyncio.get_event_loop()
        
        def run_crew():
            return patient_data_crew.get_structured_patient_data(
                patient_info=message,
                patient_timeline=existing_patient_data.get("patient_timeline", {}),
                messages=[],  # 不需要历史消息
                files=files_to_pass,
                agent_session_id=conversation_id,
                existing_patient_data=existing_patient_data
            )
        
        with ThreadPoolExecutor() as executor:
            result = await loop.run_in_executor(executor, run_crew)
        
        if "error" in result:
            error_msg = {'status': 'error', 'stage': 'crew_error', 'message': f'数据提取失败: {result["error"]}'}
            yield f"data: {json.dumps(error_msg, ensure_ascii=False)}\n\n"
            return
        
        progress_msg = {'status': 'processing', 'stage': 'data_extracted', 'message': '数据提取完成，正在保存...', 'progress': 80}
        yield f"data: {json.dumps(progress_msg, ensure_ascii=False)}\n\n"
        
        # 保存结构化数据到数据库
        patient_timeline = result.get('full_structure_data', {})
        patient_journey = result.get('patient_journey', {})
        mdt_simple_report = result.get('mdt_simple_report', {})
        patient_content = result.get('patient_content', '')
        
        BusPatientHelper.save_structured_data(
            db=db,
            patient_id=patient_id,
            conversation_id=conversation_id,
            user_id=user_id,
            patient_timeline=patient_timeline,
            patient_journey=patient_journey,
            mdt_simple_report=mdt_simple_report,
            patient_full_content=patient_content
        )
        db.commit()
        
        logger.info(f"[对话任务 {task_id}] 结构化数据已保存到 bus_patient_structured_data")
        
        progress_msg = {'status': 'processing', 'stage': 'data_saved', 'message': '患者数据已更新', 'progress': 90}
        yield f"data: {json.dumps(progress_msg, ensure_ascii=False)}\n\n"
        
        # 生成确认消息
        confirmation_message = _generate_update_confirmation(patient_timeline, files_to_pass)
        
        # 保存助手回复
        save_message(
            db=db,
            conversation_id=conversation_id,
            role="assistant",
            content=confirmation_message,
            message_type="reply",
            agent_name="patient_data_processor"
        )
        db.commit()
        
        # 流式返回确认消息
        stream_msg = {
            'status': 'streaming',
            'stage': 'response',
            'content': confirmation_message,
            'progress': 95
        }
        yield f"data: {json.dumps(stream_msg, ensure_ascii=False)}\n\n"
        
        # 返回工具输出（结构化数据）
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
        yield f"data: {json.dumps(tool_output, ensure_ascii=False)}\n\n"
        
    except Exception as e:
        logger.error(f"[对话任务 {task_id}] 数据更新失败: {str(e)}")
        import traceback
        traceback.print_exc()
        
        error_msg = {'status': 'error', 'stage': 'update_error', 'message': f'数据更新失败: {str(e)}'}
        yield f"data: {json.dumps(error_msg, ensure_ascii=False)}\n\n"


def _generate_update_confirmation(patient_timeline: Dict, files: List[Dict]) -> str:
    """生成数据更新确认消息"""
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
    yield f"data: {json.dumps(progress_msg, ensure_ascii=False)}\n\n"
    
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
                yield f"data: {json.dumps(stream_msg, ensure_ascii=False)}\n\n"
        
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
        
        progress_msg = {'status': 'processing', 'stage': 'response_completed', 'message': '回复生成完成', 'progress': 95}
        yield f"data: {json.dumps(progress_msg, ensure_ascii=False)}\n\n"
        
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
        yield f"data: {json.dumps(stream_msg, ensure_ascii=False)}\n\n"
        
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
) -> Any:
    """
    患者对话接口 - 基于 patient_id 的多轮对话聊天
    
    功能：
    - 与指定患者进行多轮对话
    - 支持文本消息和文件上传
    - 流式返回 AI 回复
    - 自动保存对话历史到 bus_conversation_messages 表
    - 支持继续已有会话或创建新会话
    
    请求参数：
        - message: 用户消息文本（可选）
        - files: 文件列表（可选，每个文件需包含 file_name、file_content(base64)）
        - conversation_id: 会话ID（可选，不传则创建新会话）
        - 注意：message 和 files 至少需要提供一个
    
    返回：
        流式响应（Server-Sent Events 格式）
    """
    try:
        # 1. 获取请求参数
        message = request.get("message", "").strip()
        files = request.get("files", [])
        conversation_id = request.get("conversation_id")
        
        # 2. 验证输入
        if not message and not files:
            raise HTTPException(
                status_code=400,
                detail="message 和 files 至少需要提供一个"
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
        
        # 使用固定用户ID（暂无认证）
        user_id = "system_user"
        
        # 5. 获取或创建会话
        conversation = get_or_create_conversation(
            db=db,
            patient_id=patient_id,
            user_id=user_id,
            conversation_id=conversation_id,
            title=message[:30] + "..." if message and len(message) > 30 else message
        )
        conversation_id = conversation.id
        
        # 6. 保存用户消息
        user_msg = save_message(
            db=db,
            conversation_id=conversation_id,
            role="user",
            content=message,
            message_type="text"
        )
        db.commit()
        
        # 7. 获取会话历史
        conversation_history = get_conversation_history(db, conversation_id)
        
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

