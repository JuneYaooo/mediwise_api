# JSON按字段分块生成 - 详细说明

## 🎯 核心概念

### 什么是"按字段分块"？

简单来说：**把一个大的JSON拆成多个小的JSON，每次只生成部分字段，最后合并**。

### 🆕 上下文传递机制

为了保证分块之间的逻辑一致性，系统会：
1. **累积上下文**：每生成一个分块后，将其内容保存到累积上下文中
2. **传递上下文**：生成下一个分块时，将之前生成的所有内容作为上下文传递给LLM
3. **一致性检查**：LLM会根据已生成的内容，确保新生成的内容与之前的内容保持逻辑一致

**示例**：
- 第1次生成基本信息：患者年龄45岁，诊断为高血压
- 第2次生成治疗信息时，LLM会看到"患者45岁，高血压"，因此会生成降压药治疗方案，而不是降糖药
- 第3次生成检查信息时，LLM会看到"患者45岁，高血压，正在服用降压药"，因此会生成血压监测等相关检查

---

## 🔗 上下文传递示例

### 场景：生成患者PPT数据（带上下文传递）

**第1次LLM调用** - 生成基本信息（无上下文）
```
提示词：
你是一个医疗数据处理专家。现在需要生成PPT数据的【基本信息】部分。
任务: 只生成以下字段的数据：title, patient, diag
...
```

输出：
```json
{
  "pptTemplate2Vm": {
    "title": "患者病历报告",
    "patient": {
      "name": "张三",
      "age": 45,
      "gender": "男"
    },
    "diag": {
      "diagnosis": "高血压",
      "date": "2024-01-15"
    }
  }
}
```

**第2次LLM调用** - 生成治疗信息（带上下文）
```
提示词：
你是一个医疗数据处理专家。现在需要生成PPT数据的【治疗信息】部分。
任务: 只生成以下字段的数据：treatments, medications

**已生成的内容**（请保持一致，不要产生矛盾）:
{
  "title": "患者病历报告",
  "patient": {
    "name": "张三",
    "age": 45,
    "gender": "男"
  },
  "diag": {
    "diagnosis": "高血压",
    "date": "2024-01-15"
  }
}

**上下文一致性要求**:
- 你生成的内容必须与上述已生成的内容保持逻辑一致
- 例如：如果患者诊断是"高血压"，治疗方案应该是降压药，不能是降糖药
- 如果患者年龄是45岁，不要在其他地方说50岁
- 保持所有日期、名称、数值、诊断信息的一致性
...
```

输出（注意：LLM看到了诊断是"高血压"，因此生成降压药）：
```json
{
  "pptTemplate2Vm": {
    "treatments": [
      {
        "name": "降压治疗",
        "date": "2024-01-15",
        "details": "针对高血压的综合治疗方案"
      }
    ],
    "medications": [
      {
        "name": "氨氯地平",
        "dosage": "5mg",
        "frequency": "每日一次",
        "purpose": "降压"
      }
    ]
  }
}
```

**第3次LLM调用** - 生成检查信息（带更多上下文）
```
提示词：
你是一个医疗数据处理专家。现在需要生成PPT数据的【检查信息】部分。
任务: 只生成以下字段的数据：examinations, lab_tests

**已生成的内容**（请保持一致，不要产生矛盾）:
{
  "title": "患者病历报告",
  "patient": {
    "name": "张三",
    "age": 45,
    "gender": "男"
  },
  "diag": {
    "diagnosis": "高血压",
    "date": "2024-01-15"
  },
  "treatments": [
    {
      "name": "降压治疗",
      "date": "2024-01-15",
      "details": "针对高血压的综合治疗方案"
    }
  ],
  "medications": [
    {
      "name": "氨氯地平",
      "dosage": "5mg",
      "frequency": "每日一次",
      "purpose": "降压"
    }
  ]
}

**上下文一致性要求**:
- 你生成的内容必须与上述已生成的内容保持逻辑一致
...
```

输出（注意：LLM看到了"高血压"和"降压治疗"，因此生成血压相关检查）：
```json
{
  "pptTemplate2Vm": {
    "examinations": [
      {
        "type": "血压监测",
        "date": "2024-01-15",
        "result": "收缩压150mmHg，舒张压95mmHg"
      }
    ],
    "lab_tests": [
      {
        "name": "血脂检查",
        "date": "2024-01-15",
        "result": "总胆固醇5.2mmol/L"
      }
    ]
  }
}
```

**最终合并结果**：
```json
{
  "pptTemplate2Vm": {
    "title": "患者病历报告",
    "patient": {
      "name": "张三",
      "age": 45,
      "gender": "男"
    },
    "diag": {
      "diagnosis": "高血压",
      "date": "2024-01-15"
    },
    "treatments": [
      {
        "name": "降压治疗",
        "date": "2024-01-15",
        "details": "针对高血压的综合治疗方案"
      }
    ],
    "medications": [
      {
        "name": "氨氯地平",
        "dosage": "5mg",
        "frequency": "每日一次",
        "purpose": "降压"
      }
    ],
    "examinations": [
      {
        "type": "血压监测",
        "date": "2024-01-15",
        "result": "收缩压150mmHg，舒张压95mmHg"
      }
    ],
    "lab_tests": [
      {
        "name": "血脂检查",
        "date": "2024-01-15",
        "result": "总胆固醇5.2mmol/L"
      }
    ]
  }
}
```

**关键点**：
- ✅ 所有内容都围绕"高血压"这个诊断
- ✅ 治疗方案是降压药（不是降糖药）
- ✅ 检查项目是血压监测（不是血糖监测）
- ✅ 患者年龄、姓名在所有分块中保持一致
- ✅ 没有逻辑矛盾

---

## 📝 具体示例

### 示例1: PPT生成

#### 完整JSON（太大，一次生成不了）

```json
{
  "pptTemplate2Vm": {
    "title": "患者病历报告",
    "patient": {
      "name": "张三",
      "age": 45,
      "gender": "男"
    },
    "diag": {
      "diagnosis": "高血压",
      "date": "2024-01-15"
    },
    "treatments": [
      // 100条治疗记录，每条200字
      // 总共约20,000字符 = 约10,000 tokens
    ],
    "examinations": [
      // 200条检查记录
      // 总共约30,000字符 = 约15,000 tokens
    ],
    "images": [
      // 50张图片信息
    ]
  }
}
```

**问题**: 完整JSON需要约30,000 tokens，但GPT-4只能输出4,096 tokens ❌

---

#### 解决方案：分5次生成

**第1次LLM调用** - 只生成基本信息（约500 tokens）✅
```json
{
  "pptTemplate2Vm": {
    "title": "患者病历报告",
    "patient": {
      "name": "张三",
      "age": 45,
      "gender": "男"
    },
    "diag": {
      "diagnosis": "高血压",
      "date": "2024-01-15"
    }
  }
}
```

**第2次LLM调用** - 只生成治疗信息（约3,000 tokens）✅
```json
{
  "pptTemplate2Vm": {
    "treatments": [
      {
        "name": "降压治疗",
        "date": "2024-01-15",
        "details": "..."
      },
      // ... 更多治疗记录
    ]
  }
}
```

**第3次LLM调用** - 只生成检查信息（约3,000 tokens）✅
```json
{
  "pptTemplate2Vm": {
    "examinations": [
      {
        "type": "血压检查",
        "date": "2024-01-15",
        "result": "..."
      },
      // ... 更多检查记录
    ]
  }
}
```

**第4次LLM调用** - 只生成影像资料（约2,000 tokens）✅
```json
{
  "pptTemplate2Vm": {
    "images": [
      {
        "url": "https://...",
        "type": "CT",
        "date": "2024-01-15"
      },
      // ... 更多影像
    ]
  }
}
```

**第5次LLM调用** - 只生成时间轴和图表（约2,000 tokens）✅
```json
{
  "pptTemplate2Vm": {
    "timeline": [...],
    "indicators": [...],
    "gantt": [...]
  }
}
```

**最后合并** - 得到完整JSON ✅
```json
{
  "pptTemplate2Vm": {
    "title": "患者病历报告",
    "patient": {...},
    "diag": {...},
    "treatments": [...],      // 从第2次调用
    "examinations": [...],    // 从第3次调用
    "images": [...],          // 从第4次调用
    "timeline": [...],        // 从第5次调用
    "indicators": [...],      // 从第5次调用
    "gantt": [...]           // 从第5次调用
  }
}
```

---

### 示例2: 患者信息结构化

#### 完整JSON（太大）

```json
{
  "patient_structured_data": {
    "patient_info": {...},
    "diagnoses": [...],        // 50条诊断
    "medications": [...],      // 100种药物
    "lab_tests": [...],        // 200次检验
    "examinations": [...],     // 150次检查
    "treatments": [...],       // 80次治疗
    "medical_history": {...}
  }
}
```

**问题**: 需要约25,000 tokens输出 ❌

---

#### 解决方案：分6次生成

**第1次** - 基本信息（500 tokens）
```json
{
  "patient_structured_data": {
    "patient_info": {
      "name": "李四",
      "age": 50,
      "gender": "女",
      "id": "123456"
    }
  }
}
```

**第2次** - 诊断信息（2,000 tokens）
```json
{
  "patient_structured_data": {
    "diagnoses": [
      {
        "diagnosis": "糖尿病",
        "date": "2024-01-01",
        "icd_code": "E11"
      },
      // ... 更多诊断
    ]
  }
}
```

**第3次** - 用药信息（2,000 tokens）
```json
{
  "patient_structured_data": {
    "medications": [
      {
        "name": "二甲双胍",
        "dosage": "500mg",
        "frequency": "每日三次"
      },
      // ... 更多药物
    ]
  }
}
```

**第4次** - 检查检验（3,000 tokens）
```json
{
  "patient_structured_data": {
    "lab_tests": [...],
    "examinations": [...]
  }
}
```

**第5次** - 治疗记录（3,000 tokens）
```json
{
  "patient_structured_data": {
    "treatments": [...]
  }
}
```

**第6次** - 病史和随访（2,000 tokens）
```json
{
  "patient_structured_data": {
    "medical_history": {...},
    "follow_ups": [...]
  }
}
```

**合并** - 完整的患者结构化数据 ✅

---

## 🔧 使用方式

### 方式1: 使用预定义配置

```python
from src.utils.universal_chunked_generator import UniversalChunkedGenerator
from src.utils.token_manager import TokenManager

# 初始化
token_manager = TokenManager(logger=logger)
generator = UniversalChunkedGenerator(logger=logger, token_manager=token_manager)

# PPT生成
ppt_data = generator.generate_in_chunks(
    llm=document_generation_llm,
    task_type='ppt_generation',  # 使用预定义的PPT分块配置
    input_data=patient_data,
    template_or_schema=template_json,
    model_name='gpt-4'
)

# 患者信息结构化
structured_data = generator.generate_in_chunks(
    llm=document_generation_llm,
    task_type='patient_structuring',  # 使用预定义的患者结构化配置
    input_data=raw_patient_data,
    template_or_schema=schema_json,
    model_name='gpt-4'
)
```

### 方式2: 自定义分块

```python
# 创建自定义分块配置
custom_chunks = generator.create_custom_chunks([
    ('基本信息', ['name', 'age', 'gender'], 500),
    ('诊断信息', ['diagnoses', 'symptoms'], 2000),
    ('用药信息', ['medications', 'allergies'], 2000),
    ('检查信息', ['lab_tests', 'examinations'], 3000),
])

# 使用自定义配置生成
data = generator.generate_in_chunks(
    llm=llm,
    task_type='custom',
    input_data=input_data,
    template_or_schema=schema,
    model_name='gpt-4',
    custom_chunks=custom_chunks  # 传入自定义配置
)
```

---

## 📊 预定义的分块配置

### PPT生成（ppt_generation）

| 分块 | 字段 | 预估tokens |
|------|------|-----------|
| 基本信息 | title, patient, diag | 1,000 |
| 治疗信息 | treatments, medications, surgeries | 3,000 |
| 检查信息 | examinations, lab_tests, vital_signs | 3,000 |
| 影像资料 | images, medical_images, scans | 2,000 |
| 时间轴和图表 | timeline, events, indicators, gantt | 2,000 |

### 患者信息结构化（patient_structuring）

| 分块 | 字段 | 预估tokens |
|------|------|-----------|
| 基本信息 | patient_info, demographics, contact | 500 |
| 诊断信息 | diagnoses, chief_complaint, present_illness | 2,000 |
| 用药信息 | medications, allergies, adverse_reactions | 2,000 |
| 检查检验 | lab_tests, examinations, imaging_studies | 3,000 |
| 治疗记录 | treatments, procedures, surgeries | 3,000 |
| 病史和随访 | medical_history, family_history, follow_ups | 2,000 |

---

## 🎯 自动检测

系统会自动判断是否需要分块：

```python
# 自动检测
needs_chunking = generator.should_use_chunking(
    task_type='ppt_generation',
    model_name='gpt-4',
    expected_output_size=12000  # 预期输出12K tokens
)

if needs_chunking:
    # 使用分块生成
    data = generator.generate_in_chunks(...)
else:
    # 直接生成
    data = generate_directly(...)
```

**判断标准**:
- 预期输出 > 模型输出限制 × 安全比例 × 80%
- 例如GPT-4: 4096 × 0.9 × 0.8 = 2949 tokens

---

## 📝 日志示例

```log
====================================================================================================
🔀 启动分块生成模式 - 任务类型: patient_structuring
====================================================================================================

📦 生成分块 1/6: 基本信息
  ├─ 包含字段: ['patient_info', 'demographics', 'contact']
  └─ 最大tokens: 500
  ✅ 分块生成成功

📦 生成分块 2/6: 诊断信息
  ├─ 包含字段: ['diagnoses', 'chief_complaint', 'present_illness']
  └─ 最大tokens: 2000
  ✅ 分块生成成功

📦 生成分块 3/6: 用药信息
  ├─ 包含字段: ['medications', 'allergies', 'adverse_reactions']
  └─ 最大tokens: 2000
  ✅ 分块生成成功

📦 生成分块 4/6: 检查检验
  ├─ 包含字段: ['lab_tests', 'examinations', 'imaging_studies']
  └─ 最大tokens: 3000
  ✅ 分块生成成功

📦 生成分块 5/6: 治疗记录
  ├─ 包含字段: ['treatments', 'procedures', 'surgeries']
  └─ 最大tokens: 3000
  ✅ 分块生成成功

📦 生成分块 6/6: 病史和随访
  ├─ 包含字段: ['medical_history', 'family_history', 'follow_ups']
  └─ 最大tokens: 2000
  ✅ 分块生成成功

🔗 开始合并所有分块...

====================================================================================================
✅ 分块生成完成！共生成 6 个分块
📦 patient_structured_data 包含字段: ['patient_info', 'diagnoses', 'medications', 'lab_tests', 'examinations', 'treatments', 'medical_history', 'follow_ups']
====================================================================================================
```

---

## 🎨 优势

### 1. 突破输出限制
- ✅ 小输出模型也能生成大JSON
- ✅ 每个分块都在限制内
- ✅ 保证输出完整性

### 2. 灵活可控
- ✅ 可以自定义分块方式
- ✅ 可以调整每块的大小
- ✅ 可以设置优先级

### 3. 容错性强
- ✅ 单个分块失败不影响其他
- ✅ 可以单独重试失败的分块
- ✅ 详细的日志记录

### 4. 通用性强
- ✅ 支持PPT生成
- ✅ 支持患者信息结构化
- ✅ 支持任意JSON生成任务

---

## 📌 总结

**按字段分块** = 把大JSON拆成小JSON，分多次生成，最后合并

**适用场景**:
- ✅ 输出限制小的模型（GPT-4 4K）
- ✅ 需要生成大量数据（完整PPT、患者结构化）
- ✅ 对输出完整性要求高

**不适用场景**:
- ❌ 大输出模型（Gemini 64K）
- ❌ 输出数据量小（<2K tokens）
- ❌ 对速度要求极高（分块会慢一些）
