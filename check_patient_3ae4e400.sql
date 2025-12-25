-- 检查患者 3ae4e400-f8b2-4c9b-b465-9637e06eabcc 的 file_uuid 对应关系

-- 设置患者ID变量
\set patient_id '3ae4e400-f8b2-4c9b-b465-9637e06eabcc'

\echo '======================================================================================================'
\echo '1️⃣ bus_patient_files 表中的文件'
\echo '======================================================================================================'

SELECT
    file_uuid,
    file_name,
    created_at,
    upload_timestamp
FROM bus_patient_files
WHERE patient_id = :'patient_id'
    AND is_deleted = false
ORDER BY created_at DESC;

\echo ''
\echo '======================================================================================================'
\echo '2️⃣ bus_patient_structured_data 表'
\echo '======================================================================================================'

SELECT
    data_type,
    data_category,
    created_at,
    LENGTH(structuredcontent::text) as content_length
FROM bus_patient_structured_data
WHERE patient_id = :'patient_id'
    AND is_deleted = false
ORDER BY created_at DESC;

\echo ''
\echo '======================================================================================================'
\echo '3️⃣ 检查第一个 file_uuid 是否在 structuredcontent 中'
\echo '======================================================================================================'

-- 获取第一个 file_uuid
WITH first_file AS (
    SELECT file_uuid, file_name
    FROM bus_patient_files
    WHERE patient_id = :'patient_id'
        AND is_deleted = false
    ORDER BY created_at DESC
    LIMIT 1
)
SELECT
    ff.file_uuid,
    ff.file_name,
    psd.data_type,
    psd.data_category,
    CASE
        WHEN psd.structuredcontent::text LIKE '%' || ff.file_uuid || '%'
        THEN '✅ 找到'
        ELSE '❌ 未找到'
    END as uuid_found
FROM first_file ff
CROSS JOIN bus_patient_structured_data psd
WHERE psd.patient_id = :'patient_id'
    AND psd.is_deleted = false;

\echo ''
\echo '======================================================================================================'
\echo '4️⃣ 提取 timeline 中的所有 file_uuid'
\echo '======================================================================================================'

SELECT
    data_type,
    data_category,
    jsonb_path_query(
        structuredcontent,
        '$.timeline[*].data_blocks[*].items[*].file_uuid'
    ) as file_uuid_in_content
FROM bus_patient_structured_data
WHERE patient_id = :'patient_id'
    AND is_deleted = false
    AND data_type = 'timeline'
LIMIT 1;

\echo ''
\echo '======================================================================================================'
\echo '5️⃣ 统计匹配情况'
\echo '======================================================================================================'

WITH patient_files AS (
    SELECT file_uuid
    FROM bus_patient_files
    WHERE patient_id = :'patient_id'
        AND is_deleted = false
),
content_uuids AS (
    SELECT DISTINCT jsonb_path_query(
        structuredcontent,
        '$.timeline[*].data_blocks[*].items[*].file_uuid'
    )::text AS file_uuid
    FROM bus_patient_structured_data
    WHERE patient_id = :'patient_id'
        AND is_deleted = false
        AND data_type = 'timeline'
)
SELECT
    (SELECT COUNT(*) FROM patient_files) as files_count,
    (SELECT COUNT(*) FROM content_uuids) as content_uuids_count,
    (SELECT COUNT(*)
     FROM patient_files pf
     JOIN content_uuids cu ON pf.file_uuid = cu.file_uuid::text
    ) as matched_count;

\echo ''
\echo '======================================================================================================'
\echo '6️⃣ 显示不匹配的 file_uuid'
\echo '======================================================================================================'

-- 在 files 表中但不在 content 中的
\echo '在 bus_patient_files 中但不在 structuredcontent 中的 file_uuid:'

WITH content_uuids AS (
    SELECT DISTINCT trim(both '"' from jsonb_path_query(
        structuredcontent,
        '$.timeline[*].data_blocks[*].items[*].file_uuid'
    )::text) AS file_uuid
    FROM bus_patient_structured_data
    WHERE patient_id = :'patient_id'
        AND is_deleted = false
        AND data_type = 'timeline'
)
SELECT
    pf.file_uuid,
    pf.file_name,
    pf.created_at
FROM bus_patient_files pf
WHERE pf.patient_id = :'patient_id'
    AND pf.is_deleted = false
    AND pf.file_uuid NOT IN (SELECT file_uuid FROM content_uuids WHERE file_uuid IS NOT NULL);

\echo ''
\echo '在 structuredcontent 中但不在 bus_patient_files 中的 file_uuid:'

WITH patient_files AS (
    SELECT file_uuid
    FROM bus_patient_files
    WHERE patient_id = :'patient_id'
        AND is_deleted = false
),
content_uuids AS (
    SELECT DISTINCT trim(both '"' from jsonb_path_query(
        structuredcontent,
        '$.timeline[*].data_blocks[*].items[*].file_uuid'
    )::text) AS file_uuid
    FROM bus_patient_structured_data
    WHERE patient_id = :'patient_id'
        AND is_deleted = false
        AND data_type = 'timeline'
)
SELECT
    cu.file_uuid
FROM content_uuids cu
WHERE cu.file_uuid NOT IN (SELECT file_uuid FROM patient_files)
    AND cu.file_uuid IS NOT NULL;

\echo ''
\echo '======================================================================================================'
\echo '检查完成'
\echo '======================================================================================================'
