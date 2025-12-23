# MediWise API 接口文档

**版本**: 1.0.0
**Base URL**: `http://182.254.240.153:9527`
**认证方式**: 暂无需认证

---

## 目录

- [1. 患者数据处理接口](#1-患者数据处理接口)
  - [1.1 混合智能处理](#11-混合智能处理)
  - [1.2 查询任务状态](#12-查询任务状态)
- [2. 患者 PPT 生成接口](#2-患者-ppt-生成接口)
  - [2.1 生成患者 PPT](#21-生成患者-ppt)
  - [2.2 获取患者 PPT 数据](#22-获取患者-ppt-数据)
- [3. 测试脚本使用说明](#3-测试脚本使用说明)
  - [3.1 test_flow_simple.py](#31-test_flow_simplepy)
  - [3.2 test_ppt_api.py](#32-test_ppt_apipy)

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
| patient_description | string | 否 | 患者说明文本，描述患者基本情况 |
| consultation_purpose | string | 否 | 会诊目的，说明本次处理的目标 |
| files | array | 否 | 文件列表 |
| files[].file_name | string | 是 | 文件名（含扩展名） |
| files[].file_content | string | 是 | 文件内容（Base64 编码） |

**注意**: `patient_description` 和 `files` 至少需要提供一个

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
data: {"task_id": "uuid-xxx-xxx", "status": "started", "message": "开始处理患者数据", "progress": 0}

data: {"status": "processing", "stage": "file_processing", "message": "正在处理 2 个文件", "progress": 10}

data: {"status": "processing", "stage": "file_processing_completed", "message": "文件处理完成，共提取 2 个文件", "progress": 25}

data: {"status": "processing", "stage": "patient_data_structuring", "message": "正在进行患者数据结构化处理", "progress": 30}

data: {"status": "completed", "message": "患者数据处理完成", "progress": 100, "duration": 123.45, "result": {...}}
```

**完成时的 result 字段**:

```json
{
  "patient_id": "患者唯一ID",
  "conversation_id": "会话ID",
  "uploaded_files_count": 2,
  "uploaded_file_ids": ["file_id_1", "file_id_2"],
  "patient_timeline": {
    "基本信息": {...},
    "时间轴": [...]
  },
  "patient_journey": {
    "诊疗历程": [...]
  },
  "mdt_simple_report": {
    "MDT简报": {...}
  },
  "patient_full_content": "患者完整内容文本"
}
```

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
1. 客户端可以中途断开连接，后台任务会继续执行
2. 第一条消息中包含 `task_id`，客户端应保存此 ID
3. 如需查询任务状态，使用 `task_id` 调用状态查询接口

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

**处理中**:
```json
{
  "status": "processing",
  "progress": 45,
  "message": "正在进行患者数据结构化处理",
  "stage": "patient_data_structuring"
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
    "patient_id": "患者ID",
    "conversation_id": "会话ID",
    "uploaded_files_count": 2,
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
- 本接口可能需要较长时间（通常 1-5 分钟）
- 建议设置较长的请求超时时间（如 300 秒）
- 返回的 URL 类型取决于配置：
  - `ppt_url`: Suvalue API 模式的 PPT 链接
  - `qiniu_url`: 本地生成 + 七牛云上传的链接
  - `local_path`: 本地文件路径

---

### 2.2 获取患者 PPT 数据

**接口**: `GET /api/patients/{patient_id}/ppt_data`

**功能说明**:
- 获取患者用于生成 PPT 的所有数据
- 用于预览、调试或验证数据完整性
- 不会生成 PPT，仅返回数据

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
  "data": {
    "patient_info": {
      "patient_id": "patient_uuid_xxx",
      "name": "李云山",
      "gender": "男",
      "age": 65
    },
    "patient_timeline": {
      "基本信息": {...},
      "时间轴": [
        {
          "日期": "2024-01-01",
          "事件": "初诊",
          "详情": "..."
        }
      ]
    },
    "patient_journey": {
      "诊疗历程": [...]
    },
    "mdt_reports": [
      {
        "日期": "2024-01-15",
        "类型": "MDT讨论",
        "内容": "..."
      }
    ],
    "raw_files_data": [
      {
        "file_id": "file_1",
        "file_name": "检查报告.pdf",
        "source_type": "pdf",
        "file_size": 1024000
      }
    ]
  }
}
```

**HTTP 状态码**:
- `200`: 成功获取数据
- `404`: 患者不存在
- `500`: 查询失败

---

