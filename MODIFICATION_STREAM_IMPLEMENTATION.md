# 患者数据修改流式回答功能实现文档

## 📋 概述

为 `/api/patient_data/modify_patient_data` 接口添加了流式回答功能，当有 `patient_id` 时，修改完成后会生成大模型流式确认消息。

## 🎯 实现目标

参考 `/home/ubuntu/github/mediwise/app/agents/medical_graph_stream.py` 中的 `modify_patient_info` 函数（第295-563行），实现：

1. 当提供 `patient_id` 时，查询现有患者数据
2. 使用 `PatientInfoUpdateCrew` 进行数据修改
3. **修改完成后，生成流式确认消息**（这是本次实现的重点）

## ✅ 已完成的修改

### 1. 添加导入 (第9-10行)

```python
import os
import asyncio
```

### 2. 实现流式确认消息生成函数 (第32-114行)

新增 `generate_modification_confirmation_stream()` 函数：

```python
async def generate_modification_confirmation_stream(
    modification_request: str,
    result: dict,
    task_id: str,
    conversation_id: str
)
```

**功能特性：**
- 使用 `ChatOpenAI` 模型生成专业的确认消息
- 支持流式输出（`streaming=True`）
- 通过 `async for chunk in model.astream()` 逐块返回消息
- 包含错误处理和降级方案

**消息格式：**
```python
{
    'status': 'streaming_response',
    'stage': 'confirmation',
    'message': '确认消息内容',
    'is_chunk': True/False,
    'progress': 90
}
```

### 3. 修改 `smart_stream_patient_modification` 函数

#### 3.1 优化 writer_func (第2181-2191行)

**之前：**
```python
def writer_func(message):
    # 这里只记录日志，不做流式传输
    if message.get("type") == "status":
        logger.info(f"...")
```

**修改后：**
```python
crew_messages = []

def writer_func(message):
    """接收crew的输出消息并缓存"""
    crew_messages.append(message)
    # 记录日志
    if message.get("type") == "status":
        logger.info(f"...")
```

#### 3.2 添加流式确认消息生成 (第2354-2369行)

在数据库更新完成后、返回最终结果之前，添加：

```python
# ========== 生成流式确认消息 ==========
logger.info(f"[修改任务 {task_id}] 开始生成流式确认消息")

# 调用流式确认消息生成器
async for confirmation_msg in generate_modification_confirmation_stream(
    modification_request=modification_request,
    result=result,
    task_id=task_id,
    conversation_id=conversation_id
):
    # 流式传输确认消息
    yield f"data: {json.dumps(confirmation_msg, ensure_ascii=False)}\n\n"
    await asyncio.sleep(0)
    # 更新任务状态
    if confirmation_msg.get('progress'):
        task_status_store[task_id].update({'progress': confirmation_msg['progress']})
```

## 📊 数据流程

```
用户请求 (patient_id + modification_request)
    ↓
查询现有患者数据
    ↓
调用 PatientInfoUpdateCrew.task_async()
    ↓
更新数据库
    ↓
🌟 生成流式确认消息 (新增)
    ↓
返回最终结果
```

## 🧪 测试方法

### 准备工作

1. **查询可用的测试患者：**
   ```bash
   python3 check_test_patients.py
   ```

   输出示例：
   ```
   8. Patient ID: 8feb8a48-d100-4f46-aea4-4f1f5ad178ca
      姓名: 患者
      ✅ 有结构化数据（可用于测试修改接口）
      基本信息:
        - 姓名: 李云山
        - 年龄: 68岁
        - 性别: 男
   ```

2. **确保 API 服务运行中：**
   ```bash
   # 检查服务状态
   curl http://localhost:9527/health

   # 如果没有运行，启动服务
   cd /home/ubuntu/github/mediwise_api
   uvicorn main:app --host 0.0.0.0 --port 9527
   ```

### 运行测试

```bash
python3 test_modify_patient_stream.py <patient_id> '<modification_request>'
```

**示例：**
```bash
python3 test_modify_patient_stream.py \
  8feb8a48-d100-4f46-aea4-4f1f5ad178ca \
  '将患者的年龄修改为70岁，性别修改为女'
```

### 预期输出

```
================================================================================
测试患者数据修改流式接口
================================================================================

📤 发送请求到: http://localhost:9527/api/patient_data/modify_patient_data
📋 请求数据:
   - patient_id: 8feb8a48-d100-4f46-aea4-4f1f5ad178ca
   - modification_request: 将患者的年龄修改为70岁

⏳ 等待流式响应...
--------------------------------------------------------------------------------

🆔 Task ID: <uuid>

📍 阶段: patient_data_modification
   进度: 30% | 消息: 正在修改患者数据

📍 阶段: generating_response
   进度: 70% | 消息: 正在生成修改确认消息

📍 阶段: confirmation
💬 患者信息已成功修改！我已经将李云山先生的年龄从68岁更新为70岁。
💬
💬 您可以在患者详情页面查看更新后的信息。如果还需要进行其他修改或有其他问题，请随时告诉我。

✅ 流式确认消息完成

--------------------------------------------------------------------------------
✅ 患者数据修改完成!

⏱️  总耗时: 15.32 秒

📊 修改结果:
   - patient_id: 8feb8a48-d100-4f46-aea4-4f1f5ad178ca
   - conversation_id: <uuid>
   - 上传文件数: 0

📈 统计:
   - 总消息数: 12
   - 流式确认消息数: 5

================================================================================
✅ 测试完成
================================================================================

✅ 流式确认消息功能正常！(共5条流式消息)
```

## 🔍 关键特性

### 1. 流式传输

- 使用 Server-Sent Events (SSE) 格式
- 消息格式：`data: {json}\n\n`
- 支持实时显示生成过程

### 2. 进度追踪

流程进度分配：
- 0-30%: 文件处理和数据准备
- 30-70%: PatientInfoUpdateCrew 处理
- 70-90%: 生成流式确认消息
- 90-95%: 流式消息传输
- 95-100%: 保存最终结果

### 3. 错误处理

- 捕获 LLM 调用异常
- 提供降级方案（简单文本确认）
- 记录详细日志

## 📝 API 接口说明

### 请求

**端点：** `POST /api/patient_data/modify_patient_data`

**请求体：**
```json
{
  "patient_id": "8feb8a48-d100-4f46-aea4-4f1f5ad178ca",
  "modification_request": "将患者年龄修改为70岁",
  "files": []
}
```

### 响应

**Content-Type:** `text/event-stream`

**消息类型：**

1. **任务启动：**
   ```json
   {
     "task_id": "uuid",
     "status": "started",
     "message": "开始修改患者数据",
     "progress": 0
   }
   ```

2. **处理进度：**
   ```json
   {
     "status": "processing",
     "stage": "patient_data_modification",
     "message": "正在修改患者数据",
     "progress": 30
   }
   ```

3. **流式确认消息（新增）：**
   ```json
   {
     "status": "streaming_response",
     "stage": "confirmation",
     "message": "患者信息已成功修改...",
     "is_chunk": true,
     "progress": 90
   }
   ```

4. **完成消息：**
   ```json
   {
     "status": "completed",
     "message": "患者数据修改完成",
     "progress": 100,
     "duration": 15.32,
     "result": {
       "patient_id": "...",
       "conversation_id": "...",
       "patient_timeline": {...},
       "patient_journey": {...},
       "mdt_simple_report": {...}
     }
   }
   ```

## 🔗 参考实现

本实现参考了 `/home/ubuntu/github/mediwise/app/agents/medical_graph_stream.py` 中的以下函数：

1. **`modify_patient_info` (第296-477行)**
   - 处理患者信息修改的主流程
   - 调用 `PatientInfoUpdateCrew` 或 `PatientDataCrew`

2. **`generate_modification_confirmation` (第480-562行)**
   - 生成流式确认消息
   - 使用 `ChatOpenAI` 流式输出
   - 通过 `writer` 参数传递消息

## ⚙️ 环境变量

确保在 `.env` 文件中配置以下变量：

```env
GENERAL_CHAT_MODEL_NAME=Pro/deepseek-ai/DeepSeek-V3.2-Exp
GENERAL_CHAT_API_KEY=your_api_key
GENERAL_CHAT_BASE_URL=https://api.example.com/v1
```

## 🐛 故障排查

### 问题1：没有流式确认消息

**检查点：**
1. 确认 `GENERAL_CHAT_API_KEY` 已配置
2. 检查网络连接到 LLM API
3. 查看日志：`logs/<date>.log`

### 问题2：API连接失败

```bash
# 检查服务是否运行
curl http://localhost:9527/health

# 查看服务日志
tail -f logs/$(date +%Y-%m-%d).log
```

### 问题3：患者数据未修改

**可能原因：**
- patient_id 不存在
- 患者没有结构化数据
- 数据库连接问题

**解决方法：**
```bash
# 检查患者数据
python3 check_test_patients.py

# 如果没有结构化数据，先创建
# 使用 /api/patient_data/process_patient_data_smart 接口
```

## 📚 相关文件

- **主实现文件：** `/home/ubuntu/github/mediwise_api/app/routers/patient_data_processing.py`
- **测试脚本：** `/home/ubuntu/github/mediwise_api/test_modify_patient_stream.py`
- **查询工具：** `/home/ubuntu/github/mediwise_api/check_test_patients.py`
- **参考实现：** `/home/ubuntu/github/mediwise/app/agents/medical_graph_stream.py`

## 🎉 总结

通过本次实现，`/api/patient_data/modify_patient_data` 接口现在完整支持：

1. ✅ 基于 patient_id 的数据修改
2. ✅ 使用 PatientInfoUpdateCrew 进行智能更新
3. ✅ **流式生成确认消息（新功能）**
4. ✅ 完整的进度追踪
5. ✅ 错误处理和降级方案

与 `mediwise` 项目中的 `modify_patient_info` 功能保持一致！
