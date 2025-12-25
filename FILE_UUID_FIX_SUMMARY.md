# file_uuid 不一致问题修复总结

## 🐛 问题描述

**现象**: `bus_patient_files` 表中的 `file_uuid` 与 `bus_patient_structured_data` 表中 `structuredcontent` 里的 `file_uuid` 对应不上。

**根本原因**: 文件提取器 (`extract_content_from_path.py`) 在处理文件时重新生成了新的 UUID，并且文件处理逻辑 (`file_processing.py`) 优先使用了提取器生成的 UUID，导致原始 UUID 被覆盖。

---

## 🔍 问题定位

### 原始流程（有问题）

```
1. file_processing_manager.py:107
   └─> 生成原始 file_uuid = "abc-123"

2. qiniu_upload_service.py:144
   └─> 保存到七牛云，返回 file_uuid = "abc-123"

3. extract_content_from_path.py:200
   └─> ❌ 重新生成 file_uuid = "xyz-789"

4. file_processing.py:131
   └─> ❌ 优先使用提取器的 UUID: final_file_uuid = "xyz-789"

5. 保存到 bus_patient_files
   └─> ??? 可能使用了 "xyz-789"

6. 传给 LLM
   └─> file_uuid = "xyz-789"

7. LLM 输出到 structuredcontent
   └─> file_uuid = "xyz-789"

结果：file_uuid 不一致！
```

---

## ✅ 修复方案

### 修复 1: `file_processing.py:131` - 优先级调整

**修改位置**: `/home/ubuntu/github/mediwise_api/app/utils/file_processing.py:131`

**修改前**:
```python
# 使用提取结果中的UUID，如果没有则使用之前的UUID
final_file_uuid = extracted_file_uuid if extracted_file_uuid else file_uuid
```

**修改后**:
```python
# 🔧 修复：优先使用原始UUID而不是提取器生成的UUID，确保与数据库一致
final_file_uuid = file_uuid if file_uuid else extracted_file_uuid
```

**作用**: 确保原始的 `file_uuid` (在 `file_processing_manager.py:107` 生成的) 始终被保留，不会被提取器生成的 UUID 覆盖。

---

### 修复 2: `extract_content_from_path.py:196-221` - 移除不必要的UUID生成

**修改位置**: `/home/ubuntu/github/mediwise_api/src/custom_tools/extract_content_from_path.py`

#### 2.1 第196-206行 - 单个文件结果

**修改前**:
```python
if isinstance(result, dict):
    # 为字典结果添加UUID
    if 'file_uuid' not in result:
        result['file_uuid'] = str(uuid.uuid4())  # ❌ 生成新UUID
```

**修改后**:
```python
if isinstance(result, dict):
    # 标记提取成功（如果result是字典且没有error字段）
    if 'extraction_success' not in result:
        # 判断是否提取成功：有file_content且内容不为空
        has_content = result.get('file_content') and len(str(result.get('file_content', '')).strip()) > 0
        result['extraction_success'] = has_content
        if not has_content:
            result['extraction_error'] = '提取内容为空'

    # 注意：不在这里生成file_uuid，由上层统一管理
```

**作用**: 不再为单个文件生成新的 UUID，让上层 (`file_processing.py`) 统一管理。

---

#### 2.2 第207-221行 - 列表结果（zip/PDF子文件）

**修改后**:
```python
elif isinstance(result, list):
    # 对于返回列表的情况（如zip文件、PDF with images），标记提取状态
    for item in result:
        if isinstance(item, dict):
            # 标记提取成功
            if 'extraction_success' not in item:
                has_content = item.get('file_content') and len(str(item.get('file_content', '')).strip()) > 0
                item['extraction_success'] = has_content
                if not has_content:
                    item['extraction_error'] = '提取内容为空'

            # 注意：这里保留UUID生成，因为zip/PDF中的子文件需要新的UUID
            # 但是主文件的UUID应该保留原始值
            if 'file_uuid' not in item:
                item['file_uuid'] = str(uuid.uuid4())
```

**作用**:
- 对于 **zip/PDF 中的子文件**，仍然生成新的 UUID（因为它们是新的文件记录）
- 对于 **主文件**，不生成 UUID，保留原始值

---

#### 2.3 第147-159行 - 隐藏文件处理

**修改前**:
```python
return {
    'file_extension': 'hidden',
    'file_name': filename,
    'file_content': f"系统隐藏文件: {filename} (已跳过处理)",
    'extraction_success': False,
    'extraction_error': '系统隐藏文件，已跳过处理',
    'file_uuid': str(uuid.uuid4())  # ❌ 生成新UUID
}
```

**修改后**:
```python
return {
    'file_extension': 'hidden',
    'file_name': filename,
    'file_content': f"系统隐藏文件: {filename} (已跳过处理)",
    'extraction_success': False,
    'extraction_error': '系统隐藏文件，已跳过处理'
    # 注意：不生成UUID，由上层统一管理
}
```

---

#### 2.4 第224-234行 - 异常处理

**修改前**:
```python
return {
    'file_extension': os.path.splitext(filename)[1].lower()[1:] if os.path.isfile(path) else 'unknown',
    'file_name': filename,
    'file_content': f"文件提取失败: {str(e)}",
    'extraction_success': False,
    'extraction_error': f"{type(e).__name__}: {str(e)}",
    'file_uuid': str(uuid.uuid4())  # ❌ 生成新UUID
}
```

**修改后**:
```python
return {
    'file_extension': os.path.splitext(filename)[1].lower()[1:] if os.path.isfile(path) else 'unknown',
    'file_name': filename,
    'file_content': f"文件提取失败: {str(e)}",
    'extraction_success': False,
    'extraction_error': f"{type(e).__name__}: {str(e)}"
    # 注意：不生成UUID，由上层统一管理
}
```

---

## 🎯 修复后的流程

```
1. file_processing_manager.py:107
   └─> 生成原始 file_uuid = "abc-123"

2. qiniu_upload_service.py:144
   └─> 保存到七牛云，返回 file_uuid = "abc-123"

3. extract_content_from_path.py
   └─> ✅ 不再生成新UUID，只处理文件内容

4. file_processing.py:131
   └─> ✅ 优先使用原始UUID: final_file_uuid = "abc-123"

5. file_metadata_builder.py:96
   └─> ✅ 构建元数据时保持: file_uuid = "abc-123"

6. bus_patient_helpers.py:382
   └─> ✅ 保存到数据库: file_uuid = "abc-123"

7. 传给 LLM (patient_data_crew.py)
   └─> ✅ 传递: file_uuid = "abc-123"

8. LLM 输出到 structuredcontent
   └─> ✅ 输出: file_uuid = "abc-123"

结果：file_uuid 保持一致！✅
```

---

## 📋 验证步骤

修复完成后，建议通过以下步骤验证：

### 1. 上传新文件并检查

```sql
-- 查看最新上传的文件
SELECT
    id,
    patient_id,
    file_uuid,
    file_name,
    created_at
FROM bus_patient_files
WHERE is_deleted = false
ORDER BY created_at DESC
LIMIT 5;
```

### 2. 检查结构化数据

```sql
-- 查看对应的结构化数据
SELECT
    id,
    patient_id,
    data_type,
    conversation_id,
    structuredcontent::text LIKE '%YOUR_FILE_UUID%' AS uuid_found
FROM bus_patient_structured_data
WHERE patient_id = 'YOUR_PATIENT_ID'
    AND is_deleted = false;
```

### 3. 完整验证查询

```sql
-- 完整的UUID对应关系检查
WITH patient_files AS (
    SELECT
        patient_id,
        file_uuid,
        file_name
    FROM bus_patient_files
    WHERE patient_id = 'YOUR_PATIENT_ID'
        AND is_deleted = false
)
SELECT
    pf.file_uuid,
    pf.file_name,
    psd.data_type,
    psd.structuredcontent::text LIKE '%' || pf.file_uuid || '%' AS uuid_in_content
FROM patient_files pf
CROSS JOIN bus_patient_structured_data psd
WHERE psd.patient_id = 'YOUR_PATIENT_ID'
    AND psd.is_deleted = false
    AND psd.data_type IN ('timeline', 'journey');
```

---

## 🚨 注意事项

### 特殊情况：zip/PDF 子文件

对于 **zip 文件** 和 **PDF 带图片模式** 处理出的子文件：

- **主 zip/PDF 文件**: 使用原始 UUID
- **子文件（如 zip 中的图片、PDF 的页面图片）**: 生成新的 UUID（合理的，因为它们是新的文件记录）

这种情况是正常的，不需要修复。

### 检查点

如果修复后仍然发现 `file_uuid` 不一致，请检查：

1. **是否是子文件**: zip/PDF 的子文件会有新的 UUID
2. **是否有其他代码路径**: 可能还有其他地方在修改 `file_uuid`
3. **数据库中的旧数据**: 修复只影响新上传的文件

---

## 📅 修复信息

- **修复日期**: 2025-12-25
- **修复人**: Claude Code
- **影响范围**: 所有新上传的文件
- **向后兼容**: 是（不影响已有数据）

---

## 🔗 相关文件

- `app/utils/file_processing.py` - 文件处理主逻辑
- `src/custom_tools/extract_content_from_path.py` - 文件内容提取器
- `app/utils/file_processing_manager.py` - 文件处理管理器
- `app/utils/file_metadata_builder.py` - 文件元数据构建器
- `app/models/bus_patient_helpers.py` - 数据库保存逻辑

---

## ✅ 测试建议

1. 上传一个新的 PDF 文件
2. 检查 `bus_patient_files` 表中的 `file_uuid`
3. 处理完成后，检查 `bus_patient_structured_data` 表中的 `structuredcontent`
4. 确认两者的 `file_uuid` 一致

预期结果：两个表中的 `file_uuid` 应该完全一致。
