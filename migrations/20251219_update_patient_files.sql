-- =====================================================
-- Mediwise 数据库表结构更新脚本
-- 创建时间: 2025-12-19
-- 说明: 更新 bus_patient_files 表，新增文件来源追踪、PDF处理、医学影像相关字段
-- =====================================================

-- 备份提示
-- 执行前请先备份: mysqldump -u username -p database_name > backup_20251219.sql

-- =====================================================
-- 1. 更新 bus_patient_files 表
-- =====================================================

-- 添加文件基本信息字段
ALTER TABLE bus_patient_files
ADD COLUMN upload_filename VARCHAR(255) COMMENT '上传后的文件名（包含UUID和扩展名）' AFTER file_name;

ALTER TABLE bus_patient_files
ADD COLUMN file_extension VARCHAR(20) COMMENT '文件扩展名（如pdf, jpg, zip）' AFTER upload_filename;

-- 添加关联对话ID
ALTER TABLE bus_patient_files
ADD COLUMN conversation_id VARCHAR(36) COMMENT '关联的对话ID（如果通过对话上传）' AFTER patient_id;

-- 添加文件来源追踪字段
ALTER TABLE bus_patient_files
ADD COLUMN source_type VARCHAR(30) DEFAULT 'uploaded' COMMENT '文件来源类型：uploaded, extracted_from_pdf, extracted_from_zip, rendered_pdf_page' AFTER file_hash;

ALTER TABLE bus_patient_files
ADD COLUMN parent_pdf_uuid VARCHAR(36) COMMENT '父PDF文件UUID（如果是从PDF提取的图片）' AFTER source_type;

ALTER TABLE bus_patient_files
ADD COLUMN parent_pdf_filename VARCHAR(255) COMMENT '父PDF文件名' AFTER parent_pdf_uuid;

ALTER TABLE bus_patient_files
ADD COLUMN parent_zip_uuid VARCHAR(36) COMMENT '父ZIP文件UUID（如果是从ZIP解压的）' AFTER parent_pdf_filename;

ALTER TABLE bus_patient_files
ADD COLUMN parent_zip_filename VARCHAR(255) COMMENT '父ZIP文件名' AFTER parent_zip_uuid;

ALTER TABLE bus_patient_files
ADD COLUMN is_from_zip BOOLEAN DEFAULT FALSE COMMENT '是否来自ZIP文件' AFTER parent_zip_filename;

ALTER TABLE bus_patient_files
ADD COLUMN is_from_pdf BOOLEAN DEFAULT FALSE COMMENT '是否来自PDF文件' AFTER is_from_zip;

-- 添加PDF相关字段
ALTER TABLE bus_patient_files
ADD COLUMN extraction_mode VARCHAR(50) COMMENT 'PDF提取模式（text_only, with_images等）' AFTER is_from_pdf;

ALTER TABLE bus_patient_files
ADD COLUMN extracted_image_count INT COMMENT 'PDF提取的图片数量' AFTER extraction_mode;

ALTER TABLE bus_patient_files
ADD COLUMN page_number INT COMMENT '在PDF中的页码（如果是PDF提取的图片）' AFTER extracted_image_count;

ALTER TABLE bus_patient_files
ADD COLUMN image_index_in_page INT COMMENT '在页面中的图片索引' AFTER page_number;

-- 添加医学影像相关字段
ALTER TABLE bus_patient_files
ADD COLUMN has_medical_image BOOLEAN DEFAULT FALSE COMMENT '是否包含医学影像' AFTER image_index_in_page;

ALTER TABLE bus_patient_files
ADD COLUMN image_bbox JSON COMMENT '医学影像边界框（归一化坐标0-1，用于裁剪）' AFTER has_medical_image;

ALTER TABLE bus_patient_files
ADD COLUMN cropped_image_uuid VARCHAR(36) COMMENT '裁剪后的医学影像UUID' AFTER image_bbox;

ALTER TABLE bus_patient_files
ADD COLUMN cropped_image_url VARCHAR(500) COMMENT '裁剪后的医学影像URL' AFTER cropped_image_uuid;

ALTER TABLE bus_patient_files
ADD COLUMN cropped_image_available BOOLEAN DEFAULT FALSE COMMENT '是否有裁剪后的医学影像' AFTER cropped_image_url;

-- 添加提取状态字段（插入到 extracted_text 之后）
ALTER TABLE bus_patient_files
ADD COLUMN extraction_failed BOOLEAN DEFAULT FALSE COMMENT '内容提取是否失败' AFTER extractedmetadata;

ALTER TABLE bus_patient_files
ADD COLUMN extraction_success BOOLEAN COMMENT '内容提取是否成功' AFTER extraction_failed;

ALTER TABLE bus_patient_files
ADD COLUMN extraction_error TEXT COMMENT '提取失败的错误信息' AFTER extraction_success;

-- 添加上传时间戳
ALTER TABLE bus_patient_files
ADD COLUMN upload_timestamp TIMESTAMP COMMENT '上传时间戳' AFTER uploaded_at;

-- =====================================================
-- 2. 添加索引优化查询性能
-- =====================================================

CREATE INDEX idx_conversation_id ON bus_patient_files(conversation_id);
CREATE INDEX idx_source_type ON bus_patient_files(source_type);
CREATE INDEX idx_parent_pdf_uuid ON bus_patient_files(parent_pdf_uuid);
CREATE INDEX idx_parent_zip_uuid ON bus_patient_files(parent_zip_uuid);
CREATE INDEX idx_has_medical_image ON bus_patient_files(has_medical_image);
CREATE INDEX idx_page_number ON bus_patient_files(page_number);

-- =====================================================
-- 3. 验证脚本 - 检查表结构
-- =====================================================

SELECT
    COLUMN_NAME,
    COLUMN_TYPE,
    IS_NULLABLE,
    COLUMN_DEFAULT,
    COLUMN_COMMENT
FROM
    INFORMATION_SCHEMA.COLUMNS
WHERE
    TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'bus_patient_files'
ORDER BY ORDINAL_POSITION;

-- =====================================================
-- 4. 回滚脚本（如需要）
-- =====================================================

/*
-- 删除新增的字段
ALTER TABLE bus_patient_files DROP COLUMN upload_filename;
ALTER TABLE bus_patient_files DROP COLUMN file_extension;
ALTER TABLE bus_patient_files DROP COLUMN conversation_id;
ALTER TABLE bus_patient_files DROP COLUMN source_type;
ALTER TABLE bus_patient_files DROP COLUMN parent_pdf_uuid;
ALTER TABLE bus_patient_files DROP COLUMN parent_pdf_filename;
ALTER TABLE bus_patient_files DROP COLUMN parent_zip_uuid;
ALTER TABLE bus_patient_files DROP COLUMN parent_zip_filename;
ALTER TABLE bus_patient_files DROP COLUMN is_from_zip;
ALTER TABLE bus_patient_files DROP COLUMN is_from_pdf;
ALTER TABLE bus_patient_files DROP COLUMN extraction_mode;
ALTER TABLE bus_patient_files DROP COLUMN extracted_image_count;
ALTER TABLE bus_patient_files DROP COLUMN page_number;
ALTER TABLE bus_patient_files DROP COLUMN image_index_in_page;
ALTER TABLE bus_patient_files DROP COLUMN has_medical_image;
ALTER TABLE bus_patient_files DROP COLUMN image_bbox;
ALTER TABLE bus_patient_files DROP COLUMN cropped_image_uuid;
ALTER TABLE bus_patient_files DROP COLUMN cropped_image_url;
ALTER TABLE bus_patient_files DROP COLUMN cropped_image_available;
ALTER TABLE bus_patient_files DROP COLUMN extraction_failed;
ALTER TABLE bus_patient_files DROP COLUMN extraction_success;
ALTER TABLE bus_patient_files DROP COLUMN extraction_error;
ALTER TABLE bus_patient_files DROP COLUMN upload_timestamp;

-- 删除索引
DROP INDEX idx_conversation_id ON bus_patient_files;
DROP INDEX idx_source_type ON bus_patient_files;
DROP INDEX idx_parent_pdf_uuid ON bus_patient_files;
DROP INDEX idx_parent_zip_uuid ON bus_patient_files;
DROP INDEX idx_has_medical_image ON bus_patient_files;
DROP INDEX idx_page_number ON bus_patient_files;
*/

-- =====================================================
-- 执行说明
-- =====================================================

/*
执行步骤：
1. 备份数据库
2. 在测试环境执行此脚本
3. 验证表结构和数据完整性
4. 在生产环境执行

影响：
- 对现有数据无影响（仅添加字段，不修改现有数据）
- 新字段都有默认值
- 新增索引可能需要一些时间（取决于表大小）
*/
