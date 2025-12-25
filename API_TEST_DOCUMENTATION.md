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
- [2. 患者 PPT 生成接口](#2-患者-ppt-生成接口)
  - [2.1 生成患者 PPT](#21-生成患者-ppt)
  - [2.2 获取患者 PPT 数据](#22-获取患者-ppt-数据)

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

### 1.1 混合智能处理

**接口**: `POST /api/patient_data/process_patient_data_smart`

**功能说明**:
- 处理患者病历文件，提取结构化数据（患者时间轴、诊疗历程等）
- 支持流式响应（Server-Sent Events），实时返回处理进度
- 支持客户端断开后后台继续执行
- 生成 `patient_id` 和 `conversation_id`，用于后续 PPT 生成

**请求方式**: `POST`

**Content-Type**: `application/json`

**请求参数**:

| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| patient_id | string | 否 | 患者ID。提供时更新现有患者数据，不提供时创建新患者 |
| patient_description | string | 否 | 患者说明文本，描述患者基本情况 |
| consultation_purpose | string | 否 | 会诊目的，说明本次处理的目标 |
| files | array | 否 | 文件列表 |
| files[].file_name | string | 是 | 文件名（含扩展名） |
| files[].file_content | string | 是 | 文件内容（Base64 编码） |

**注意**:
- `patient_description` 和 `files` 至少需要提供一个
- 提供 `patient_id` 时，接口会更新该患者的现有数据（追加文件，合并结构化数据）
- 不提供 `patient_id` 时，接口会创建新患者记录

**请求示例**:

**创建新患者**:
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

**更新现有患者**:
```json
{
  "patient_id": "patient_uuid_xxx",
  "patient_description": "补充最新的复查报告",
  "files": [
    {
      "file_name": "复查报告.pdf",
      "file_content": "JVBERi0xLjQKJeLjz9MKMSAwIG9..."
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

**更新模式的流式响应**（提供了 patient_id）:

更新模式下，在数据处理完成后，会额外生成一个**AI对话式确认消息**，模拟医疗助手与用户的友好交互。

```
data: {"task_id": "uuid-xxx-xxx", "status": "received", "message": "✅ 保存成功，系统会在后台进行自动解析并添加到患者列表中，预计10~20分钟，您可以先关闭对话框，耐心等待。", "progress": 0}

data: {"status": "processing", "stage": "patient_data_structuring", "message": "正在进行患者数据更新处理", "progress": 30}

# ========== AI对话式确认消息开始（逐字流式输出） ==========
data: {"status": "streaming_response", "stage": "confirmation", "message": "✅", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": " 患者", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "信息", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "修改", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "已经", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "完成", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "！", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "我已", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "成功", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "为您", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "补充", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "了", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": " 2", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": " 个", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "文件", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "，", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "并更新", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "了", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "患者", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "的", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "时间", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "轴", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "数据", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "。", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "您可以", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "查看", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "更新", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "后的", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "患者", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "信息", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "。", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "还有", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "其他", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "需要", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "帮助", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "的吗", "is_chunk": true, "progress": 90}

data: {"status": "streaming_response", "stage": "confirmation", "message": "？", "is_chunk": true, "progress": 90}

# ========== AI确认消息结束标记 ==========
data: {"status": "streaming_response", "stage": "confirmation_complete", "message": "", "is_chunk": false, "progress": 95}

# ========== 最终完成消息 ==========
data: {"status": "completed", "message": "患者数据更新完成", "progress": 100, "duration": 98.32, "is_update": true, "result": {...}}
```

**AI确认消息字段说明**：
- `status`: 固定为 `"streaming_response"`，表示这是流式AI响应
- `stage`:
  - `"confirmation"`: AI确认消息的内容块
  - `"confirmation_complete"`: AI确认消息结束标记
- `message`:
  - 当 `is_chunk: true` 时，包含AI生成的文本片段（逐字或逐词）
  - 当 `is_chunk: false` 时，为空字符串（结束标记）
- `is_chunk`:
  - `true`: 表示这是消息的一部分，需要累积拼接
  - `false`: 表示消息结束
- `progress`: 固定为90-95之间，表示即将完成



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

## 2. 患者 PPT 生成接口

### 2.1 生成患者 PPT

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

