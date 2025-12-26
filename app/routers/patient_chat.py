"""
患者对话聊天接口 - 基于 patient_id 的多轮对话
使用 bus_patient_conversations 和 bus_conversation_messages 表

此接口区别于 patient_data_processing.py 中的数据处理接口：
- patient_data_processing.py: 用于首次创建患者和更新患者数据（结构化提取）
- patient_chat.py: 用于基于某个 patient_id 进行多轮对话聊天
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Any, List, Dict, Optional
import json
import asyncio
import time
import uuid

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
        
        # ========== 调用 Medical API 进行对话 ==========
        progress_msg = {'status': 'processing', 'stage': 'ai_processing', 'message': '正在生成回复...', 'progress': 30}
        yield f"data: {json.dumps(progress_msg, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0)
        
        try:
            from app.agents.medical_api import MedicalAPI, Message as MedicalMessage
            
            medical_api = MedicalAPI()
            
            # 构建消息列表
            messages = []
            for hist in conversation_history:
                messages.append(MedicalMessage(role=hist["role"], content=hist["content"]))
            
            # 添加当前用户消息
            user_message_obj = MedicalMessage(role="user", content=message)
            if files_to_pass:
                user_message_obj.files = files_to_pass
            messages.append(user_message_obj)
            
            # 获取患者时间轴作为上下文
            patient_timeline = patient_context.get("patient_timeline") or {}
            
            # 流式调用 medical_api
            response_stream = medical_api.create(
                messages=messages,
                user_id=user_id,
                session_id=conversation_id,
                stream=True,
                patient_timeline=patient_timeline
            )
            
            # 收集完整回复
            full_response = ""
            tool_outputs = []
            
            async for chunk in response_stream:
                # 处理不同类型的响应
                if hasattr(chunk, 'object'):
                    chunk_type = chunk.object if hasattr(chunk, 'object') else getattr(chunk, 'type', 'unknown')
                    
                    if chunk_type == 'chat.completion.chunk':
                        # 文本内容
                        if hasattr(chunk, 'choices') and chunk.choices:
                            delta = chunk.choices[0].delta
                            if hasattr(delta, 'content') and delta.content:
                                content = delta.content
                                full_response += content
                                
                                # 流式返回文本块
                                stream_msg = {
                                    'status': 'streaming',
                                    'stage': 'response',
                                    'content': content,
                                    'progress': 50
                                }
                                yield f"data: {json.dumps(stream_msg, ensure_ascii=False)}\n\n"
                                await asyncio.sleep(0)
                    
                    elif chunk_type in ['tool_output', 'status', 'thinking']:
                        # 工具输出或状态消息
                        status_msg = {
                            'status': 'processing',
                            'stage': chunk_type,
                            'data': chunk.dict() if hasattr(chunk, 'dict') else str(chunk),
                            'progress': 40
                        }
                        yield f"data: {json.dumps(status_msg, ensure_ascii=False)}\n\n"
                        await asyncio.sleep(0)
                        
                        if chunk_type == 'tool_output':
                            tool_outputs.append(chunk.dict() if hasattr(chunk, 'dict') else {'content': str(chunk)})
                else:
                    # 处理字典类型的响应
                    if isinstance(chunk, dict):
                        chunk_type = chunk.get('object') or chunk.get('type', 'unknown')
                        
                        if chunk_type == 'chat.completion.chunk':
                            choices = chunk.get('choices', [])
                            if choices:
                                delta = choices[0].get('delta', {})
                                content = delta.get('content', '')
                                if content:
                                    full_response += content
                                    
                                    stream_msg = {
                                        'status': 'streaming',
                                        'stage': 'response',
                                        'content': content,
                                        'progress': 50
                                    }
                                    yield f"data: {json.dumps(stream_msg, ensure_ascii=False)}\n\n"
                                    await asyncio.sleep(0)
                        
                        elif chunk_type in ['tool_output', 'status', 'thinking']:
                            status_msg = {
                                'status': 'processing',
                                'stage': chunk_type,
                                'data': chunk,
                                'progress': 40
                            }
                            yield f"data: {json.dumps(status_msg, ensure_ascii=False)}\n\n"
                            await asyncio.sleep(0)
                            
                            if chunk_type == 'tool_output':
                                tool_outputs.append(chunk)
            
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
                    agent_name="medical_assistant",
                    tool_outputs=tool_outputs if tool_outputs else None
                )
                db.commit()
                
                logger.info(f"[对话任务 {task_id}] 助手回复已保存，长度: {len(full_response)}")
            
            # 检查 tool_outputs 中是否有结构化数据更新
            if tool_outputs:
                for tool_output in tool_outputs:
                    try:
                        # 检查是否是患者数据更新
                        tool_data = tool_output if isinstance(tool_output, dict) else (tool_output.dict() if hasattr(tool_output, 'dict') else {})
                        tool_name = tool_data.get('tool_name', '') or tool_data.get('name', '')
                        tool_content = tool_data.get('content', {})
                        
                        # 如果是患者信息修改工具的输出
                        if tool_name in ['modify_patient_info', 'update_patient_data', 'patient_data_update']:
                            if isinstance(tool_content, str):
                                try:
                                    tool_content = json.loads(tool_content)
                                except:
                                    pass
                            
                            if isinstance(tool_content, dict):
                                # 提取更新的数据
                                updated_timeline = tool_content.get('patient_timeline') or tool_content.get('timeline')
                                updated_journey = tool_content.get('patient_journey') or tool_content.get('journey')
                                updated_mdt_report = tool_content.get('mdt_simple_report') or tool_content.get('mdt_report')
                                
                                if updated_timeline or updated_journey or updated_mdt_report:
                                    # 保存结构化数据更新
                                    BusPatientHelper.save_structured_data(
                                        db=db,
                                        patient_id=patient_id,
                                        conversation_id=conversation_id,
                                        user_id=user_id,
                                        patient_timeline=updated_timeline,
                                        patient_journey=updated_journey,
                                        mdt_simple_report=updated_mdt_report,
                                        patient_full_content=None
                                    )
                                    db.commit()
                                    logger.info(f"[对话任务 {task_id}] 已保存结构化数据更新到 bus_patient_structured_data")
                    except Exception as e:
                        logger.warning(f"[对话任务 {task_id}] 处理 tool_output 时出错: {str(e)}")
        
        except ImportError as e:
            # 如果没有 medical_api，使用简单的回复
            logger.warning(f"Medical API 不可用，使用模拟回复: {str(e)}")
            
            full_response = f"您好，我是医疗助手。您说：\"{message}\"。目前系统正在配置中，请稍后再试。"
            
            # 流式返回模拟回复
            for char in full_response:
                stream_msg = {
                    'status': 'streaming',
                    'stage': 'response',
                    'content': char,
                    'progress': 50
                }
                yield f"data: {json.dumps(stream_msg, ensure_ascii=False)}\n\n"
                await asyncio.sleep(0.02)
            
            # 保存助手回复
            save_message(
                db=db,
                conversation_id=conversation_id,
                role="assistant",
                content=full_response,
                message_type="reply"
            )
            db.commit()
        
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
            "message": "对话处理完成",
            "progress": 100,
            "duration": overall_duration,
            "result": {
                "patient_id": patient_id,
                "conversation_id": conversation_id,
                "response_length": len(full_response) if full_response else 0,
                "files_processed": len(uploaded_file_ids),
                "files_saved": len(raw_files_data)  # 保存到数据库的文件数
            }
        }
        
        yield f"data: {json.dumps(final_result, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0)
        
        chat_task_status_store[task_id] = final_result
        logger.info(f"[对话任务 {task_id}] 处理完成，耗时: {overall_duration:.2f}秒")
        
    except asyncio.CancelledError:
        logger.warning(f"[对话任务 {task_id}] 客户端断开连接")
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
        chat_task_status_store[task_id] = error_response


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

