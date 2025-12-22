-- =====================================================
-- Mediwise 数据库表结构更新脚本 (PostgreSQL)
-- 创建时间: 2025-12-21
-- 说明: 为 bus_patient_files 表添加文件来源追踪、PDF处理、医学影像相关字段
-- =====================================================

-- 执行前请先备份
-- pg_dump -h 112.124.15.49 -U mdtadmin -d db_mdt > backup_20251221.sql

BEGIN;

-- =====================================================
-- 1. 添加基本文件信息字段
-- =====================================================

-- 添加 conversation_id
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS conversation_id VARCHAR(36);
COMMENT ON COLUMN bus_patient_files.conversation_id IS '关联的对话ID（如果通过对话上传）';

-- 添加 upload_filename
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS upload_filename VARCHAR(255);
COMMENT ON COLUMN bus_patient_files.upload_filename IS '上传后的文件名（包含UUID和扩展名）';

-- 添加 file_extension
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS file_extension VARCHAR(20);
COMMENT ON COLUMN bus_patient_files.file_extension IS '文件扩展名（如pdf, jpg, zip）';

-- =====================================================
-- 2. 添加文件来源追踪字段
-- =====================================================

-- 添加 source_type
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS source_type VARCHAR(30) DEFAULT 'uploaded';
COMMENT ON COLUMN bus_patient_files.source_type IS '文件来源类型：uploaded, extracted_from_pdf, extracted_from_zip, rendered_pdf_page';

-- 添加 parent_pdf_uuid
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS parent_pdf_uuid VARCHAR(36);
COMMENT ON COLUMN bus_patient_files.parent_pdf_uuid IS '父PDF文件UUID（如果是从PDF提取的图片）';

-- 添加 parent_pdf_filename
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS parent_pdf_filename VARCHAR(255);
COMMENT ON COLUMN bus_patient_files.parent_pdf_filename IS '父PDF文件名';

-- 添加 parent_zip_uuid
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS parent_zip_uuid VARCHAR(36);
COMMENT ON COLUMN bus_patient_files.parent_zip_uuid IS '父ZIP文件UUID（如果是从ZIP解压的）';

-- 添加 parent_zip_filename
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS parent_zip_filename VARCHAR(255);
COMMENT ON COLUMN bus_patient_files.parent_zip_filename IS '父ZIP文件名';

-- 添加 is_from_zip
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS is_from_zip BOOLEAN DEFAULT FALSE NOT NULL;
COMMENT ON COLUMN bus_patient_files.is_from_zip IS '是否来自ZIP文件';

-- 添加 is_from_pdf
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS is_from_pdf BOOLEAN DEFAULT FALSE NOT NULL;
COMMENT ON COLUMN bus_patient_files.is_from_pdf IS '是否来自PDF文件';

-- =====================================================
-- 3. 添加PDF相关字段
-- =====================================================

-- 添加 extraction_mode
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS extraction_mode VARCHAR(50);
COMMENT ON COLUMN bus_patient_files.extraction_mode IS 'PDF提取模式（text_only, with_images等）';

-- 添加 extracted_image_count
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS extracted_image_count INTEGER;
COMMENT ON COLUMN bus_patient_files.extracted_image_count IS 'PDF提取的图片数量';

-- 添加 page_number
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS page_number INTEGER;
COMMENT ON COLUMN bus_patient_files.page_number IS '在PDF中的页码（如果是PDF提取的图片）';

-- 添加 image_index_in_page
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS image_index_in_page INTEGER;
COMMENT ON COLUMN bus_patient_files.image_index_in_page IS '在页面中的图片索引';

-- =====================================================
-- 4. 添加医学影像相关字段
-- =====================================================

-- 添加 has_medical_image
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS has_medical_image BOOLEAN DEFAULT FALSE NOT NULL;
COMMENT ON COLUMN bus_patient_files.has_medical_image IS '是否包含医学影像';

-- 添加 image_bbox
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS image_bbox JSON;
COMMENT ON COLUMN bus_patient_files.image_bbox IS '医学影像边界框（归一化坐标0-1，用于裁剪）';

-- 添加 cropped_image_uuid
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS cropped_image_uuid VARCHAR(36);
COMMENT ON COLUMN bus_patient_files.cropped_image_uuid IS '裁剪后的医学影像UUID';

-- 添加 cropped_image_url
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS cropped_image_url VARCHAR(500);
COMMENT ON COLUMN bus_patient_files.cropped_image_url IS '裁剪后的医学影像URL';

-- 添加 cropped_image_available
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS cropped_image_available BOOLEAN DEFAULT FALSE NOT NULL;
COMMENT ON COLUMN bus_patient_files.cropped_image_available IS '是否有裁剪后的医学影像';

-- =====================================================
-- 5. 添加提取状态字段
-- =====================================================

-- 添加 extraction_failed
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS extraction_failed BOOLEAN DEFAULT FALSE NOT NULL;
COMMENT ON COLUMN bus_patient_files.extraction_failed IS '内容提取是否失败';

-- 添加 extraction_success
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS extraction_success BOOLEAN;
COMMENT ON COLUMN bus_patient_files.extraction_success IS '内容提取是否成功';

-- 添加 extraction_error
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS extraction_error TEXT;
COMMENT ON COLUMN bus_patient_files.extraction_error IS '提取失败的错误信息';

-- =====================================================
-- 6. 添加上传时间戳
-- =====================================================

-- 添加 upload_timestamp
ALTER TABLE bus_patient_files
ADD COLUMN IF NOT EXISTS upload_timestamp TIMESTAMP;
COMMENT ON COLUMN bus_patient_files.upload_timestamp IS '上传时间戳';

-- =====================================================
-- 7. 创建索引优化查询性能
-- =====================================================

CREATE INDEX IF NOT EXISTS idx_conversation_id ON bus_patient_files(conversation_id);
CREATE INDEX IF NOT EXISTS idx_source_type ON bus_patient_files(source_type);
CREATE INDEX IF NOT EXISTS idx_parent_pdf_uuid ON bus_patient_files(parent_pdf_uuid);
CREATE INDEX IF NOT EXISTS idx_parent_zip_uuid ON bus_patient_files(parent_zip_uuid);
CREATE INDEX IF NOT EXISTS idx_has_medical_image ON bus_patient_files(has_medical_image);
CREATE INDEX IF NOT EXISTS idx_page_number ON bus_patient_files(page_number);

-- =====================================================
-- 8. 验证字段添加结果
-- =====================================================

-- 查看表结构
SELECT
    column_name,
    data_type,
    character_maximum_length,
    is_nullable,
    column_default
FROM
    information_schema.columns
WHERE
    table_name = 'bus_patient_files'
ORDER BY
    ordinal_position;

COMMIT;

-- =====================================================
-- 回滚脚本（如需要）
-- =====================================================

/*
BEGIN;

ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS conversation_id;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS upload_filename;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS file_extension;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS source_type;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS parent_pdf_uuid;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS parent_pdf_filename;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS parent_zip_uuid;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS parent_zip_filename;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS is_from_zip;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS is_from_pdf;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS extraction_mode;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS extracted_image_count;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS page_number;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS image_index_in_page;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS has_medical_image;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS image_bbox;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS cropped_image_uuid;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS cropped_image_url;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS cropped_image_available;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS extraction_failed;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS extraction_success;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS extraction_error;
ALTER TABLE bus_patient_files DROP COLUMN IF EXISTS upload_timestamp;

DROP INDEX IF EXISTS idx_conversation_id;
DROP INDEX IF EXISTS idx_source_type;
DROP INDEX IF EXISTS idx_parent_pdf_uuid;
DROP INDEX IF EXISTS idx_parent_zip_uuid;
DROP INDEX IF EXISTS idx_has_medical_image;
DROP INDEX IF EXISTS idx_page_number;

COMMIT;
*/

-- =====================================================
-- 执行说明
-- =====================================================

/*
执行步骤：
1. 备份数据库: pg_dump -h 112.124.15.49 -U mdtadmin -d db_mdt > backup_20251221.sql
2. 在测试环境执行此脚本
3. 验证表结构和数据完整性
4. 在生产环境执行

影响：
- 对现有数据无影响（仅添加字段，不修改现有数据）
- 新字段都有默认值
- 新增索引可能需要一些时间（取决于表大小）
- 使用 IF NOT EXISTS 确保脚本可重复执行
*/
