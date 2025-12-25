# 患者 3ae4e400-f8b2-4c9b-b465-9637e06eabcc file_uuid 检查指南

## 🔍 如何检查

由于环境限制，我无法直接运行数据库查询。请你在**有数据库访问权限**的环境中运行以下检查：

---

## 方法 1: 使用 SQL 脚本（推荐）

```bash
psql -h 112.124.15.49 -p 5432 -U mdtadmin -d db_mdt -f check_patient_3ae4e400.sql
```

这个脚本会显示：
1. bus_patient_files 表中的所有文件
2. bus_patient_structured_data 表中的数据
3. file_uuid 是否在 structuredcontent 中
4. 匹配统计
5. 不匹配的 UUID 列表

---

## 方法 2: 手动 SQL 查询

### 步骤 1: 查看文件列表

```sql
SELECT
    file_uuid,
    file_name,
    created_at
FROM bus_patient_files
WHERE patient_id = '3ae4e400-f8b2-4c9b-b465-9637e06eabcc'
    AND is_deleted = false
ORDER BY created_at DESC;
```

**记录结果**: 有多少个文件？第一个 file_uuid 是什么？

---

### 步骤 2: 查看结构化数据

```sql
SELECT
    data_type,
    data_category,
    created_at
FROM bus_patient_structured_data
WHERE patient_id = '3ae4e400-f8b2-4c9b-b465-9637e06eabcc'
    AND is_deleted = false
ORDER BY created_at DESC;
```

**记录结果**: 有哪些类型的数据？最新的是什么时候创建的？

---

### 步骤 3: 检查 file_uuid 是否存在

用步骤1中的第一个 file_uuid 替换 `YOUR_FILE_UUID`:

```sql
SELECT
    data_type,
    CASE
        WHEN structuredcontent::text LIKE '%YOUR_FILE_UUID%'
        THEN '✅ 找到'
        ELSE '❌ 未找到'
    END as found
FROM bus_patient_structured_data
WHERE patient_id = '3ae4e400-f8b2-4c9b-b465-9637e06eabcc'
    AND is_deleted = false;
```

---

### 步骤 4: 提取 timeline 中的 file_uuid

```sql
SELECT
    jsonb_path_query(
        structuredcontent,
        '$.timeline[*].data_blocks[*].items[*].file_uuid'
    ) as file_uuids
FROM bus_patient_structured_data
WHERE patient_id = '3ae4e400-f8b2-4c9b-b465-9637e06eabcc'
    AND is_deleted = false
    AND data_type = 'timeline'
LIMIT 1;
```

**记录结果**: 提取出了哪些 file_uuid？

---

## 🎯 判断标准

### ✅ 正常情况

- **步骤1**: 找到 N 个文件，每个有不同的 file_uuid
- **步骤3**: 所有 file_uuid 都显示 "✅ 找到"
- **步骤4**: 提取出的 file_uuid 与步骤1中的完全匹配

### ❌ 异常情况 A: 完全没有 file_uuid

- **步骤3**: 所有都显示 "❌ 未找到"
- **步骤4**: 返回空结果或 NULL

**原因**: LLM 没有输出 file_uuid 字段

**解决方案**:
1. 检查这是不是**修复前**的旧数据（查看 created_at 是否 < 2025-12-25 13:00:00）
2. 如果是新数据，需要检查 LLM 的提示词配置

---

### ❌ 异常情况 B: file_uuid 不匹配

- **步骤3**: 显示 "❌ 未找到"
- **步骤4**: 提取出的 file_uuid 与步骤1中的不同

**原因**: LLM 生成了不同的 UUID

**解决方案**:
1. 检查是否是修复前的旧数据
2. 查看日志，确认传给 LLM 的 file_uuid
3. 查看 LLM 的原始输出

---

### ⚠️ 异常情况 C: 部分匹配

- **步骤3**: 部分显示 "✅ 找到"，部分 "❌ 未找到"

**原因**:
- 某些文件的数据还未处理完成
- 或者只有部分文件的信息被包含在 timeline 中

---

## 📊 期望结果（修复后）

如果代码修复生效，新上传的文件应该：

```
bus_patient_files.file_uuid = abc-123-def-456
                                    ↓
                              (传给 LLM)
                                    ↓
          structuredcontent.timeline[].data_blocks[].items[].file_uuid = abc-123-def-456
                                    ↓
                                  ✅ 匹配
```

---

## 🔧 根据结果采取行动

### 情况 1: 这是旧数据（created_at < 2025-12-25 13:00:00）

**建议**: 上传一个**新文件**测试，检查新文件的 file_uuid 是否正确

---

### 情况 2: 这是新数据但仍然不匹配

**需要提供的信息**:
1. 步骤1的完整输出（所有 file_uuid）
2. 步骤2的完整输出（数据类型和时间）
3. 步骤3的完整输出（是否找到）
4. 步骤4的完整输出（提取的 UUID）
5. 最新文件的 created_at 时间

有了这些信息，我可以进一步诊断问题。

---

## 💡 快速诊断命令

把以下命令的输出全部复制给我：

```sql
-- 一次性查询所有信息
WITH patient_files AS (
    SELECT
        file_uuid,
        file_name,
        created_at
    FROM bus_patient_files
    WHERE patient_id = '3ae4e400-f8b2-4c9b-b465-9637e06eabcc'
        AND is_deleted = false
    ORDER BY created_at DESC
),
structured_data AS (
    SELECT
        data_type,
        data_category,
        created_at,
        structuredcontent
    FROM bus_patient_structured_data
    WHERE patient_id = '3ae4e400-f8b2-4c9b-b465-9637e06eabcc'
        AND is_deleted = false
    ORDER BY created_at DESC
),
timeline_uuids AS (
    SELECT DISTINCT
        trim(both '"' from jsonb_path_query(
            structuredcontent,
            '$.timeline[*].data_blocks[*].items[*].file_uuid'
        )::text) AS file_uuid
    FROM structured_data
    WHERE data_type = 'timeline'
        AND structuredcontent IS NOT NULL
)
SELECT
    '=== 文件列表 ===' as section,
    NULL as file_uuid,
    NULL as file_name,
    NULL as created_at,
    NULL as data_type,
    NULL as match_status
UNION ALL
SELECT
    '',
    pf.file_uuid,
    pf.file_name,
    pf.created_at,
    NULL,
    CASE
        WHEN tu.file_uuid IS NOT NULL THEN '✅ 匹配'
        ELSE '❌ 不匹配'
    END
FROM patient_files pf
LEFT JOIN timeline_uuids tu ON pf.file_uuid = tu.file_uuid
UNION ALL
SELECT
    '=== 结构化数据 ===' as section,
    NULL, NULL, NULL, NULL, NULL
UNION ALL
SELECT
    '',
    NULL,
    NULL,
    sd.created_at,
    sd.data_type || ' (' || COALESCE(sd.data_category, 'NULL') || ')',
    NULL
FROM structured_data sd
ORDER BY section DESC, created_at DESC NULLS LAST;
```

---

## 📞 后续支持

根据你的查询结果，我可以：
1. 判断是否是旧数据问题
2. 判断是否是 LLM 输出问题
3. 提供针对性的修复方案
4. 如果需要，提供数据修复脚本
