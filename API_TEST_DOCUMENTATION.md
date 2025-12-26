# MediWise API 接口文档

**版本**: 1.0.0
**Base URL**: `http://182.254.240.153:9527`
**本地测试**: `http://localhost:9527`
**认证方式**: 暂无需认证

---

## 目录

- [0. 基础接口](#0-基础接口)
  - [0.1 根路径](#01-根路径)
  - [0.2 健康检查](#02-健康检查)
- [1. 患者数据处理接口](#1-患者数据处理接口)
  - [1.1 混合智能处理](#11-混合智能处理)
  - [1.2 查询任务状态](#12-查询任务状态)
- [2. 患者对话更新接口](#2-患者对话更新接口)
  - [2.1 对话式患者信息更新](#21-对话式患者信息更新)
- [3. 患者多轮对话接口](#3-患者多轮对话接口)
  - [3.1 与患者对话聊天](#31-与患者对话聊天)
  - [3.2 获取患者聊天列表](#32-获取患者聊天列表)
  - [3.3 获取聊天消息记录](#33-获取聊天消息记录)
  - [3.4 查询对话任务状态](#34-查询对话任务状态)
  - [3.5 删除聊天](#35-删除聊天)
- [4. 患者 PPT 生成接口](#4-患者-ppt-生成接口)
  - [4.1 生成患者 PPT](#41-生成患者-ppt)
  - [4.2 获取患者 PPT 数据](#42-获取患者-ppt-数据)

---

## 0. 基础接口

### 0.1 根路径

**接口**: `GET /`

**功能说明**:
- 返回API服务的基本信息
- 列出所有可用的端点

**请求方式**: `GET`

**请求示例**:

```bash
curl http://localhost:9527/
```

**响应示例**:

```json
{
  "message": "MediWise API Service",
  "version": "1.0.0",
  "endpoints": {
    "patient_data_processing": "/api/patient_data/process_patient_data_smart",
    "patient_data_task_status": "/api/patient_data/task_status/{task_id}",
    "patient_chat": "/api/patients/{patient_id}/chat",
    "patient_ppt_generate": "/api/patients/{patient_id}/generate_ppt",
    "patient_ppt_data": "/api/patients/{patient_id}/ppt_data"
  }
}
```

**HTTP 状态码**:
- `200`: 成功

---

### 0.2 健康检查

**接口**: `GET /health`

**功能说明**:
- 用于检查API服务是否正常运行
- 适用于负载均衡器和监控系统

**请求方式**: `GET`

**请求示例**:

```bash
curl http://localhost:9527/health
```

**响应示例**:

```json
{
  "status": "healthy"
}
```

**HTTP 状态码**:
- `200`: 服务正常

---

## 1. 患者数据处理接口

### 1.1 患者首次数据处理

**接口**: `POST /api/patient_data/process_patient_data_smart`

**功能说明**:
- 创建新患者并处理其病历文件
- 提取结构化数据（患者时间轴、诊疗历程、MDT报告等）
- 支持流式响应（Server-Sent Events），实时返回处理进度
- 支持客户端断开后后台继续执行
- 生成 `patient_id` 和 `conversation_id`，用于后续操作

**请求方式**: `POST`

**Content-Type**: `application/json`

**请求参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| patient_description | string | 否 | 患者说明文本，描述患者基本情况 |
| consultation_purpose | string | 否 | 会诊目的，说明本次处理的目标 |
| files | array | 否 | 文件列表 |
| files[].file_name | string | 是 | 文件名（含扩展名） |
| files[].file_content | string | 是 | 文件内容（Base64 编码） |

**注意**:
- `patient_description` 和 `files` 至少需要提供一个
- 此接口仅用于创建新患者
- 如需更新现有患者数据，请使用 `POST /api/patients/{patient_id}/chat` 接口

**请求示例**:

```json
{
  "patient_description": "患者李云山的完整病例资料，包含多次检查报告和影像资料",
  "consultation_purpose": "多学科会诊，制定综合治疗方案，评估预后情况",
  "files": [
    {
      "file_name": "检查报告.pdf",
      "file_content": "JVBERi0xLjQKJeLjz9MKMSAwIG9iago8PC9UeXBlL0NhdGFsb..."
    },
    {
      "file_name": "影像资料.jpg",
      "file_content": "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJ..."
    }
  ]
}
```

**响应格式**: `text/event-stream` (Server-Sent Events)

**流式响应示例**:

```
data: {"task_id": "uuid-xxx-xxx", "status": "received", "message": "✅ 保存成功，系统会在后台进行自动解析并添加到患者列表中，预计10~20分钟，您可以先关闭对话框，耐心等待。", "progress": 0}

data: {"status": "processing", "stage": "file_upload", "message": "正在上传文件 1/2: 检查报告.pdf", "progress": 10, "file_info": {"current": 1, "total": 2, "file_name": "检查报告.pdf"}}

data: {"status": "processing", "stage": "file_upload", "message": "正在上传文件 2/2: 影像资料.jpg", "progress": 20, "file_info": {"current": 2, "total": 2, "file_name": "影像资料.jpg"}}

data: {"status": "processing", "stage": "file_processing_completed", "message": "文件处理完成，共提取 2 个文件", "progress": 25}

data: {"status": "processing", "stage": "patient_data_structuring", "message": "正在进行患者数据结构化处理", "progress": 30}

data: {"status": "completed", "message": "患者数据处理完成", "progress": 100, "duration": 123.45, "is_update": false, "result": {...}}
```

**完成时的 result 字段**:

```json
{
  "status": "completed",
  "message": "患者数据处理完成",
  "progress": 100,
  "duration": 123.45,
  "is_update": false,
  "result": {
    "patient_id": "患者唯一ID (UUID格式)",
    "conversation_id": "会话ID",
    "uploaded_files_count": 2,
    "uploaded_file_ids": ["file_id_1", "file_id_2"],
    "patient_timeline": {
      "patient_info": {
        "basic": {
          "name": "李云山",
          "age": "65岁",
          "gender": "男",
          "id_number": "...",
          "contact": "..."
        },
        "medical_history": {...},
        "family_history": {...}
      },
      "events": [
        {
          "date": "2024-01-15",
          "type": "检查",
          "description": "...",
          "details": {...}
        }
      ]
    },
    "patient_journey": {
      "diagnosis_path": [...],
      "treatment_timeline": [...]
    },
    "mdt_simple_report": {
      "summary": "...",
      "recommendations": [...]
    },
    "patient_full_content": "患者完整原始内容文本"
  }
}
```

**字段说明**:
- `is_update`: `false` 表示创建新患者，`true` 表示更新现有患者
- `message`: 创建模式为 "患者数据处理完成"，更新模式为 "患者数据更新完成"
- `patient_id`: 患者唯一标识符（UUID格式），用于后续PPT生成
- `conversation_id`: 本次处理的会话ID
- `patient_timeline`: 结构化的患者时间轴数据（包含基本信息、病史、事件等）
- `patient_journey`: 诊疗历程数据
- `mdt_simple_report`: MDT简报数据
- `patient_full_content`: 患者完整原始内容（合并所有文本和文件内容）

**错误响应**:

```json
{
  "status": "error",
  "message": "处理失败: 具体错误信息",
  "error": "错误详情"
}
```

**HTTP 状态码**:
- `200`: 成功建立流式连接
- `400`: 请求参数错误
- `500`: 服务器内部错误

**使用说明**:
1. **流式处理**：接口采用SSE (Server-Sent Events) 流式返回，实时推送处理进度
2. **断线续传**：客户端可以中途断开连接，后台任务会自动继续执行
3. **任务ID**：第一条消息中包含 `task_id`，客户端应保存此ID用于后续状态查询
4. **状态查询**：断开后可通过 `GET /api/patient_data/task_status/{task_id}` 查询任务状态
5. **更新模式**：提供 `patient_id` 时为更新模式，会合并现有数据；不提供时为创建模式
6. **文件上传**：文件内容需要Base64编码，系统会自动提取文件信息并存储
7. **数据提取**：系统会自动从结构化数据中提取患者姓名、年龄、性别等基本信息
8. **超时时间**：建议设置较长的请求超时时间（10-20分钟），或使用客户端断线续传功能

---

### 1.2 查询任务状态

**接口**: `GET /api/patient_data/task_status/{task_id}`

**功能说明**:
- 查询后台任务的执行状态和进度
- 获取已完成任务的结果数据

**请求方式**: `GET`

**路径参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| task_id | string | 是 | 任务ID（从流式接口返回） |

**请求示例**:

```bash
GET /api/patient_data/task_status/uuid-xxx-xxx
```

**响应示例**:

**任务已接收（初始状态）**:
```json
{
  "status": "pending",
  "progress": 0,
  "message": "任务已创建",
  "start_time": 1703145623.456
}
```

**处理中（文件上传）**:
```json
{
  "status": "processing",
  "stage": "file_upload",
  "progress": 15,
  "message": "正在上传文件 2/3: 影像资料.jpg",
  "file_info": {
    "current": 2,
    "total": 3,
    "file_name": "影像资料.jpg"
  }
}
```

**处理中（数据结构化）**:
```json
{
  "status": "processing",
  "stage": "patient_data_structuring",
  "progress": 45,
  "message": "正在进行患者数据结构化处理"
}
```

**已完成**:
```json
{
  "status": "completed",
  "progress": 100,
  "message": "患者数据处理完成",
  "duration": 123.45,
  "is_update": false,
  "result": {
    "patient_id": "patient_uuid_xxx",
    "conversation_id": "conv_uuid_xxx",
    "uploaded_files_count": 3,
    "uploaded_file_ids": ["file_1", "file_2", "file_3"],
    "patient_timeline": {
      "patient_info": {...},
      "events": [...]
    },
    "patient_journey": {...},
    "mdt_simple_report": {...},
    "patient_full_content": "..."
  }
}
```

**失败**:
```json
{
  "status": "error",
  "message": "处理失败: 文件解析错误",
  "error": "具体错误信息",
  "duration": 10.5
}
```

**任务不存在**:
```json
{
  "detail": "任务不存在"
}
```

**HTTP 状态码**:
- `200`: 成功获取任务状态
- `404`: 任务不存在

---

## 2. 患者对话更新接口（已合并）

> ⚠️ **注意**: 此功能已合并到 **[3. 患者多轮对话接口](#3-患者多轮对话接口统一入口)** 中。
> 
> 现在使用统一的 `POST /api/patients/{patient_id}/chat` 接口，系统会自动识别用户意图：
> - 上传文件或要求更新数据 → 自动调用 `PatientDataCrew` 更新结构化数据
> - 普通对话问题 → 直接回答用户问题
> 
> **不再需要单独调用数据更新接口。**

### 2.1 对话式患者信息更新（已合并到多轮对话接口）

请参考 **[3.1 与患者对话聊天](#31-与患者对话聊天)**

当您在对话中：
- 上传文件（CT报告、检验单等）
- 或消息中包含"更新"、"修改"、"添加"等关键词

系统会自动识别为"数据更新"意图，并执行以下操作：
1. 提取文件中的结构化数据
2. 更新患者时间轴（`bus_patient_structured_data`）
3. 保存对话记录（`bus_conversation_messages`）
4. 返回更新确认和结构化数据

**示例请求**（上传新报告并更新数据）:

```json
{
  "message": "补充最新的复查CT报告",
  "files": [
    {
      "file_name": "复查CT.pdf",
      "file_content": "JVBERi0xLjQKJeLjz9MKMSAwIG9iago8PC9UeXBlL0NhdGFsb..."
    }
  ]
}
```

**响应中会包含意图识别结果和处理进度**:

```
data: {"status": "processing", "stage": "intent_detected", "message": "意图识别: update_data (置信度: 95%)", "intent": "update_data", "intent_confidence": 0.95, "progress": 28}

data: {"status": "processing", "stage": "data_extraction", "message": "正在提取患者数据...", "progress": 35}

data: {"status": "processing", "stage": "crew_processing", "message": "正在分析文件并提取结构化数据...", "progress": 40}

data: {"status": "processing", "stage": "data_saved", "message": "患者数据已更新", "progress": 90}

data: {"status": "streaming", "stage": "response", "content": "✅ **患者数据更新成功！**\n- 已处理 1 个文件\n- 时间轴包含 5 条记录", "progress": 95}

data: {"status": "tool_output", "stage": "patient_timeline", "data": {"tool_name": "patient_timeline", "content": {...}}}
```
- `500`: 服务器内部错误

**使用说明**:
1. 此接口用于更新现有患者的数据
2. 每次调用会创建一个新的conversation记录
3. 自动合并现有数据和新数据
4. 支持纯文本对话、纯文件上传、或两者结合

---

## 3. 患者多轮对话接口（统一入口）

> **重要说明**: 此接口是患者对话和数据更新的统一入口，通过意图识别自动判断用户需求：
> - **普通对话**: 直接回答用户问题，结合患者上下文信息
> - **数据更新**: 当用户上传文件或明确要求更新数据时，自动调用 `PatientDataCrew` 提取并保存结构化数据

### 3.1 与患者对话聊天

**接口**: `POST /api/patients/{patient_id}/chat`

**功能说明**:
- 🔄 **智能意图识别**: 自动判断用户意图（对话 or 数据更新）
- 💬 **普通对话**: 基于患者信息回答问题
- 📄 **数据更新**: 上传文件时自动提取并更新患者结构化数据
- 📝 **自动保存**: 对话历史保存到 `bus_conversation_messages` 表
- 🔗 **多轮会话**: 支持继续已有会话或创建新会话
- 📊 **上下文感知**: 对话上下文包含患者的时间轴数据

**意图识别方式**:
- 🧠 **大模型智能识别**: 使用 LLM 分析用户消息的语义，判断用户意图
- 📄 **文件上传快速路径**: 如果用户上传了文件，直接识别为"数据更新"意图（无需调用LLM）
- 💬 **语义理解**: 
  - "帮我录入这份CT报告" → 数据更新
  - "患者的诊断结果是什么？" → 普通对话
  - "补充一下患者的用药信息" → 数据更新
  - "这个治疗方案有什么建议？" → 普通对话

**请求方式**: `POST`

**Content-Type**: `application/json`

**路径参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| patient_id | string | 是 | 患者ID（从首次处理接口返回） |

**请求参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| message | string | 否 | 用户消息文本 |
| files | array | 否 | 文件列表 |
| files[].file_name | string | 是 | 文件名（含扩展名） |
| files[].file_content | string | 是 | 文件内容（Base64 编码） |
| conversation_id | string | 否 | 会话ID（可选，不传则创建新会话，传入则继续该会话） |

**注意**:
- `message` 和 `files` 至少需要提供一个

**请求示例**:

```json
{
  "message": "这位患者的治疗方案有什么建议？",
  "conversation_id": "conv_uuid_xxx"
}
```

**响应格式**: `text/event-stream` (Server-Sent Events)

**流式响应示例**:

```
data: {"task_id": "task_uuid", "status": "received", "message": "消息已接收，正在处理...", "progress": 0}

data: {"status": "processing", "stage": "ai_processing", "message": "正在生成回复...", "progress": 30}

data: {"status": "streaming", "stage": "response", "content": "根据", "progress": 50}

data: {"status": "streaming", "stage": "response", "content": "患者的", "progress": 50}

data: {"status": "streaming", "stage": "response", "content": "病历资料...", "progress": 50}

data: {"status": "completed", "message": "对话处理完成", "progress": 100, "duration": 5.67, "result": {"patient_id": "xxx", "conversation_id": "xxx", "response_length": 256, "files_processed": 0}}
```

**HTTP 状态码**:
- `200`: 成功建立流式连接
- `400`: 请求参数错误
- `404`: 患者不存在
- `500`: 服务器内部错误

---

### 3.2 获取患者聊天列表

**接口**: `GET /api/patients/{patient_id}/chats`

**功能说明**:
- 获取指定患者的所有聊天列表
- 按更新时间倒序排列

**请求方式**: `GET`

**路径参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| patient_id | string | 是 | 患者ID |

**查询参数**:

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| skip | int | 否 | 0 | 跳过记录数 |
| limit | int | 否 | 50 | 返回记录数 |

**请求示例**:

```bash
GET /api/patients/patient_uuid_xxx/chats?skip=0&limit=20
```

**响应示例**:

```json
{
  "status": "success",
  "patient_id": "patient_uuid_xxx",
  "total": 3,
  "chats": [
    {
      "id": "chat_uuid_001",
      "session_id": "chat_xxx",
      "title": "治疗方案咨询...",
      "conversation_type": "chat",
      "status": "active",
      "created_at": "2025-01-15T10:30:00",
      "updated_at": "2025-01-15T11:00:00",
      "last_message_at": "2025-01-15T11:00:00"
    },
    {
      "id": "chat_uuid_002",
      "session_id": "chat_yyy",
      "title": "药物副作用咨询",
      "conversation_type": "chat",
      "status": "active",
      "created_at": "2025-01-14T14:00:00",
      "updated_at": "2025-01-14T14:30:00",
      "last_message_at": "2025-01-14T14:30:00"
    }
  ]
}
```

**HTTP 状态码**:
- `200`: 成功
- `404`: 患者不存在

---

### 3.3 获取聊天消息记录

**接口**: `GET /api/patients/{patient_id}/chats/{chat_id}/messages`

**功能说明**:
- 获取指定聊天的所有消息记录
- 按消息序号正序排列

**请求方式**: `GET`

**路径参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| patient_id | string | 是 | 患者ID |
| chat_id | string | 是 | 聊天ID |

**查询参数**:

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| skip | int | 否 | 0 | 跳过记录数 |
| limit | int | 否 | 100 | 返回记录数 |

**请求示例**:

```bash
GET /api/patients/patient_uuid_xxx/chats/chat_uuid_001/messages
```

**响应示例**:

```json
{
  "status": "success",
  "patient_id": "patient_uuid_xxx",
  "chat_id": "chat_uuid_001",
  "total": 4,
  "messages": [
    {
      "id": "msg_id_001",
      "message_id": "msg_xxx_001",
      "role": "user",
      "content": "这位患者的治疗方案有什么建议？",
      "type": "text",
      "agent_name": null,
      "parent_id": null,
      "sequence_number": 1,
      "tool_outputs": [],
      "status_data": {},
      "created_at": "2025-01-15T10:30:00"
    },
    {
      "id": "msg_id_002",
      "message_id": "msg_xxx_002",
      "role": "assistant",
      "content": "根据患者的病历资料，我建议以下治疗方案...",
      "type": "reply",
      "agent_name": "medical_assistant",
      "parent_id": "msg_xxx_001",
      "sequence_number": 2,
      "tool_outputs": [],
      "status_data": {},
      "created_at": "2025-01-15T10:30:15"
    }
  ]
}
```

**HTTP 状态码**:
- `200`: 成功
- `404`: 患者或聊天不存在

---

### 3.4 查询对话任务状态

**接口**: `GET /api/patients/chat_task_status/{task_id}`

**功能说明**:
- 查询对话任务的处理状态
- 用于客户端断开后重新获取任务进度

**请求方式**: `GET`

**路径参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| task_id | string | 是 | 任务ID（从对话接口返回的 task_id） |

**请求示例**:

```bash
GET /api/patients/chat_task_status/task_uuid_xxx
```

**响应示例**:

**处理中**:
```json
{
  "status": "processing",
  "progress": 50,
  "message": "正在生成回复...",
  "patient_id": "patient_uuid_xxx",
  "conversation_id": "conv_uuid_xxx"
}
```

**已完成**:
```json
{
  "status": "completed",
  "progress": 100,
  "message": "对话处理完成",
  "duration": 5.67,
  "result": {
    "patient_id": "patient_uuid_xxx",
    "conversation_id": "conv_uuid_xxx",
    "response_length": 256,
    "files_processed": 0
  }
}
```

**HTTP 状态码**:
- `200`: 成功获取任务状态
- `404`: 任务不存在

---

### 3.5 删除聊天

**接口**: `DELETE /api/patients/{patient_id}/chats/{chat_id}`

**功能说明**:
- 删除指定聊天及其所有消息记录

**请求方式**: `DELETE`

**路径参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| patient_id | string | 是 | 患者ID |
| chat_id | string | 是 | 聊天ID |

**请求示例**:

```bash
DELETE /api/patients/patient_uuid_xxx/chats/chat_uuid_001
```

**响应示例**:

```json
{
  "status": "success",
  "message": "聊天已删除",
  "chat_id": "chat_uuid_001"
}
```

**HTTP 状态码**:
- `200`: 成功删除
- `404`: 患者或聊天不存在
- `500`: 删除失败

---

## 4. 患者 PPT 生成接口

### 4.1 生成患者 PPT

**接口**: `POST /api/patients/{patient_id}/generate_ppt`

**功能说明**:
- 基于患者的所有结构化数据生成医疗会诊 PPT
- 自动聚合患者的时间轴、诊疗历程、MDT 报告等数据
- 从数据库获取所有关联的原始文件
- 生成包含患者完整病历的 PPT 文件

**请求方式**: `POST`

**路径参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| patient_id | string | 是 | 患者ID（从数据处理接口返回） |

**请求示例**:

```bash
POST /api/patients/patient_uuid_xxx/generate_ppt
```

**请求 Body**: 无需提供

**响应示例**:

**成功**:
```json
{
  "success": true,
  "ppt_url": "https://suvalue.com/ppt/xxx",
  "local_path": "/app/output/patient_uuid_xxx/medical_ppt.pptx",
  "file_uuid": "file_uuid_xxx",
  "qiniu_url": "https://cdn.qiniu.com/xxx.pptx",
  "message": "PPT生成成功",
  "patient_info": {
    "patient_id": "patient_uuid_xxx",
    "name": "李云山",
    "created_at": "2025-01-01 10:00:00"
  }
}
```

**失败**:
```json
{
  "success": false,
  "error": "患者时间轴数据为空，无法生成PPT",
  "detail": "请先处理患者数据"
}
```

**HTTP 状态码**:
- `200`: 成功生成 PPT
- `400`: 患者数据不完整，无法生成
- `404`: 患者不存在
- `500`: PPT 生成失败

**说明**:
- **处理时间**：本接口可能需要较长时间（通常 1-5 分钟），取决于患者数据量和文件数量
- **超时设置**：建议设置较长的请求超时时间（如 300-600 秒）
- **数据聚合**：接口会自动聚合患者的所有结构化数据（timeline、journey、mdt_report等）
- **文件获取**：从 `bus_patient.raw_file_ids` 字段获取所有关联的原始文件
- **数据库保存**：生成成功后会自动保存到数据库：
  - `bus_patient_ppt_data`: PPT流程数据（ppt_data、treatment_gantt_data）
  - `bus_patient_ppt_final`: PPT最终成果（URL、文件路径等）
- **URL类型**：返回的 URL 类型取决于系统配置：
  - `ppt_url`: Suvalue API 模式的 PPT 链接
  - `qiniu_url`: 本地生成 + 七牛云上传的链接
  - `local_path`: 本地文件路径
- **患者信息**：响应中包含患者基本信息（patient_info），便于前端展示

---

### 4.2 获取患者 PPT 数据

**接口**: `GET /api/patients/{patient_id}/ppt_data`

**功能说明**:
- 获取患者的 PPT 相关数据
- 用于查看 PPT 生成结果或检查数据完整性

**请求方式**: `GET`

**路径参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| patient_id | string | 是 | 患者ID |

**请求示例**:

```bash
GET /api/patients/patient_uuid_xxx/ppt_data
```

**响应示例**:

```json
{
  "success": true,
  "patient_id": "patient_uuid_xxx",
  "patient_info": {
    "name": "李云山",
    "gender": "男",
    "birth_date": "1965-03-15"
  },
  "ppt_data": {...},
  "ppt_final": {
    "ppt_url": "https://suvalue.com/ppt/xxx",
    "generated_at": "2025-01-15T10:30:00"
  }
}
```

**HTTP 状态码**:
- `200`: 成功
- `404`: 患者或 PPT 数据不存在

---

## 5. 数据更新策略说明

### 5.1 通过chat接口更新患者数据

当使用 `POST /api/patients/{patient_id}/chat` 接口时，系统会自动更新患者的结构化数据。

#### 数据覆盖策略

**会被完全覆盖的数据**（存储在 `bus_patient_structured_data` 表）：

| 数据类型 | data_type | 字段 | 更新方式 |
|---------|-----------|------|---------|
| 患者时间轴 | `timeline` | `structuredcontent` | **完全覆盖**为AI重新生成的最新结构化数据 |
| 诊疗历程 | `journey` | `structuredcontent` | **完全覆盖**为AI重新生成的数据 |
| MDT简报 | `mdt_report` | `structuredcontent` | **完全覆盖**为AI重新生成的数据 |
| 患者完整内容 | - | `text_content` | **覆盖**为最新的合并文本内容 |

**会追加合并的数据**：

| 数据表 | 字段 | 更新方式 |
|--------|------|---------|
| `bus_patient_files` | 文件记录 | **追加**：新文件添加到表中，旧文件保留 |
| `bus_patient` | `raw_file_ids` | **合并去重**：新旧文件ID合并后去重 |

**会更新的基本信息**（存储在 `bus_patient` 表）：

| 字段 | 更新条件 |
|------|---------|
| `name` | 如果从新数据中提取到更准确的姓名（非"患者"默认值） |
| `gender` | 如果从新数据中提取到性别信息 |
| `birth_date` | 如果从新数据中提取到出生日期或年龄 |

#### 更新流程详解

```
1. 检测到 patient_id → 进入更新模式
   ↓
2. 获取现有患者的所有结构化数据 (patient_timeline, patient_journey 等)
   ↓
3. 处理新上传的文件 → 文件追加到 bus_patient_files
   ↓
4. AI 基于 [现有数据 + 新数据] 重新生成完整的结构化内容
   ↓
5. 覆盖更新 bus_patient_structured_data 表中的对应记录
   ↓
6. 更新 bus_patient 表的基本信息（如果提取到更准确的信息）
   ↓
7. 生成 AI 对话式确认消息（可选）
```

#### 重要注意事项

⚠️ **数据覆盖风险**：
- 更新操作会**完全覆盖** `bus_patient_structured_data` 表中对应 `conversation_id` 的结构化数据
- AI会基于旧数据和新数据**重新生成**完整的时间轴、诊疗历程等
- 虽然AI会尝试合并旧数据，但理论上可能丢失部分细节

✅ **数据保护措施**：
- 每次更新都会创建新的 `conversation_id` 记录本次操作
- 可以通过 `conversation_id` 追溯历史数据变更
- `bus_patient_structured_data` 表支持 `version` 字段进行版本控制
- 文件永远不会被删除，只会追加

💡 **最佳实践**：
- **增量更新**：建议每次只补充新的检查报告或文件，不要重复上传旧数据
- **数据验证**：更新后通过 `GET /api/patients/{patient_id}/ppt_data` 检查数据完整性
- **重要操作前备份**：如果担心数据丢失，可以先调用 `ppt_data` 接口备份现有数据

#### 示例场景

**场景1：补充新的检查报告**
```json
{
  "patient_id": "patient_abc123",
  "patient_description": "补充2025-01-20的复查CT报告",
  "files": [{"file_name": "复查CT.pdf", "file_content": "..."}]
}
```
- ✅ 新文件追加到文件列表
- ✅ AI会在现有时间轴基础上添加新的检查事件
- ✅ 旧的时间轴事件理论上会保留（但取决于AI生成）

**场景2：修正患者基本信息**
```json
{
  "patient_id": "patient_abc123",
  "patient_description": "患者姓名应为'张三'，年龄65岁，男性"
}
```
- ✅ `bus_patient` 表的 `name`、`gender` 会更新
- ✅ AI会基于新信息重新生成结构化数据

**场景3：大量补充历史病历**
```json
{
  "patient_id": "patient_abc123",
  "patient_description": "补充患者2020-2024年的完整病历",
  "files": [多个历史文件]
}
```
- ⚠️ 所有结构化数据会被重新生成
- ⚠️ 建议先备份现有数据
- ✅ 文件会全部保留

---

## 6. 数据库表结构说明

### 6.1 核心数据表

#### bus_patient（患者基本信息表）
```sql
-- 主要字段
patient_id VARCHAR(36) PRIMARY KEY  -- 患者唯一标识
name VARCHAR(255)                    -- 患者姓名
gender VARCHAR(10)                   -- 性别
birth_date TIMESTAMP                 -- 出生日期
raw_file_ids TEXT                    -- 文件ID列表（逗号分隔）
status VARCHAR(20)                   -- 状态
created_at TIMESTAMP
updated_at TIMESTAMP
is_deleted BOOLEAN
```

#### bus_patient_structured_data（结构化数据表）
```sql
-- 主要字段
id VARCHAR(36) PRIMARY KEY
patient_id VARCHAR(36)               -- 关联患者
conversation_id VARCHAR(36)          -- 关联会话（追溯数据来源）
data_type VARCHAR(20)                -- 数据类型：timeline/journey/mdt_report
structuredcontent JSON               -- 结构化内容（JSON格式）
text_content TEXT                    -- 完整文本内容
version INTEGER                      -- 版本号
parent_version_id VARCHAR(36)        -- 父版本ID
created_by VARCHAR(36)
created_at TIMESTAMP
updated_at TIMESTAMP
is_deleted BOOLEAN
```

**关键点**：
- 同一个 `patient_id` 可以有多个 `conversation_id` 的记录（历史版本）
- 每个 `conversation_id` 下有3条记录（timeline、journey、mdt_report）
- 更新时会覆盖最新 `conversation_id` 对应的记录

#### bus_patient_files（文件记录表）
```sql
-- 主要字段
id VARCHAR(36) PRIMARY KEY           -- 文件UUID
patient_id VARCHAR(36)               -- 关联患者
conversation_id VARCHAR(36)          -- 关联会话（追溯文件来源）
file_name VARCHAR(255)               -- 原始文件名
file_path VARCHAR(500)               -- 文件路径
file_url VARCHAR(500)                -- 文件访问URL
file_type VARCHAR(50)                -- 文件类型（pdf/image等）
file_size BIGINT                     -- 文件大小
source_type VARCHAR(30)              -- 来源类型（uploaded/extracted等）
parent_pdf_uuid VARCHAR(36)          -- 父PDF的UUID（如果是提取的图片）
created_at TIMESTAMP
is_deleted BOOLEAN
```

**关键点**：
- 文件只会追加，不会删除（除非手动标记 `is_deleted=true`）
- 支持文件溯源（通过 `parent_pdf_uuid` 追踪提取来源）

#### bus_patient_conversations（会话记录表）
```sql
-- 主要字段
id VARCHAR(36) PRIMARY KEY           -- 会话ID
patient_id VARCHAR(36)               -- 关联患者
user_id VARCHAR(36)                  -- 操作用户
title VARCHAR(500)                   -- 会话标题
session_id VARCHAR(100)              -- 会话标识
conversation_type VARCHAR(20)        -- 类型：extraction/update等
created_at TIMESTAMP
is_deleted BOOLEAN
```

**关键点**：
- 每次调用 `process_patient_data_smart` 都会创建新的 `conversation_id`
- 通过 `conversation_id` 可以追溯每次数据处理的历史

---

## 7. API 使用最佳实践

### 7.1 完整工作流程

**首次创建患者**：
```bash
# 步骤1: 上传患者数据
curl -X POST http://localhost:9527/api/patient_data/process_patient_data_smart \
  -H "Content-Type: application/json" \
  -d '{
    "patient_description": "患者李云山的完整病例资料",
    "files": [...]
  }'

# 步骤2: 获取 patient_id
# 从流式响应中提取: {"result": {"patient_id": "xxx"}}

# 步骤3: 生成 PPT
curl -X POST http://localhost:9527/api/patients/{patient_id}/generate_ppt
```

**更新患者数据**：
```bash
# 步骤1: 使用chat接口更新数据
curl -X POST http://localhost:9527/api/patients/{patient_id}/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "补充最新检查报告",
    "files": [...]
  }'

# 步骤2: 验证更新结果
curl http://localhost:9527/api/patients/{patient_id}/ppt_data

# 步骤3: 重新生成 PPT
curl -X POST http://localhost:9527/api/patients/{patient_id}/generate_ppt
```

### 7.2 错误处理建议

**超时处理**：
```javascript
// 使用断线续传
const response = await fetch('/api/patient_data/process_patient_data_smart', {
  method: 'POST',
  body: JSON.stringify(data),
  signal: AbortSignal.timeout(10000)  // 10秒后主动断开
});

// 从第一条消息提取 task_id
const firstLine = await reader.read();
const taskId = JSON.parse(firstLine.value).task_id;

// 定期轮询状态
const pollStatus = setInterval(async () => {
  const status = await fetch(`/api/patient_data/task_status/${taskId}`);
  const result = await status.json();

  if (result.status === 'completed') {
    clearInterval(pollStatus);
    handleSuccess(result.result);
  } else if (result.status === 'error') {
    clearInterval(pollStatus);
    handleError(result.error);
  }
}, 3000);  // 每3秒查询一次
```

**数据验证**：
```javascript
// 更新后验证数据完整性
async function validatePatientData(patientId) {
  const data = await fetch(`/api/patients/${patientId}/ppt_data`);
  const json = await data.json();

  // 检查关键字段
  if (!json.data.patient_timeline) {
    throw new Error('患者时间轴数据缺失');
  }

  if (!json.data.patient_timeline.patient_info) {
    throw new Error('患者基本信息缺失');
  }

  console.log('✅ 数据验证通过');
  return json.data;
}
```

---

## 8. 联系与支持

如有问题或建议，请联系开发团队。

**API版本**: 1.0.0
**最后更新**: 2025-01-25
**文档维护**: MediWise API Team

