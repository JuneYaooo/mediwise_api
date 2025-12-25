#!/bin/bash

# 快速检查 file_uuid 对应关系
# 用法: ./quick_check_file_uuid.sh [patient_id]

PATIENT_ID=$1

# 如果没有提供 patient_id，获取最新的
if [ -z "$PATIENT_ID" ]; then
    echo "没有提供 patient_id，获取最新的患者..."
    PATIENT_ID=$(PGPASSWORD='mdtadmin@2025' psql -h 112.124.15.49 -p 5432 -U mdtadmin -d db_mdt -t -c "
        SELECT DISTINCT patient_id
        FROM bus_patient_files
        WHERE is_deleted = false
        ORDER BY created_at DESC
        LIMIT 1
    " | xargs)
fi

echo "========================================================================"
echo "检查患者: $PATIENT_ID"
echo "========================================================================"

echo ""
echo "1️⃣ bus_patient_files 表中的 file_uuid:"
echo "------------------------------------------------------------------------"
PGPASSWORD='mdtadmin@2025' psql -h 112.124.15.49 -p 5432 -U mdtadmin -d db_mdt -c "
SELECT
    file_uuid,
    file_name,
    created_at
FROM bus_patient_files
WHERE patient_id = '$PATIENT_ID'
    AND is_deleted = false
ORDER BY created_at DESC
LIMIT 5;
"

echo ""
echo "2️⃣ bus_patient_structured_data 表中的数据类型:"
echo "------------------------------------------------------------------------"
PGPASSWORD='mdtadmin@2025' psql -h 112.124.15.49 -p 5432 -U mdtadmin -d db_mdt -c "
SELECT
    data_type,
    data_category,
    created_at,
    LENGTH(structuredcontent::text) as content_length
FROM bus_patient_structured_data
WHERE patient_id = '$PATIENT_ID'
    AND is_deleted = false
ORDER BY created_at DESC;
"

echo ""
echo "3️⃣ 检查 structuredcontent 中是否包含 file_uuid:"
echo "------------------------------------------------------------------------"

# 获取第一个 file_uuid
FIRST_UUID=$(PGPASSWORD='mdtadmin@2025' psql -h 112.124.15.49 -p 5432 -U mdtadmin -d db_mdt -t -c "
    SELECT file_uuid
    FROM bus_patient_files
    WHERE patient_id = '$PATIENT_ID'
        AND is_deleted = false
    ORDER BY created_at DESC
    LIMIT 1
" | xargs)

echo "检查 file_uuid: $FIRST_UUID"

PGPASSWORD='mdtadmin@2025' psql -h 112.124.15.49 -p 5432 -U mdtadmin -d db_mdt -c "
SELECT
    data_type,
    data_category,
    CASE
        WHEN structuredcontent::text LIKE '%$FIRST_UUID%'
        THEN '✅ 找到'
        ELSE '❌ 未找到'
    END as uuid_found
FROM bus_patient_structured_data
WHERE patient_id = '$PATIENT_ID'
    AND is_deleted = false
ORDER BY created_at DESC;
"

echo ""
echo "4️⃣ 提取 structuredcontent 中的 file_uuid (如果有):"
echo "------------------------------------------------------------------------"
PGPASSWORD='mdtadmin@2025' psql -h 112.124.15.49 -p 5432 -U mdtadmin -d db_mdt -c "
SELECT
    data_type,
    jsonb_path_query(
        structuredcontent,
        '$.timeline[*].data_blocks[*].items[*].file_uuid'
    ) as file_uuids_in_timeline
FROM bus_patient_structured_data
WHERE patient_id = '$PATIENT_ID'
    AND is_deleted = false
    AND data_type = 'timeline'
LIMIT 1;
"

echo ""
echo "========================================================================"
echo "检查完成"
echo "========================================================================"
