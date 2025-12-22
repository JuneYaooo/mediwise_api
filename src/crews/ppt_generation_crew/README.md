# PPT Generation Crew - 使用说明

## 概述

PPTGenerationCrew 支持两种PPT生成模式：
1. **Suvalue API模式**（默认）：调用远程API生成PPT
2. **本地模式**：使用python-pptx在本地生成PPT

## 快速开始

### 配置环境变量（推荐）

在 `.env` 文件中添加以下配置：

```bash
# PPT生成模式：true=使用Suvalue API（默认）, false=使用本地python-pptx
USE_SUVALUE_PPT=true

# Suvalue API认证Token（使用API模式时必需）
SUVALUE_PPT_AUTH_TOKEN=your_actual_token_here
```

### 基本使用

```python
from src.crews.ppt_generation_crew import PPTGenerationCrew

# 自动从环境变量读取配置
crew = PPTGenerationCrew()

# 生成PPT - auth_token会从环境变量自动读取（如果设置了）
result = crew.generate_ppt(
    patient_timeline=patient_timeline_data,
    patient_journey=patient_journey_data,
    raw_files_data=files_data,
    agent_session_id="session_123",
    auth_token="your_token"  # 或从环境变量读取
)
```

## 使用方法

### 1. Suvalue API模式（推荐）

**方式A：使用环境变量（推荐）**
```bash
# .env 文件
USE_SUVALUE_PPT=true
SUVALUE_PPT_AUTH_TOKEN=your_bearer_token
```

```python
from src.crews.ppt_generation_crew import PPTGenerationCrew
import os

# 自动从环境变量读取模式
crew = PPTGenerationCrew()

# auth_token从环境变量或参数传入
result = crew.generate_ppt(
    patient_timeline=patient_timeline_data,
    patient_journey=patient_journey_data,
    raw_files_data=files_data,
    agent_session_id="session_123",
    auth_token=os.getenv("SUVALUE_PPT_AUTH_TOKEN")
)
```

**方式B：代码中指定**
```python
# 显式指定使用Suvalue API
crew = PPTGenerationCrew(use_suvalue_api=True)

result = crew.generate_ppt(
    patient_timeline=patient_timeline_data,
    patient_journey=patient_journey_data,
    raw_files_data=files_data,
    agent_session_id="session_123",
    auth_token="your_bearer_token"
)
```

**返回格式：**
```python
{
    "success": True,
    "ppt_url": "https://ppt.suvalue.com/api/files/Ppts/xxx.pptx",
    "message": "PPT生成成功"
}
```

### 2. 本地模式

**方式A：使用环境变量**
```bash
# .env 文件
USE_SUVALUE_PPT=false
```

```python
from src.crews.ppt_generation_crew import PPTGenerationCrew

# 自动从环境变量读取模式
crew = PPTGenerationCrew()

result = crew.generate_ppt(
    patient_timeline=patient_timeline_data,
    patient_journey=patient_journey_data,
    raw_files_data=files_data,
    agent_session_id="session_123",
    template_id="medical"  # 可选
)
```

**方式B：代码中指定**
```python
# 显式指定使用本地模式
crew = PPTGenerationCrew(use_suvalue_api=False)

result = crew.generate_ppt(
    patient_timeline=patient_timeline_data,
    patient_journey=patient_journey_data,
    raw_files_data=files_data,
    agent_session_id="session_123",
    template_id="medical"
)
```

**返回格式：**
```python
{
    "success": True,
    "local_path": "/path/to/file.pptx",
    "filename": "medical_case_xxx.pptx",
    "file_uuid": "uuid-string",
    "file_key": "presentations/session_id/uuid.pptx",
    "qiniu_url": "https://..."
}
```

## 环境变量说明

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `USE_SUVALUE_PPT` | string | `"true"` | 控制PPT生成模式<br>• `true`/`1`/`yes`: 使用Suvalue API<br>• `false`/`0`/`no`: 使用本地生成 |
| `SUVALUE_PPT_AUTH_TOKEN` | string | - | Suvalue API的Bearer Token（API模式必需） |

## 参数说明

### 初始化参数

```python
PPTGenerationCrew(use_suvalue_api=None)
```

- `use_suvalue_api` (bool, optional):
  - `None`: 从环境变量 `USE_SUVALUE_PPT` 读取（默认）
  - `True`: 强制使用Suvalue API
  - `False`: 强制使用本地python-pptx

### generate_ppt() 参数

**通用参数：**
- `patient_timeline` (dict/list): 患者时间轴数据，用于PPT内容生成
- `patient_journey` (dict/list): 患者旅程数据，用于生成图片（时间旅程图、指标趋势图）
- `raw_files_data` (list): 原始文件数据
- `agent_session_id` (str): 会话ID

**Suvalue API模式专用：**
- `auth_token` (str): Bearer Token，**必需**（可从环境变量读取）

**本地模式专用：**
- `template_id` (str): PPT模板ID，默认"medical"

## 模式切换示例

### 示例1：完全使用环境变量
```bash
# .env
USE_SUVALUE_PPT=true
SUVALUE_PPT_AUTH_TOKEN=your_token_here
```

```python
import os
from src.crews.ppt_generation_crew import PPTGenerationCrew

# 完全从环境变量读取配置
crew = PPTGenerationCrew()

result = crew.generate_ppt(
    patient_timeline=timeline_data,
    patient_journey=journey_data,
    raw_files_data=files,
    agent_session_id="session_id",
    auth_token=os.getenv("SUVALUE_PPT_AUTH_TOKEN")
)
```

### 示例2：代码优先，环境变量备用
```python
from src.crews.ppt_generation_crew import PPTGenerationCrew

# 根据业务逻辑动态选择
use_api = some_condition()
crew = PPTGenerationCrew(use_suvalue_api=use_api)
```

### 示例3：开发/生产环境切换
```bash
# .env.development
USE_SUVALUE_PPT=false  # 开发环境用本地

# .env.production
USE_SUVALUE_PPT=true   # 生产环境用API
SUVALUE_PPT_AUTH_TOKEN=production_token
```

## 配置文件

### Agents配置 (config/agents.yaml)
- `ppt_content_generator`: 本地模式使用的agent
- `suvalue_ppt_data_transformer`: Suvalue API模式使用的agent

### Tasks配置 (config/tasks.yaml)
- `generate_ppt_slides_task`: 本地模式使用的task
- `transform_and_generate_ppt_task`: Suvalue API模式使用的task

## 返回值对比

| 字段 | Suvalue API模式 | 本地模式 |
|------|----------------|---------|
| success | ✓ | ✓ |
| ppt_url | ✓ | - |
| message | ✓ | - |
| local_path | - | ✓ |
| filename | - | ✓ |
| file_uuid | - | ✓ |
| file_key | - | ✓ |
| qiniu_url | - | ✓ |

## 注意事项

1. **环境变量优先级**：代码中显式指定 > 环境变量 > 默认值(true)
2. **Suvalue API模式**需要有效的auth_token
3. **本地模式**会生成本地文件并自动上传到七牛云
4. 两种模式生成的PPT格式和内容可能略有差异
5. 建议在生产环境根据实际需求选择合适的模式

## 故障排查

### 问题1：未读取到环境变量
确保 `.env` 文件在项目根目录，且代码开头有：
```python
from dotenv import load_dotenv
load_dotenv()
```

### 问题2：Suvalue API认证失败
检查 `SUVALUE_PPT_AUTH_TOKEN` 是否正确设置且有效

### 问题3：不知道当前使用的模式
查看日志输出：
```
PPTGenerationCrew 初始化: 模式=Suvalue API
```
或
```
PPTGenerationCrew 初始化: 模式=本地python-pptx
```
