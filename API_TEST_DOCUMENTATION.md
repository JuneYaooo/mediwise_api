# MediWise API 接口文档

**版本**: 1.0.0
**Base URL**: `http://182.254.240.153:9527`
**本地测试**: `http://localhost:9527`
**认证方式**: 部分接口需要 JWT Token 鉴权（见下方说明）

---

## 认证说明

### 需要 Token 鉴权的接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/patients/{patient_id}/chat` | POST | 患者对话接口 |
| `/api/patients/{patient_id}/generate_ppt` | POST | 生成患者 PPT |

### 不需要鉴权的接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 根路径 |
| `/health` | GET | 健康检查 |
| `/api/patient_data/process_patient_data_smart` | POST | 患者首次数据处理（支持 Token 或 user_id） |
| `/api/patient_data/task_status/{task_id}` | GET | 查询任务状态 |
| `/api/patients/{patient_id}/ppt_data` | GET | 获取患者 PPT 数据 |

### JWT Token 格式

```
Authorization: Bearer <your_jwt_token>
```

### Token 配置

- 算法：HS256 或 HS512（对称加密）
- 密钥：由系统管理员在 `.env` 文件中配置
- Token 中需要包含 `sub`、`user_id`、`userid` 或 `userId` 字段来标识用户
- 配置项：`JWT_SECRET_KEY` 和 `JWT_ALGORITHM`

---

## 目录

- [0. 基础接口](#0-基础接口)
  - [0.1 根路径](#01-根路径)
  - [0.2 健康检查](#02-健康检查)
- [1. 患者数据处理接口](#1-患者数据处理接口)
  - [1.1 患者首次数据处理](#11-患者首次数据处理)
  - [1.2 查询任务状态](#12-查询任务状态)
- [2. 患者对话接口](#2-患者对话接口)
  - [2.1 与患者对话聊天](#21-与患者对话聊天)
- [3. 患者 PPT 生成接口](#3-患者-ppt-生成接口)
  - [3.1 生成患者 PPT](#31-生成患者-ppt)
  - [3.2 获取患者 PPT 数据](#32-获取患者-ppt-数据)

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
| user_id | string | 否 | 用户ID（如果未提供 token，则必填） |
| patient_description | string | 否 | 患者说明文本，描述患者基本情况 |
| consultation_purpose | string | 否 | 会诊目的，说明本次处理的目标 |
| files | array | 否 | 文件列表 |
| files[].file_name | string | 是 | 文件名（含扩展名） |
| files[].file_content | string | 是 | 文件内容（Base64 编码） |

**认证方式**:
- **推荐方式**：在 `Authorization` header 中提供 JWT token
  ```
  Authorization: Bearer <your_jwt_token>
  ```
- **备选方式**：在请求体中提供 `user_id`

**JWT Token 说明**:
- 算法：HS256（对称加密）
- 密钥：由系统管理员在 `.env` 文件中配置
- Token 中需要包含 `sub`、`user_id` 或 `userId` 字段来标识用户
- 配置项：`JWT_SECRET_KEY` 和 `JWT_ALGORITHM`

**注意**:
- `patient_description` 和 `files` 至少需要提供一个
- 此接口仅用于创建新患者，创建后会自动为 `user_id` 授予该患者的**所有者（owner）**权限
- 如需更新现有患者数据，请使用 `POST /api/patients/{patient_id}/chat` 接口

**请求示例 1（使用 Token）**:

```bash
curl -X POST http://localhost:9527/api/patient_data/process_patient_data_smart \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -d '{
    "patient_description": "患者李云山的完整病例资料，包含多次检查报告和影像资料",
    "consultation_purpose": "多学科会诊，制定综合治疗方案，评估预后情况",
    "files": [
      {
        "file_name": "检查报告.pdf",
        "file_content": "JVBERi0xLjQKJeLjz9MKMSAwIG9iago8PC9UeXBlL0NhdGFsb..."
      }
    ]
  }'
```

**请求示例 2（使用 user_id）**:

```json
{
  "user_id": "xxx",
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
- `is_update`: `false` 表示创建新患者
- `message`: "患者数据处理完成"
- `patient_id`: 患者唯一标识符（UUID格式），用于后续对话和PPT生成
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
- `400`: 请求参数错误（patient_description 和 files 至少需要提供一个）
- `500`: 服务器内部错误

**使用说明**:
1. **流式处理**：接口采用SSE (Server-Sent Events) 流式返回，实时推送处理进度
2. **断线续传**：客户端可以中途断开连接，后台任务会自动继续执行
3. **任务ID**：第一条消息中包含 `task_id`，客户端应保存此ID用于后续状态查询
4. **状态查询**：断开后可通过 `GET /api/patient_data/task_status/{task_id}` 查询任务状态
5. **文件上传**：文件内容需要Base64编码，系统会自动提取文件信息并存储
6. **数据提取**：系统会自动从结构化数据中提取患者姓名、年龄、性别等基本信息
7. **超时时间**：建议设置较长的请求超时时间（10-20分钟），或使用客户端断线续传功能

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
  "result": {
    "patient_id": "patient_uuid_xxx",
    "conversation_id": "conv_uuid_xxx",
    "uploaded_files_count": 3,
    "uploaded_file_ids": ["file_1", "file_2", "file_3"],
    "patient_timeline": {...},
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

## 2. 患者对话接口

> **统一入口**: 此接口同时支持**普通对话**和**数据更新**，通过大模型智能识别用户意图：
> - 💬 **普通对话 (chat)**: 直接回答用户问题，结合患者上下文信息
> - 📄 **新增数据 (update_data)**: 上传文件或要求补充数据时，调用 `PatientDataCrew` 提取结构化数据
> - ✏️ **修改数据 (modify_data)**: 要求修改已有数据时，调用 `PatientInfoUpdateCrew` 更新指定内容

### 2.1 与患者对话聊天

**接口**: `POST /api/patients/{patient_id}/chat`

**🔐 认证**: **需要 Token 鉴权**

**功能说明**:
- 🔄 **智能意图识别**: 自动判断用户意图（对话 / 新增数据 / 修改数据）
- 💬 **普通对话**: 基于患者信息回答问题
- 📄 **新增数据**: 上传文件时自动调用 `PatientDataCrew` 提取并合并结构化数据
- ✏️ **修改数据**: 修改已有数据时调用 `PatientInfoUpdateCrew` 更新指定内容
- 📝 **自动保存**: 对话历史保存到 `bus_conversation_messages` 表
- 🔗 **多轮会话**: 支持继续已有会话或创建新会话
- 📊 **上下文感知**: 对话上下文包含患者的时间轴数据

**意图类型**:

| 意图 | 说明 | 触发场景 | 处理方式 |
|------|------|----------|----------|
| `chat` | 普通对话/咨询/提问 | 询问治疗建议、病情分析、用药咨询等 | 使用通用 LLM 回复 |
| `update_data` | 新增/补充患者数据 | 录入检查报告、补充病历、上传文件等 | 调用 `PatientDataCrew` |
| `modify_data` | 修改已有数据 | 修改时间轴内容、更正患者信息等 | 调用 `PatientInfoUpdateCrew` |

**意图识别方式**:
- 🧠 **大模型智能识别**: 使用 LLM 分析用户消息语义，结合对话上下文判断意图
- 📄 **文件上传快速路径**: 上传文件时直接识别为 `update_data`（无需调用LLM）
- 💬 **语义理解示例**: 
  - "帮我录入这份CT报告" → `update_data` (modify_type: `add_new_data`)
  - "患者的诊断结果是什么？" → `chat`
  - "补充一下患者的用药信息" → `update_data` (modify_type: `add_new_data`)
  - "请把患者的过敏史更新为：青霉素过敏" → `modify_data` (modify_type: `modify_current_data`)
  - "这个治疗方案有什么建议？" → `chat`

**请求方式**: `POST`

**请求头**:

| Header | 值 | 必填 | 说明 |
|--------|------|------|------|
| Content-Type | application/json | 是 | 请求内容类型 |
| Authorization | Bearer \<token\> | 是 | JWT Token 鉴权 |

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
| messages | array | 否 | 对话历史（可选，类似 OpenAI 格式，用于客户端控制上下文） |
| messages[].role | string | 是 | 角色：`user`、`assistant` 或 `system` |
| messages[].content | string | 是 | 消息内容 |

**注意**:
- `message` 和 `files` 至少需要提供一个

**历史消息模式（混合模式）**:

本接口支持两种历史消息管理方式，可单独使用或组合使用：

| 场景 | conversation_id | messages | 行为 |
|------|-----------------|----------|------|
| 新对话 | ❌ | ❌ | 创建新会话，无历史上下文 |
| 继续会话 | ✅ | ❌ | 从数据库自动加载历史消息 |
| 无状态调用 | ❌ | ✅ | 使用传入的 messages 作为上下文，同时创建新会话保存消息 |
| 混合模式 | ✅ | ✅ | **messages 优先作为上下文**，但消息仍保存到指定会话 |

**请求示例（普通对话）**:

```bash
curl -X POST http://localhost:9527/api/patients/{patient_id}/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -d '{
    "message": "这位患者的治疗方案有什么建议？",
    "conversation_id": "conv_uuid_xxx"
  }'
```

**请求示例（新增数据 - 上传文件）**:

```bash
curl -X POST http://localhost:9527/api/patients/{patient_id}/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -d '{
    "message": "补充最新复查报告和影像资料，用于跟踪治疗效果",
    "files": [
      {
        "file_name": "复查CT.pdf",
        "file_content": "JVBERi0xLjQK..."
      }
    ]
  }'
```

**请求示例（修改数据）**:

```json
{
  "message": "请把患者的过敏史更新为：青霉素过敏、头孢类过敏"
}
```

**请求示例（OpenAI 风格 - 客户端传入上下文）**:

```json
{
  "message": "还有什么其他建议？",
  "messages": [
    {"role": "user", "content": "患者头痛三天了，有高血压病史"},
    {"role": "assistant", "content": "根据患者情况，建议进行头颅CT检查排除脑血管病变..."}
  ]
}
```

**请求示例（混合模式 - 自定义上下文 + 持久化）**:

```json
{
  "message": "继续分析治疗方案",
  "conversation_id": "conv_uuid_xxx",
  "messages": [
    {"role": "user", "content": "这是我想用的上下文"},
    {"role": "assistant", "content": "好的，我理解了"}
  ]
}
```

> 💡 **混合模式说明**: 当同时传入 `conversation_id` 和 `messages` 时，AI 会使用 `messages` 作为对话上下文（而非从数据库加载），但当前消息仍会保存到 `conversation_id` 对应的会话中，实现"自定义上下文 + 持久化存储"的效果。

**响应格式**: `text/event-stream` (Server-Sent Events)

**流式响应事件类型**:

| status | 说明 | 主要字段 |
|--------|------|----------|
| `received` | 消息已接收 | `task_id`, `message`, `progress` |
| `processing` | 处理中 | `stage`, `message`, `progress`, `intent`, `intent_confidence` |
| `streaming` | 流式返回AI回复 | `stage: response`, `content`, `progress` |
| `tool_output` | 工具输出（结构化数据） | `stage`, `data` |
| `completed` | 处理完成 | `message`, `duration`, `result` |
| `error` | 处理失败 | `message`, `error_type` |

**流式响应示例（普通对话）**:

```
data: {"task_id": "task_uuid", "status": "received", "message": "消息已接收，正在处理...", "progress": 0}

data: {"status": "processing", "stage": "intent_detected", "message": "意图识别: chat (置信度: 95%)", "intent": "chat", "intent_confidence": 0.95, "progress": 28}

data: {"status": "processing", "stage": "ai_processing", "message": "正在生成回复...", "progress": 35}

data: {"status": "streaming", "stage": "response", "content": "根据", "progress": 60}

data: {"status": "streaming", "stage": "response", "content": "患者的", "progress": 60}

data: {"status": "streaming", "stage": "response", "content": "病历资料...", "progress": 60}

data: {"status": "processing", "stage": "response_completed", "message": "回复生成完成", "progress": 95}

data: {"status": "completed", "message": "处理完成", "progress": 100, "duration": 5.67, "result": {"patient_id": "xxx", "conversation_id": "xxx", "intent": "chat", "files_processed": 0}}
```

**流式响应示例（新增/修改数据）**:

```
data: {"task_id": "task_uuid", "status": "received", "message": "消息已接收，正在处理...", "progress": 0}

data: {"status": "processing", "stage": "file_processing", "message": "正在处理 2 个文件", "progress": 10}

data: {"status": "processing", "stage": "file_processing_completed", "message": "文件处理完成，已保存 2 个文件", "progress": 25}

data: {"status": "processing", "stage": "intent_detected", "message": "意图识别: update_data (置信度: 98%)", "intent": "update_data", "intent_confidence": 0.98, "user_requirement": "补充最新复查报告", "progress": 28}

data: {"status": "processing", "stage": "data_extraction", "message": "正在提取患者数据...", "progress": 35}

data: {"status": "processing", "stage": "crew_processing", "message": "正在分析文件并提取结构化数据（可能需要5-10分钟）...", "progress": 40}

data: {"status": "processing", "stage": "data_extracted", "message": "数据处理完成，正在保存...", "progress": 80}

data: {"status": "processing", "stage": "data_saved", "message": "患者数据已更新，正在生成确认消息...", "progress": 90}

data: {"status": "tool_output", "stage": "patient_timeline", "data": {"tool_name": "patient_timeline", "tool_type": "timeline", "agent_name": "患者数据处理专家", "content": {"patient_timeline": {...}, "patient_journey": {...}, "mdt_simple_report": {...}}}}

data: {"status": "streaming", "stage": "response", "content": "✅ 患者数据更新已完成！", "progress": 95}

data: {"status": "completed", "message": "处理完成", "progress": 100, "duration": 65.32, "result": {"patient_id": "xxx", "conversation_id": "xxx", "intent": "update_data", "files_processed": 2}}
```

**完成时的 result 字段**:

```json
{
  "patient_id": "患者ID",
  "conversation_id": "会话ID",
  "intent": "chat|update_data|modify_data",
  "files_processed": 0
}
```

**HTTP 状态码**:
- `200`: 成功建立流式连接
- `400`: 请求参数错误（message 和 files 至少需要提供一个）
- `401`: 未授权（缺少或无效的 Token）
- `404`: 患者不存在
- `500`: 服务器内部错误

---

## 3. 患者 PPT 生成接口

### 3.1 生成患者 PPT

**接口**: `POST /api/patients/{patient_id}/generate_ppt`

**🔐 认证**: **需要 Token 鉴权**

**功能说明**:
- 基于患者的所有结构化数据生成医疗会诊 PPT
- 自动聚合患者的时间轴、诊疗历程、MDT 报告等数据
- 从数据库获取所有关联的原始文件
- 生成包含患者完整病历的 PPT 文件
- 自动保存 PPT 数据和成果到数据库

**请求方式**: `POST`

**请求头**:

| Header | 值 | 必填 | 说明 |
|--------|------|------|------|
| Content-Type | application/json | 是 | 请求内容类型 |
| Authorization | Bearer \<token\> | 是 | JWT Token 鉴权 |

**路径参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| patient_id | string | 是 | 患者ID（从数据处理接口返回） |

**请求示例**:

```bash
curl -X POST http://localhost:9527/api/patients/patient_uuid_xxx/generate_ppt \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
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
  },
  "ppt_data": {...},
  "treatment_gantt_data": {...}
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
- `400`: 患者数据不完整，无法生成（如时间轴数据为空）
- `401`: 未授权（缺少或无效的 Token）
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



