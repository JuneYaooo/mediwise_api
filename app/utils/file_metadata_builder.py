"""
文件元数据构建工具
用于构建raw_files_data等文件元数据
"""
import time
from typing import List, Dict, Any
from app.config.file_constants import (
    IMAGE_EXTENSIONS, DOCUMENT_EXTENSIONS, TEXT_EXTENSIONS
)
from app.utils.timezone_utils import get_beijing_now_naive
from src.utils.logger import BeijingLogger

logger = BeijingLogger().get_logger()


class FileMetadataBuilder:
    """文件元数据构建类"""

    @staticmethod
    def generate_extracted_text(file_content: str, original_filename: str,
                               file_type: str, file_extension: str,
                               extraction_failed: bool, parent_zip: str = "") -> str:
        """
        为空内容或提取失败的文件生成描述性文本

        Args:
            file_content: 文件内容
            original_filename: 原始文件名
            file_type: 文件类型
            file_extension: 文件扩展名
            extraction_failed: 是否提取失败
            parent_zip: 来源zip文件名

        Returns:
            描述性文本
        """
        if file_content and file_content.strip():
            return file_content

        # 生成描述性内容
        if extraction_failed:
            extracted_text = f"文件名: {original_filename}\n文件类型: {file_type}\n状态: 内容提取失败，但文件存在"
            if parent_zip:
                extracted_text += f"\n来源: {parent_zip}"
        else:
            extracted_text = f"文件名: {original_filename}\n文件类型: {file_type}\n状态: 文件内容为空"
            if parent_zip:
                extracted_text += f"\n来源: {parent_zip}"

        # 根据文件扩展名添加可能的内容描述
        if file_extension in DOCUMENT_EXTENSIONS or file_extension == 'pdf':
            extracted_text += "\n可能包含: 文档内容、诊断报告、检验结果等"
        elif file_extension in IMAGE_EXTENSIONS:
            extracted_text += "\n可能包含: 医学影像、检查图片、病理切片等"
        elif file_extension in TEXT_EXTENSIONS:
            extracted_text += "\n可能包含: 文本记录、病历信息等"
        elif file_extension in ['xlsx', 'xls', 'csv']:
            extracted_text += "\n可能包含: 数据表格、检验数值、统计信息等"
        elif file_extension == 'zip':
            extracted_text += "\n可能包含: 压缩包，包含多个医疗相关文件"

        return extracted_text

    @classmethod
    def build_raw_file_item(cls, result: Dict) -> Dict:
        """
        构建单个文件的raw_files_data项

        Args:
            result: 文件提取结果

        Returns:
            raw_files_data项
        """
        original_filename = result.get('file_name', '')
        file_ext = result.get('file_extension', '')
        sub_file_uuid = result.get('file_uuid')

        # 构建上传文件名
        if file_ext:
            upload_filename = f"{sub_file_uuid}.{file_ext}"
        else:
            upload_filename = sub_file_uuid

        file_content = result.get('file_content', '')
        extracted_text = cls.generate_extracted_text(
            file_content=file_content,
            original_filename=original_filename,
            file_type=result.get('file_type', '其他'),
            file_extension=file_ext,
            extraction_failed=result.get('extraction_failed', False),
            parent_zip=result.get('parent_zip_file', '')
        )

        raw_file_item = {
            # 🔧 关键字段：保留原始字段名，供 save_patient_files 使用
            "file_uuid": sub_file_uuid,
            "file_name": original_filename,           # ✅ 保留原字段名（而非改为 filename）
            "file_url": result.get('file_url'),       # ✅ 保留原字段名（而非改为 cloud_storage_url）
            "file_path": result.get('file_path'),     # ✅ 新增：保留文件路径
            "file_hash": result.get('file_hash'),     # ✅ 新增：保留文件哈希（用于去重）

            # 兼容字段：为其他模块提供备用字段名
            "filename": original_filename,
            "upload_filename": upload_filename,
            "cloud_storage_url": result.get('file_url'),

            "file_extension": file_ext,
            "file_type": result.get('file_type'),
            "has_medical_image": result.get('has_medical_image', False),
            "file_size": len(file_content) if file_content else 0,
            "file_content": file_content,
            "extracted_text": extracted_text,
            "upload_timestamp": get_beijing_now_naive().strftime('%Y-%m-%dT%H:%M:%S'),  # 🔧 修复：使用北京时间
            "exam_date": result.get('exam_date'),

            # ZIP相关字段
            "parent_zip_file": result.get('parent_zip_file'),
            "parent_zip_uuid": result.get('parent_zip_uuid'),
            "parent_zip_filename": result.get('parent_zip_filename'),
            "is_from_zip": result.get('is_from_zip', False),

            # PDF相关字段
            "source_type": result.get('source_type', 'uploaded'),
            "parent_pdf_uuid": result.get('parent_pdf_uuid'),
            "parent_pdf_filename": result.get('parent_pdf_filename'),
            "is_from_pdf": result.get('is_from_pdf', False),
            "extraction_mode": result.get('extraction_mode'),
            "extracted_image_count": result.get('extracted_image_count'),
            "page_number": result.get('page_number'),
            "image_index_in_page": result.get('image_index_in_page'),

            # 位置信息
            "location": cls.build_location_info(result),

            # 医学影像边界框（用于裁剪）
            "image_bbox": result.get('image_bbox'),

            # 裁剪后的医学影像
            "cropped_image_uuid": result.get('cropped_image_uuid'),
            "cropped_image_path": result.get('cropped_image_path'),
            "cropped_image_filename": result.get('cropped_image_filename'),
            "cropped_image_url": result.get('cropped_image_url'),
            "cropped_image_available": result.get('cropped_image_available', False),

            # 提取状态
            "extraction_failed": result.get('extraction_failed', False),
            "extraction_success": result.get('extraction_success'),
            "extraction_error": result.get('extraction_error'),

            # 会话关联
            "conversation_id": result.get('conversation_id')
        }

        return raw_file_item

    @staticmethod
    def build_location_info(result: Dict) -> Dict:
        """
        构建位置信息

        Args:
            result: 文件提取结果

        Returns:
            位置信息字典
        """
        source_type = result.get('source_type', 'uploaded')

        if source_type == 'extracted_from_pdf':
            # 从PDF提取的图片
            page_number = result.get('page_number')
            image_index = result.get('image_index_in_page', 0)

            if page_number:
                return {
                    "type": "pdf_extracted_image",
                    "page_number": page_number,
                    "image_index_in_page": image_index,
                    "position_in_parent": result.get('position_in_parent', f"page_{page_number}_image_{image_index}"),
                    "description": f"第{page_number}页 图片{image_index + 1}"
                }

        elif source_type == 'uploaded':
            # 用户直接上传
            return {
                "type": "direct_upload",
                "description": "用户直接上传"
            }

        elif result.get('is_from_zip'):
            # 从ZIP提取
            return {
                "type": "zip_extracted",
                "parent_zip": result.get('parent_zip_file'),
                "description": f"来自 {result.get('parent_zip_file', '压缩包')}"
            }

        # 默认
        return {
            "type": "unknown",
            "description": "未知来源"
        }

    @classmethod
    def build_raw_files_data(cls, extracted_file_results: List[Dict]) -> List[Dict]:
        """
        构建raw_files_data列表，确保zip文件在第一个位置

        Args:
            extracted_file_results: 文件提取结果列表

        Returns:
            raw_files_data列表
        """
        zip_raw_data = []
        sub_raw_data = []
        other_raw_data = []

        for result in extracted_file_results:
            raw_file_item = cls.build_raw_file_item(result)

            # 按文件类型分组
            if result.get('is_from_zip'):
                sub_raw_data.append(raw_file_item)
            elif result.get('file_name', '').lower().endswith('.zip'):
                zip_raw_data.append(raw_file_item)
            else:
                other_raw_data.append(raw_file_item)

        # 按顺序组装：zip文件在第一个位置
        raw_files_data = zip_raw_data + sub_raw_data + other_raw_data

        logger.info(
            f"构建了 {len(raw_files_data)} 个文件的raw_files_data "
            f"(zip: {len(zip_raw_data)}, 子文件: {len(sub_raw_data)}, 其他: {len(other_raw_data)})"
        )

        # 输出统计信息
        cls.log_file_statistics(raw_files_data)

        return raw_files_data

    @staticmethod
    def log_file_statistics(raw_files_data: List[Dict]) -> None:
        """记录文件统计信息"""
        total_count = len(raw_files_data)
        zip_files_count = sum(1 for item in raw_files_data if item.get('is_from_zip'))
        successful_extractions = sum(
            1 for item in raw_files_data
            if not item.get('extraction_failed') and item.get('extracted_text', '').strip()
        )
        failed_extractions = sum(1 for item in raw_files_data if item.get('extraction_failed'))

        logger.info(
            f"文件统计: 总计 {total_count} 个, 来自zip {zip_files_count} 个, "
            f"成功提取 {successful_extractions} 个, 提取失败 {failed_extractions} 个"
        )

        # 输出前几个文件的详细信息
        for i, file_data in enumerate(raw_files_data[:5], 1):
            filename = file_data.get('filename', '未知')
            file_type = file_data.get('file_type', '未知')
            text_length = len(file_data.get('extracted_text', ''))
            is_from_zip = file_data.get('is_from_zip', False)
            extraction_failed = file_data.get('extraction_failed', False)

            status = "✅成功" if not extraction_failed and text_length > 100 else (
                "⚠️失败" if extraction_failed else "📄空内容"
            )
            source = "(来自zip)" if is_from_zip else ""

            logger.info(f"  {i}. {filename} {source} - {file_type} - {status} - {text_length} 字符")

        if len(raw_files_data) > 5:
            logger.info(f"  ... 还有 {len(raw_files_data) - 5} 个文件")

    @staticmethod
    def build_file_info_for_api(extracted_file_results: List[Dict]) -> List[Dict]:
        """
        构建传递给medical_api的文件信息列表

        Args:
            extracted_file_results: 文件提取结果列表

        Returns:
            文件信息列表
        """
        files_to_pass = []

        for extracted in extracted_file_results:
            file_info = {
                "file_id": extracted.get('file_uuid'),
                "file_uuid": extracted.get('file_uuid'),
                "file_name": extracted.get('file_name'),
                "file_url": extracted.get('file_url'),
                "file_extension": extracted.get('file_extension', ''),
                "file_type": extracted.get('file_type', '其他'),
                "has_medical_image": extracted.get('has_medical_image', False),
                "file_size": len(extracted.get('file_content', '')) if extracted.get('file_content') else 0,
                "file_content": extracted.get('file_content', ''),  # 🚨 新增：保留file_content
                "extracted_text": extracted.get('extracted_text', ''),
                "file_preview": extracted.get('file_preview', ''),
                "ai_file_type": extracted.get('file_type', '其他'),
                "exam_date": extracted.get('exam_date'),
                "extraction_time": extracted.get('extraction_time'),
                "parent_zip_file": extracted.get('parent_zip_file'),
                "is_from_zip": extracted.get('is_from_zip', False),
                "extraction_failed": extracted.get('extraction_failed', False),

                # PDF相关字段
                "source_type": extracted.get('source_type', 'uploaded'),
                "parent_pdf_uuid": extracted.get('parent_pdf_uuid'),
                "parent_pdf_filename": extracted.get('parent_pdf_filename'),

                # 🚨 关键修复：添加文件路径字段，用于上传二进制文件
                "original_file_path": extracted.get('original_file_path'),
                "temp_file_path": extracted.get('temp_file_path'),
                "temp_file_available": extracted.get('temp_file_available', False),
                "persistent_temp_file": extracted.get('persistent_temp_file', False),
                "cleanup_temp_dir": extracted.get('cleanup_temp_dir'),

                # 裁剪医学影像信息
                "cropped_image_uuid": extracted.get('cropped_image_uuid'),
                "cropped_image_path": extracted.get('cropped_image_path'),
                "cropped_image_filename": extracted.get('cropped_image_filename'),
                "cropped_image_available": extracted.get('cropped_image_available', False)
            }
            files_to_pass.append(file_info)

        logger.info(f"传递给medical_api的文件数量: {len(files_to_pass)}")

        # 输出前几个文件的信息
        for i, file_info in enumerate(files_to_pass[:3], 1):
            file_name = file_info.get('file_name', '未知')
            is_from_zip = file_info.get('is_from_zip', False)
            extraction_failed = file_info.get('extraction_failed', False)
            text_length = len(file_info.get('extracted_text', ''))

            status = "✅有内容" if text_length > 50 else (
                "⚠️提取失败" if extraction_failed else "📄无内容"
            )
            source = "(来自zip)" if is_from_zip else ""

            logger.info(f"  传递文件 {i}: {file_name} {source} - {status} - {text_length} 字符")

        return files_to_pass

    @staticmethod
    def collect_extraction_statistics(extracted_file_results: List[Dict]) -> Dict[str, Any]:
        """
        收集文件提取统计信息（只统计原始文件，不统计PDF内提取的图片）

        Args:
            extracted_file_results: 文件提取结果列表

        Returns:
            提取统计信息字典，包含：
            - total_files: 总文件数（只计原始文件）
            - successful_extractions: 成功提取数
            - failed_extractions: 失败提取数
            - success_rate: 成功率
            - failed_files: 失败文件详情列表
        """
        # 过滤：只统计原始上传的文件，排除PDF内提取的图片
        original_files = [
            result for result in extracted_file_results
            if result.get('source_type') not in ['extracted_from_pdf', 'rendered_pdf_page']
        ]

        total_files = len(original_files)
        successful_count = 0
        failed_count = 0
        failed_files = []

        for result in original_files:
            # 使用extraction_success字段判断是否成功
            extraction_success = result.get('extraction_success', None)

            # 如果有extraction_success字段，直接使用
            if extraction_success is not None:
                if extraction_success:
                    successful_count += 1
                else:
                    failed_count += 1
                    failed_files.append({
                        'filename': result.get('file_name', '未知文件'),
                        'file_type': result.get('file_extension', '未知类型'),
                        'error_reason': result.get('extraction_error', '未提供错误原因')
                    })
            # 向后兼容：如果没有extraction_success字段，使用原有的extraction_failed判断
            elif result.get('extraction_failed', False):
                failed_count += 1
                failed_files.append({
                    'filename': result.get('file_name', '未知文件'),
                    'file_type': result.get('file_extension', '未知类型'),
                    'error_reason': '提取失败'
                })
            else:
                # 检查是否有有效内容
                file_content = result.get('file_content', '') or result.get('extracted_text', '')
                has_content = file_content and len(str(file_content).strip()) > 0

                if has_content:
                    successful_count += 1
                else:
                    failed_count += 1
                    failed_files.append({
                        'filename': result.get('file_name', '未知文件'),
                        'file_type': result.get('file_extension', '未知类型'),
                        'error_reason': '提取内容为空'
                    })

        success_rate = (successful_count / total_files * 100) if total_files > 0 else 100

        statistics = {
            'total_files': total_files,
            'successful_extractions': successful_count,
            'failed_extractions': failed_count,
            'success_rate': round(success_rate, 2),
            'failed_files': failed_files,
            'collected_at': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime())
        }

        # 计算PDF内提取的图片数量（用于日志）
        pdf_extracted_count = len(extracted_file_results) - len(original_files)

        logger.info(
            f"文件提取统计（仅统计原始文件）: 总计 {total_files} 个原始文件, 成功 {successful_count} 个, "
            f"失败 {failed_count} 个, 成功率 {success_rate:.2f}%"
        )
        if pdf_extracted_count > 0:
            logger.info(f"  （另有 {pdf_extracted_count} 个PDF内提取的图片未计入统计）")

        if failed_files:
            logger.warning(f"以下 {len(failed_files)} 个文件提取失败:")
            for i, failed_file in enumerate(failed_files[:10], 1):  # 最多显示10个
                logger.warning(
                    f"  {i}. {failed_file['filename']} ({failed_file['file_type']}) - "
                    f"原因: {failed_file['error_reason']}"
                )
            if len(failed_files) > 10:
                logger.warning(f"  ... 还有 {len(failed_files) - 10} 个文件提取失败")

        return statistics

    @staticmethod
    def filter_for_llm_input(raw_files_data: List[Dict]) -> List[Dict]:
        """
        过滤用于LLM输入的文件数据（避免重复）
        跳过从PDF提取/渲染的图片，因为PDF的file_content已包含图片描述

        Args:
            raw_files_data: 原始文件数据列表

        Returns:
            过滤后的文件数据列表
        """
        if not raw_files_data:
            return []

        # 过滤掉从PDF提取或渲染的图片
        filtered = [
            file_item for file_item in raw_files_data
            if file_item.get('source_type') not in ['extracted_from_pdf', 'rendered_pdf_page']
        ]

        logger.info(
            f"过滤用于LLM输入的文件: 原始 {len(raw_files_data)} 个, "
            f"过滤后 {len(filtered)} 个 (跳过 {len(raw_files_data) - len(filtered)} 个PDF提取/渲染的图片)"
        )

        return filtered

    @staticmethod
    def filter_medical_images(raw_files_data: List[Dict]) -> List[Dict]:
        """
        只保留医学影像（包括从PDF提取的）
        用于PPT生成等需要图片URL的场景

        Args:
            raw_files_data: 原始文件数据列表

        Returns:
            医学影像列表
        """
        if not raw_files_data:
            return []

        medical_images = [
            file_item for file_item in raw_files_data
            if file_item.get('has_medical_image')
        ]

        logger.info(f"筛选医学影像: 共 {len(medical_images)} 张")

        return medical_images

    @staticmethod
    def get_pdf_extracted_images(raw_files_data: List[Dict], pdf_uuid: str) -> List[Dict]:
        """
        获取某个PDF提取的所有图片

        Args:
            raw_files_data: 原始文件数据列表
            pdf_uuid: PDF文件的UUID

        Returns:
            该PDF提取的图片列表
        """
        if not raw_files_data or not pdf_uuid:
            return []

        pdf_images = [
            file_item for file_item in raw_files_data
            if file_item.get('parent_pdf_uuid') == pdf_uuid
        ]

        logger.info(f"PDF {pdf_uuid} 提取的图片: {len(pdf_images)} 张")

        return pdf_images

