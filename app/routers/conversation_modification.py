"""
对话修改路由 - 通过自然语言对话修改和查询对话内容
支持混合智能查询和异步后台执行
"""
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Any, Dict, Optional
import json
import time
import uuid
from datetime import datetime

from app.db.database import get_db, SessionLocal
from app.core.deps import get_current_user
from app.models.user import User as UserModel
from src.utils.logger import BeijingLogger

# 初始化 logger
logger = BeijingLogger().get_logger()

# 全局字典存储任务状态（生产环境应使用Redis或数据库）
modification_task_store = {}

router = APIRouter()


# ============================================================================
# 后台任务：异步处理对话修改请求
# ============================================================================

def process_conversation_modification_background(
    task_id: str,
    conversation_id: str,
    modification_request: str,
    user_id: str
):
    """
    后台任务：处理对话修改请求
    即使客户端断开连接，任务也会继续执行
    """
    from app.models.conversation import Conversation as ConversationModel, Message as MessageModel
    from app.agents.medical_api import MedicalAPI, Message as MedicalMessage

    # 创建新的数据库会话
    db = SessionLocal()

    try:
        # 更新任务状态为处理中
        modification_task_store[task_id] = {
            "status": "processing",
            "progress": 10,
            "message": "开始处理对话修改请求",
            "start_time": time.time(),
            "user_id": user_id
        }

        logger.info(f"[对话修改任务 {task_id}] 开始处理: conversation_id={conversation_id}")

        overall_start_time = time.time()

        # 1. 验证会话是否存在
        conversation = db.query(ConversationModel).filter(
            ConversationModel.id == conversation_id,
            ConversationModel.user_id == user_id
        ).first()

        if not conversation:
            raise Exception(f"会话不存在或无权限访问: {conversation_id}")

        modification_task_store[task_id].update({
            "progress": 20,
            "message": "正在获取会话历史"
        })

        # 2. 获取会话历史消息
        messages = db.query(MessageModel).filter(
            MessageModel.conversation_id == conversation_id
        ).order_by(MessageModel.sequence_number, MessageModel.created_at).all()

        # 构建会话历史
        conversation_history = []
        for msg in messages:
            if msg.role in ["user", "assistant"]:
                conversation_history.append(
                    MedicalMessage(role=msg.role, content=msg.content or "")
                )

        modification_task_store[task_id].update({
            "progress": 40,
            "message": f"已加载 {len(conversation_history)} 条历史消息，正在处理修改请求"
        })

        # 3. 添加用户的修改请求到会话历史
        conversation_history.append(
            MedicalMessage(role="user", content=modification_request)
        )

        # 4. 调用医疗AI API处理修改请求
        modification_task_store[task_id].update({
            "progress": 50,
            "message": "正在调用AI处理修改请求"
        })

        medical_api = MedicalAPI()

        # 构建系统提示，指导AI进行对话修改
        system_prompt = """你是一个专业的医疗对话助手。用户将向你提出对当前对话的修改或查询请求。
请根据对话历史和用户的请求，提供准确、专业的回答。

可能的请求类型包括：
1. 修改某条消息的内容
2. 删除某条消息
3. 添加新的信息到对话中
4. 查询对话中的特定信息
5. 总结对话内容
6. 重新组织对话结构

请仔细理解用户的意图，并提供清晰、有用的响应。"""

        # 插入系统提示到会话历史开头
        conversation_history.insert(0, MedicalMessage(role="system", content=system_prompt))

        # 调用API（非流式）
        response = medical_api.create(
            messages=conversation_history,
            user_id=user_id,
            session_id=conversation.session_id,
            stream=False
        )

        modification_task_store[task_id].update({
            "progress": 80,
            "message": "AI处理完成，正在保存结果"
        })

        # 5. 保存用户的修改请求消息
        from app.utils.datetime_utils import get_beijing_now_naive
        current_time = get_beijing_now_naive()

        # 获取最后一条消息的序列号
        last_message = db.query(MessageModel).filter(
            MessageModel.conversation_id == conversation_id
        ).order_by(MessageModel.sequence_number.desc()).first()

        next_sequence = 1
        if last_message and last_message.sequence_number:
            next_sequence = last_message.sequence_number + 1

        # 保存用户请求
        user_message = MessageModel(
            message_id=f"mod_req_{task_id}",
            conversation_id=conversation_id,
            role="user",
            content=modification_request,
            type="modification_request",
            sequence_number=next_sequence,
            created_at=current_time,
            updated_at=current_time
        )
        db.add(user_message)

        # 6. 保存AI的响应
        ai_response_content = response.get("content", "") if isinstance(response, dict) else str(response)

        assistant_message = MessageModel(
            message_id=f"mod_resp_{task_id}",
            conversation_id=conversation_id,
            role="assistant",
            content=ai_response_content,
            type="modification_response",
            parent_id=user_message.message_id,
            sequence_number=next_sequence + 1,
            created_at=current_time,
            updated_at=current_time
        )
        db.add(assistant_message)

        # 更新会话的updated_at时间戳
        conversation.updated_at = current_time
        db.add(conversation)

        db.commit()

        modification_task_store[task_id].update({
            "progress": 100,
            "message": "对话修改处理完成"
        })

        # 处理成功
        overall_duration = time.time() - overall_start_time
        modification_task_store[task_id] = {
            "status": "completed",
            "progress": 100,
            "message": "对话修改处理完成",
            "duration": overall_duration,
            "result": {
                "conversation_id": conversation_id,
                "user_message_id": user_message.message_id,
                "assistant_message_id": assistant_message.message_id,
                "modification_request": modification_request,
                "ai_response": ai_response_content
            }
        }

        logger.info(f"[对话修改任务 {task_id}] 处理完成，总耗时: {overall_duration:.2f} 秒")

    except Exception as e:
        logger.error(f"[对话修改任务 {task_id}] 处理异常: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

        modification_task_store[task_id] = {
            "status": "error",
            "message": f"处理失败: {str(e)}",
            "error": str(e),
            "duration": time.time() - overall_start_time if 'overall_start_time' in locals() else 0
        }
    finally:
        # 关闭数据库会话
        db.close()


# ============================================================================
# 流式接口：通过对话修改会话内容（支持SSE流式响应）
# ============================================================================

@router.post("/{conversation_id}/modify_conversation_stream")
async def modify_conversation_stream(
    conversation_id: str,
    request: Dict[str, Any],
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> Any:
    """
    通过自然语言对话修改会话内容（流式接口）

    支持的修改请求示例：
    - "帮我总结一下这个对话的主要内容"
    - "删除关于药物剂量的那条消息"
    - "修改患者年龄为45岁"
    - "添加患者的过敏史信息"
    - "查询对话中提到的所有检查项目"

    请求参数:
        - modification_request: 自然语言描述的修改请求（必填）

    响应格式: text/event-stream (Server-Sent Events)

    流式响应示例:
        data: {"task_id": "xxx", "status": "started", "progress": 0}
        data: {"status": "processing", "progress": 50, "message": "正在处理修改请求"}
        data: {"status": "completed", "progress": 100, "result": {...}}
    """
    from app.models.conversation import Conversation as ConversationModel, Message as MessageModel
    from app.agents.medical_api import MedicalAPI, Message as MedicalMessage

    try:
        # 1. 获取并验证修改请求
        modification_request = request.get("modification_request", "").strip()

        if not modification_request:
            raise HTTPException(
                status_code=400,
                detail="modification_request 不能为空"
            )

        # 2. 验证会话是否存在且用户有权限
        conversation = db.query(ConversationModel).filter(
            ConversationModel.id == conversation_id,
            ConversationModel.user_id == current_user.id
        ).first()

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail="会话不存在或无权限访问"
            )

        # 3. 生成任务ID
        task_id = str(uuid.uuid4())

        async def generate():
            """流式生成器"""
            try:
                # 发送任务开始事件
                yield f"data: {json.dumps({'task_id': task_id, 'status': 'started', 'progress': 0, 'message': '开始处理修改请求'})}\n\n"

                # 获取会话历史
                yield f"data: {json.dumps({'status': 'processing', 'progress': 20, 'message': '正在获取会话历史'})}\n\n"

                messages = db.query(MessageModel).filter(
                    MessageModel.conversation_id == conversation_id
                ).order_by(MessageModel.sequence_number, MessageModel.created_at).all()

                # 构建会话历史
                conversation_history = []
                for msg in messages:
                    if msg.role in ["user", "assistant"]:
                        conversation_history.append(
                            MedicalMessage(role=msg.role, content=msg.content or "")
                        )

                yield f"data: {json.dumps({'status': 'processing', 'progress': 40, 'message': f'已加载 {len(conversation_history)} 条历史消息'})}\n\n"

                # 添加用户的修改请求
                conversation_history.append(
                    MedicalMessage(role="user", content=modification_request)
                )

                # 构建系统提示
                system_prompt = """你是一个专业的医疗对话助手。用户将向你提出对当前对话的修改或查询请求。
请根据对话历史和用户的请求，提供准确、专业的回答。

可能的请求类型包括：
1. 修改某条消息的内容
2. 删除某条消息
3. 添加新的信息到对话中
4. 查询对话中的特定信息
5. 总结对话内容
6. 重新组织对话结构

请仔细理解用户的意图，并提供清晰、有用的响应。"""

                conversation_history.insert(0, MedicalMessage(role="system", content=system_prompt))

                yield f"data: {json.dumps({'status': 'processing', 'progress': 50, 'message': '正在调用AI处理修改请求'})}\n\n"

                # 调用医疗AI API
                medical_api = MedicalAPI()

                # 使用流式API
                response_stream = medical_api.create(
                    messages=conversation_history,
                    user_id=str(current_user.id),
                    session_id=conversation.session_id,
                    stream=True
                )

                # 收集AI响应内容
                ai_response_content = ""

                # 流式推送AI响应
                async for chunk in response_stream:
                    if isinstance(chunk, dict) and "content" in chunk:
                        content_delta = chunk.get("content", "")
                        ai_response_content += content_delta

                        yield f"data: {json.dumps({'status': 'streaming', 'progress': 70, 'content_delta': content_delta})}\n\n"

                yield f"data: {json.dumps({'status': 'processing', 'progress': 85, 'message': '正在保存结果'})}\n\n"

                # 保存到数据库
                from app.utils.datetime_utils import get_beijing_now_naive
                current_time = get_beijing_now_naive()

                # 获取最后一条消息的序列号
                last_message = db.query(MessageModel).filter(
                    MessageModel.conversation_id == conversation_id
                ).order_by(MessageModel.sequence_number.desc()).first()

                next_sequence = 1
                if last_message and last_message.sequence_number:
                    next_sequence = last_message.sequence_number + 1

                # 保存用户请求
                user_message = MessageModel(
                    message_id=f"mod_req_{task_id}",
                    conversation_id=conversation_id,
                    role="user",
                    content=modification_request,
                    type="modification_request",
                    sequence_number=next_sequence,
                    created_at=current_time,
                    updated_at=current_time
                )
                db.add(user_message)

                # 保存AI响应
                assistant_message = MessageModel(
                    message_id=f"mod_resp_{task_id}",
                    conversation_id=conversation_id,
                    role="assistant",
                    content=ai_response_content,
                    type="modification_response",
                    parent_id=user_message.message_id,
                    sequence_number=next_sequence + 1,
                    created_at=current_time,
                    updated_at=current_time
                )
                db.add(assistant_message)

                # 更新会话时间戳
                conversation.updated_at = current_time
                db.add(conversation)

                db.commit()

                # 发送完成事件
                result = {
                    "conversation_id": conversation_id,
                    "user_message_id": user_message.message_id,
                    "assistant_message_id": assistant_message.message_id,
                    "modification_request": modification_request,
                    "ai_response": ai_response_content
                }

                yield f"data: {json.dumps({'status': 'completed', 'progress': 100, 'message': '对话修改处理完成', 'result': result})}\n\n"

                logger.info(f"[对话修改流式] conversation_id={conversation_id}, task_id={task_id} 处理完成")

            except Exception as e:
                error_message = f"处理修改请求时出错: {str(e)}"
                logger.error(f"[对话修改流式] {error_message}")
                import traceback
                logger.error(traceback.format_exc())

                yield f"data: {json.dumps({'status': 'error', 'message': error_message, 'error': str(e)})}\n\n"

        # 返回流式响应
        return StreamingResponse(
            generate(),
            media_type="text/event-stream"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建对话修改流式任务失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"创建修改任务失败: {str(e)}"
        )


# ============================================================================
# 异步接口：后台执行对话修改任务（客户端断开也会继续执行）
# ============================================================================

@router.post("/{conversation_id}/modify_conversation_async")
async def modify_conversation_async(
    conversation_id: str,
    request: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> Any:
    """
    异步后台修改对话接口

    与流式接口不同，此接口会立即返回任务ID，即使客户端断开连接，后端也会继续处理。
    客户端可以通过任务ID轮询任务状态。

    请求参数:
        - modification_request: 自然语言描述的修改请求（必填）

    返回:
        {
            "task_id": "任务ID",
            "status": "pending",
            "message": "任务已创建，正在后台处理",
            "conversation_id": "会话ID"
        }
    """
    try:
        # 1. 获取并验证修改请求
        modification_request = request.get("modification_request", "").strip()

        if not modification_request:
            raise HTTPException(
                status_code=400,
                detail="modification_request 不能为空"
            )

        # 2. 验证会话是否存在且用户有权限
        from app.models.conversation import Conversation as ConversationModel

        conversation = db.query(ConversationModel).filter(
            ConversationModel.id == conversation_id,
            ConversationModel.user_id == current_user.id
        ).first()

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail="会话不存在或无权限访问"
            )

        # 3. 生成任务ID
        task_id = str(uuid.uuid4())

        # 4. 初始化任务状态
        modification_task_store[task_id] = {
            "status": "pending",
            "progress": 0,
            "message": "任务已创建，等待处理",
            "create_time": time.time(),
            "user_id": str(current_user.id),
            "conversation_id": conversation_id
        }

        # 5. 添加后台任务
        background_tasks.add_task(
            process_conversation_modification_background,
            task_id=task_id,
            conversation_id=conversation_id,
            modification_request=modification_request,
            user_id=str(current_user.id)
        )

        logger.info(f"[对话修改异步] 任务已创建: task_id={task_id}, conversation_id={conversation_id}")

        # 6. 返回任务ID
        return {
            "task_id": task_id,
            "status": "pending",
            "message": "任务已创建，正在后台处理",
            "conversation_id": conversation_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建对话修改异步任务失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"创建修改任务失败: {str(e)}"
        )


# ============================================================================
# 查询任务状态接口
# ============================================================================

@router.get("/modification_tasks/{task_id}")
async def get_modification_task_status(
    task_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> Any:
    """
    查询对话修改任务状态

    返回:
        {
            "task_id": "任务ID",
            "status": "pending | processing | completed | error",
            "progress": 0-100,
            "message": "状态描述",
            "result": {...},  # 仅在completed状态时返回
            "error": "错误信息",  # 仅在error状态时返回
            "duration": 123.45  # 任务执行时长（秒）
        }
    """
    try:
        # 1. 检查任务是否存在
        if task_id not in modification_task_store:
            raise HTTPException(
                status_code=404,
                detail=f"任务不存在: {task_id}"
            )

        # 2. 获取任务状态
        task_status = modification_task_store[task_id]

        # 3. 验证用户权限（只能查询自己的任务）
        if task_status.get("user_id") != str(current_user.id):
            raise HTTPException(
                status_code=403,
                detail="无权限访问该任务"
            )

        # 4. 构建返回数据
        response = {
            "task_id": task_id,
            "status": task_status.get("status"),
            "progress": task_status.get("progress", 0),
            "message": task_status.get("message", ""),
            "conversation_id": task_status.get("conversation_id")
        }

        # 添加可选字段
        if "result" in task_status:
            response["result"] = task_status["result"]

        if "error" in task_status:
            response["error"] = task_status["error"]

        if "duration" in task_status:
            response["duration"] = task_status["duration"]

        if "start_time" in task_status:
            # 计算运行时间
            running_time = time.time() - task_status["start_time"]
            response["running_time"] = running_time

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询任务状态失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"查询任务状态失败: {str(e)}"
        )


# ============================================================================
# 查询用户所有修改任务列表
# ============================================================================

@router.get("/modification_tasks")
async def list_modification_tasks(
    status: Optional[str] = None,
    limit: int = 50,
    current_user: UserModel = Depends(get_current_user),
) -> Any:
    """
    查询当前用户的所有对话修改任务

    参数:
        - status: 筛选任务状态（可选：pending, processing, completed, error）
        - limit: 返回数量限制（默认50）

    返回:
        {
            "total": 总数量,
            "tasks": [任务列表]
        }
    """
    try:
        user_id = str(current_user.id)

        # 筛选属于当前用户的任务
        user_tasks = []
        for task_id, task_data in modification_task_store.items():
            if task_data.get("user_id") == user_id:
                # 如果指定了状态筛选
                if status and task_data.get("status") != status:
                    continue

                task_info = {
                    "task_id": task_id,
                    "status": task_data.get("status"),
                    "progress": task_data.get("progress", 0),
                    "message": task_data.get("message", ""),
                    "conversation_id": task_data.get("conversation_id"),
                    "create_time": task_data.get("create_time")
                }

                if "duration" in task_data:
                    task_info["duration"] = task_data["duration"]

                if "start_time" in task_data:
                    running_time = time.time() - task_data["start_time"]
                    task_info["running_time"] = running_time

                user_tasks.append(task_info)

        # 按创建时间倒序排序
        user_tasks.sort(key=lambda x: x.get("create_time", 0), reverse=True)

        # 限制返回数量
        user_tasks = user_tasks[:limit]

        return {
            "total": len(user_tasks),
            "tasks": user_tasks
        }

    except Exception as e:
        logger.error(f"查询任务列表失败: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"查询任务列表失败: {str(e)}"
        )
