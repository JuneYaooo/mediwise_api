-- 检查 bus_patient_files 和 bus_patient_structured_data 的关联

-- 1. 查看某个患者的文件和结构化数据
-- 替换 'YOUR_PATIENT_ID' 为实际的 patient_id
WITH patient_data AS (
    SELECT
        'YOUR_PATIENT_ID' AS target_patient_id
),
patient_files AS (
    SELECT
        pf.id AS file_record_id,
        pf.file_uuid,
        pf.file_name,
        pf.patient_id,
        pf.conversation_id AS file_conversation_id
    FROM bus_patient_files pf, patient_data pd
    WHERE pf.patient_id = pd.target_patient_id
    AND pf.is_deleted = false
),
structured_data AS (
    SELECT
        psd.id AS structured_data_id,
        psd.patient_id,
        psd.conversation_id AS structured_conversation_id,
        psd.data_type
    FROM bus_patient_structured_data psd, patient_data pd
    WHERE psd.patient_id = pd.target_patient_id
    AND psd.is_deleted = false
)
SELECT
    pf.file_record_id,
    pf.file_uuid,
    pf.file_name,
    pf.patient_id,
    pf.file_conversation_id,
    sd.structured_data_id,
    sd.structured_conversation_id,
    sd.data_type,
    CASE
        WHEN pf.file_conversation_id = sd.structured_conversation_id
        THEN '✅ 匹配'
        ELSE '❌ 不匹配'
    END AS conversation_match
FROM patient_files pf
LEFT JOIN structured_data sd ON pf.patient_id = sd.patient_id
ORDER BY pf.file_name;


-- 2. 查找所有 conversation_id 不匹配的情况
SELECT
    pf.patient_id,
    pf.file_name,
    pf.conversation_id AS file_conversation_id,
    psd.data_type,
    psd.conversation_id AS structured_conversation_id
FROM bus_patient_files pf
LEFT JOIN bus_patient_structured_data psd
    ON pf.patient_id = psd.patient_id
    AND pf.conversation_id = psd.conversation_id
WHERE pf.is_deleted = false
    AND psd.is_deleted = false
    AND pf.conversation_id != psd.conversation_id
LIMIT 20;


-- 3. 统计每个患者的文件数和结构化数据数
SELECT
    p.patient_id,
    p.name,
    COUNT(DISTINCT pf.id) AS file_count,
    COUNT(DISTINCT psd.id) AS structured_data_count,
    COUNT(DISTINCT pf.conversation_id) AS file_conversation_count,
    COUNT(DISTINCT psd.conversation_id) AS structured_conversation_count
FROM bus_patient p
LEFT JOIN bus_patient_files pf ON p.patient_id = pf.patient_id AND pf.is_deleted = false
LEFT JOIN bus_patient_structured_data psd ON p.patient_id = psd.patient_id AND psd.is_deleted = false
WHERE p.is_deleted = false
GROUP BY p.patient_id, p.name
ORDER BY p.created_at DESC
LIMIT 10;
