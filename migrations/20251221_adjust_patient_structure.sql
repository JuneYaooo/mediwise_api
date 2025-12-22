-- =====================================================
-- Mediwise 数据库结构调整脚本 (PostgreSQL)
-- 创建时间: 2025-12-21
-- 说明:
--   1. 删除 bus_patient_structured_data 的 source_file_ids 字段
--   2. 为 bus_patient 添加 raw_file_ids 字段
-- =====================================================

BEGIN;

-- =====================================================
-- 1. 删除 bus_patient_structured_data 的 source_file_ids
-- =====================================================

ALTER TABLE bus_patient_structured_data
DROP COLUMN IF EXISTS source_file_ids;

-- =====================================================
-- 2. 为 bus_patient 添加 raw_file_ids 字段
-- =====================================================

ALTER TABLE bus_patient
ADD COLUMN IF NOT EXISTS raw_file_ids TEXT;

COMMENT ON COLUMN bus_patient.raw_file_ids IS '原始上传文件ID列表（JSON数组格式，如["uuid1","uuid2"]）';

-- =====================================================
-- 3. 验证修改
-- =====================================================

-- 查看 bus_patient 表结构
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM
    information_schema.columns
WHERE
    table_name = 'bus_patient'
ORDER BY
    ordinal_position;

-- 查看 bus_patient_structured_data 表结构
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM
    information_schema.columns
WHERE
    table_name = 'bus_patient_structured_data'
ORDER BY
    ordinal_position;

COMMIT;

-- =====================================================
-- 回滚脚本（如需要）
-- =====================================================

/*
BEGIN;

-- 恢复 source_file_ids
ALTER TABLE bus_patient_structured_data
ADD COLUMN IF NOT EXISTS source_file_ids TEXT;

-- 删除 raw_file_ids
ALTER TABLE bus_patient
DROP COLUMN IF EXISTS raw_file_ids;

COMMIT;
*/
