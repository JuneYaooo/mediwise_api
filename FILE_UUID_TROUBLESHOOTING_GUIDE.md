# file_uuid 对应不上问题排查指南

## 🚨 问题现状

修复了代码逻辑后，仍然发现 `bus_patient_files` 表和 `bus_patient_structured_data` 表中的 `file_uuid` 对应不上。

---

## 🔍 已完成的修复

### 1. ✅ file_processing.py:131 - UUID 优先级修复
- 确保原始 `file_uuid` 优先使用
- 不会被提取器生成的 UUID 覆盖

### 2. ✅ extract_content_from_path.py - 移除重复UUID生成
- 单个文件不再生成新UUID
- 只有 zip/PDF 子文件生成新UUID

### 3. ✅ upload_timestamp 时区修复
- 改为使用北京时间

---

## ⚠️ 可能的原因

### 原因 1: **旧数据问题**

**症状**: 修复前的数据仍然是不一致的

**检查方法**:
```sql
-- 查看最近上传的文件（修复后的数据）
SELECT
    file_uuid,
    file_name,
    created_at
FROM bus_patient_files
WHERE is_deleted = false
    AND created_at > '2025-12-25 13:00:00'  -- 修复时间
ORDER BY created_at DESC;
```

**解决方案**: 只测试修复后新上传的文件

---

### 原因 2: **LLM 没有输出 file_uuid**

**症状**: LLM 在生成 JSON 时忽略了 `file_uuid` 字段

**检查方法**:
1. 查看日志中传给 LLM 的输入（应该包含 file_uuid）
2. 查看 LLM 的输出（检查是否包含 file_uuid）

**位置**:
- 输入: `patient_data_crew.py:384, 418, 463, 482`
- 输出解析: `patient_data_crew.py` 中的结果处理

**可能的原因**:
- LLM 模型不遵循提示词
- 提示词中没有明确要求输出 file_uuid
- LLM 输出的 JSON 格式不正确

**解决方案**: 检查 `tasks.yaml` 中的提示词配置

---

### 原因 3: **LLM 生成了错误的 file_uuid**

**症状**: LLM 生成了新的 UUID，而不是使用输入的 UUID

**检查方法**:
```python
# 对比输入和输出
input_file_uuid = "abc-123-def"
output_file_uuid = "xyz-789-ghi"  # 不一致！
```

**可能的原因**:
- LLM 自己生成了新的 UUID
- 提示词中要求生成 UUID

**解决方案**: 在提示词中明确要求"使用提供的 file_uuid，不要生成新的"

---

### 原因 4: **文件处理流程中的其他修改**

**症状**: 在某个中间环节，file_uuid 被修改了

**检查点**:
1. `file_processing_manager.py:107` - 生成 UUID ✅
2. `qiniu_upload_service.py:144` - 返回 UUID ✅
3. `file_processing.py:131` - 选择 UUID ✅ (已修复)
4. `file_metadata_builder.py:96` - 构建元数据 ✅
5. `bus_patient_helpers.py:382` - 保存到数据库 ✅
6. `patient_data_crew.py` - 传给 LLM ❓ (待检查)
7. LLM 输出 ❓ (待检查)
8. 保存结构化数据 ✅

**重点检查**: 步骤 6 和 7

---

### 原因 5: **conversation_id 不一致**

**症状**: 文件记录和结构化数据的 `conversation_id` 不匹配

**检查方法**:
```sql
SELECT
    pf.file_uuid,
    pf.file_name,
    pf.conversation_id as file_conv_id,
    psd.data_type,
    psd.conversation_id as data_conv_id
FROM bus_patient_files pf
LEFT JOIN bus_patient_structured_data psd
    ON pf.patient_id = psd.patient_id
WHERE pf.patient_id = 'YOUR_PATIENT_ID'
    AND pf.is_deleted = false
    AND psd.is_deleted = false;
```

**解决方案**: 确保使用相同的 `conversation_id`

---

## 🛠️ 排查工具

### 工具 1: 快速检查脚本

```bash
./quick_check_file_uuid.sh [patient_id]
```

会显示:
- bus_patient_files 中的 file_uuid
- bus_patient_structured_data 中的数据
- file_uuid 是否在 structuredcontent 中

---

### 工具 2: 详细排查脚本

```bash
python3 debug_file_uuid_detailed.py [patient_id]
```

会显示:
- 完整的文件列表
- 完整的结构化数据
- 详细的匹配统计

---

### 工具 3: 日志检查

查看应用日志中的关键信息:

```bash
# 查看文件处理日志
grep "file_uuid" app.log | tail -100

# 查看传给 LLM 的输入
grep "传递给" app.log | tail -50

# 查看 LLM 输出
grep "结构化数据" app.log | tail -50
```

---

## 🔬 诊断步骤

### 第 1 步: 上传新文件测试

1. 上传一个**新的**测试文件
2. 记录 `file_uuid`（从返回结果或数据库查询）
3. 等待处理完成

### 第 2 步: 查询数据库

```sql
-- 替换为你的 patient_id
SET @patient_id = 'YOUR_PATIENT_ID';

-- 查看文件记录
SELECT file_uuid, file_name
FROM bus_patient_files
WHERE patient_id = @patient_id
    AND is_deleted = false
ORDER BY created_at DESC
LIMIT 1;

-- 查看结构化数据
SELECT
    data_type,
    structuredcontent::text LIKE '%YOUR_FILE_UUID%' as has_uuid
FROM bus_patient_structured_data
WHERE patient_id = @patient_id
    AND is_deleted = false;
```

### 第 3 步: 分析结果

| 情况 | 原因 | 解决方案 |
|------|------|---------|
| ✅ 找到了 | 修复成功 | 无需处理 |
| ❌ 没找到，structuredcontent 为空 | 结构化数据生成失败 | 检查 LLM 调用日志 |
| ❌ 没找到，structuredcontent 有数据但没有 file_uuid | LLM 没有输出 file_uuid | 检查提示词 |
| ❌ 没找到，structuredcontent 有其他 file_uuid | LLM 生成了错误的 UUID | 检查 LLM 输入 |

---

## 💡 快速修复建议

### 如果是 LLM 没有输出 file_uuid

#### 检查 tasks.yaml

文件: `src/crews/patient_data_crew/config/tasks.yaml:210`

确认提示词中有：
```yaml
"file_uuid": "来源文件的UUID（如果基于某个源文件提取，否则为空）",
```

#### 强化提示词

如果 LLM 仍然忽略 file_uuid，可以在提示词中强调：

```yaml
"file_uuid": "【重要】来源文件的UUID，必须使用输入中提供的file_uuid值，不要生成新的UUID"
```

---

### 如果是 LLM 生成了错误的 UUID

#### 检查传给 LLM 的输入

在 `patient_data_crew.py:388` 附近添加日志：

```python
logger.info(f"传递给LLM的文件信息: file_uuid={file_uuid}, file_name={file_name}")
```

#### 检查 LLM 输出

在解析 LLM 输出的地方添加日志：

```python
logger.info(f"LLM输出的file_uuid: {item.get('file_uuid')}")
```

---

## 🎯 最终验证

修复完成后，运行完整测试：

1. 上传新文件
2. 运行检查脚本
3. 确认 file_uuid 一致

**预期结果**:
```
✅ bus_patient_files: file_uuid = abc-123
✅ structuredcontent: file_uuid = abc-123
✅ 对应关系正确
```

---

## 📞 如果问题仍未解决

请提供以下信息：

1. **patient_id**: 测试患者的ID
2. **file_uuid**: 期望的 file_uuid
3. **检查脚本输出**: `./quick_check_file_uuid.sh` 的完整输出
4. **相关日志**: 文件上传到结构化数据生成的完整日志
5. **创建时间**: 文件的 `created_at`（确认是修复后的数据）

---

## 📅 修复历史

| 日期 | 修复内容 | 文件 |
|------|---------|------|
| 2025-12-25 | UUID 优先级修复 | file_processing.py:131 |
| 2025-12-25 | 移除重复UUID生成 | extract_content_from_path.py:196-234 |
| 2025-12-25 | upload_timestamp 时区修复 | file_metadata_builder.py:114 |

---

## ✅ 总结

修复已完成，但需要：
1. **测试新上传的文件**（旧数据可能仍不一致）
2. **检查 LLM 输入输出**（确认 file_uuid 正确传递）
3. **验证结果**（使用提供的工具）

如果新上传的文件仍然对应不上，最可能的原因是 **LLM 没有正确处理 file_uuid**。
