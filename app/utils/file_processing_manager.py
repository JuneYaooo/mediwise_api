"""
文件处理管理器
协调文件上传、内容提取、元数据构建等操作
"""
import os
import shutil
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional
from app.utils.file_processing import FileContentExtractor
from app.utils.qiniu_upload_service import QiniuUploadService
from app.utils.file_metadata_builder import FileMetadataBuilder
from app.config.file_constants import MAX_CONCURRENT_FILE_WORKERS
from src.utils.logger import BeijingLogger

logger = BeijingLogger().get_logger()


class FileProcessingManager:
    """文件处理管理器，整合所有文件相关操作"""

    def __init__(self):
        self.upload_service = QiniuUploadService()
        self.extractor = FileContentExtractor()
        self.metadata_builder = FileMetadataBuilder()

    def process_files(self, files: List[Dict], conversation_id: str, progress_callback=None) -> tuple[List[Dict], List[str], List[Dict]]:
        """
        处理文件上传、提取和元数据构建的完整流程

        Args:
            files: 原始文件列表
            conversation_id: 会话ID
            progress_callback: 进度回调函数，接收 (current, total, message, file_info) 参数

        Returns:
            (formatted_files, uploaded_file_ids, extracted_file_results)
        """
        if not files:
            return [], [], []

        total_files = len(files)

        # 第一步：上传文件到七牛云（带进度回调）
        formatted_files = self._upload_files(files, conversation_id, progress_callback, total_files)

        # 提取已上传文件的UUID
        uploaded_file_ids = [f.get('file_uuid') for f in formatted_files if f.get('file_uuid')]

        # 通知文件上传完成
        if progress_callback:
            progress_callback(
                current=total_files,
                total=total_files,
                message=f"✅ 所有文件已上传到云存储（{total_files}/{total_files}），开始提取内容",
                file_info=None,
                stage='upload_complete'
            )

        # 第二步：提取文件内容
        extracted_file_results = []
        if formatted_files:
            extracted_file_results = self._extract_file_contents(formatted_files)

            # 第三步：上传zip子文件
            if extracted_file_results:
                extracted_file_results = self._process_zip_subfiles(
                    extracted_file_results, conversation_id
                )

            # 第四步：清理临时文件
            self._cleanup_temp_files(formatted_files, extracted_file_results)

        return formatted_files, uploaded_file_ids, extracted_file_results

    def _upload_files(self, files: List[Dict], conversation_id: str, progress_callback=None, total_files=None) -> List[Dict]:
        """
        上传文件到七牛云

        Args:
            files: 原始文件列表
            conversation_id: 会话ID
            progress_callback: 进度回调函数
            total_files: 文件总数

        Returns:
            格式化的文件信息列表
        """
        formatted_files = []
        total = total_files or len(files)

        for idx, file in enumerate(files, 1):
            file_name = file.get("file_name", "未知文件")
            file_size = file.get("file_size", 0)

            # 通知开始处理当前文件
            if progress_callback:
                size_mb = file_size / (1024 * 1024) if file_size else 0
                progress_callback(
                    current=idx,
                    total=total,
                    message=f"☁️ 正在上传文件 {idx}/{total}: {file_name} ({size_mb:.2f}MB)",
                    file_info={'file_name': file_name, 'file_size': file_size},
                    stage='uploading'
                )

            file_uuid = str(uuid.uuid4())

            # 处理文件上传
            file_info = self.upload_service.process_file_upload(
                file, conversation_id, file_uuid
            )

            if file_info:
                formatted_files.append(file_info)
            else:
                # 上传失败，创建备用文件信息
                fallback_info = self._create_fallback_file_info(file, file_uuid)
                if fallback_info:
                    formatted_files.append(fallback_info)

            # 通知当前文件处理完成
            if progress_callback:
                progress_callback(
                    current=idx,
                    total=total,
                    message=f"✅ 文件 {idx}/{total} 已上传到云存储: {file_name}",
                    file_info=file_info or fallback_info,
                    stage='uploaded'
                )

        logger.info(f"成功处理 {len(formatted_files)}/{len(files)} 个文件上传")
        return formatted_files

    def _create_fallback_file_info(self, file: Dict, file_uuid: str) -> Optional[Dict]:
        """
        为上传失败的文件创建备用信息

        Args:
            file: 原始文件信息
            file_uuid: 文件UUID

        Returns:
            备用文件信息
        """
        file_name = file.get("file_name", "")
        file_ext = self.upload_service.get_file_extension(
            file_name, file.get("file_type", "")
        )
        file_extension = file_ext.lstrip('.').lower() if file_ext else ""

        qiniu_key = f"{file_uuid}{file_ext}" if file_ext else file_uuid

        return {
            "file_id": file_uuid,
            "file_uuid": file_uuid,
            "file_name": file_name,
            "file_url": file.get("file_url"),
            "file_extension": file_extension,
            "file_type": file.get("file_type"),
            "file_size": file.get("file_size"),
            "file_content": file.get("file_content"),
            "cloud_storage_url": file.get("file_url"),
            "qiniu_key": qiniu_key,
            "file_path": None,
            "temp_file_created": False
        }

    def _extract_file_contents(self, formatted_files: List[Dict]) -> List[Dict]:
        """
        提取文件内容

        Args:
            formatted_files: 格式化的文件信息列表

        Returns:
            提取结果列表
        """
        logger.info(f"开始提取 {len(formatted_files)} 个文件的内容")

        try:
            extracted_results = self.extractor.process_files_concurrently(
                formatted_files, max_workers=MAX_CONCURRENT_FILE_WORKERS
            )

            if extracted_results:
                logger.info(f"成功提取了 {len(extracted_results)} 个文件的内容")

                # 🚨🚨🚨 DEBUG: 输出前3个文件的关键字段
                logger.info("=" * 100)
                logger.info("🔍🔍🔍 DEBUG - 提取结果详细信息（前3个文件）")
                logger.info("=" * 100)
                for i, result in enumerate(extracted_results[:3], 1):
                    logger.info(f"📄 文件 {i}/{len(extracted_results)}:")
                    logger.info(f"  ├─ file_name: {result.get('file_name')}")
                    logger.info(f"  ├─ file_uuid: {result.get('file_uuid')}")
                    logger.info(f"  ├─ source_type: {result.get('source_type')}")
                    logger.info(f"  ├─ is_from_zip: {result.get('is_from_zip')}")
                    logger.info(f"  ├─ extraction_mode: {result.get('extraction_mode')}")
                    logger.info(f"  ├─ original_file_path: {result.get('original_file_path')}")
                    logger.info(f"  ├─ temp_file_available: {result.get('temp_file_available')}")
                    logger.info(f"  └─ temp_file_path: {result.get('temp_file_path')}")
                logger.info("=" * 100)

                return extracted_results
            else:
                logger.warning("未能提取任何文件内容")
                return []

        except Exception as e:
            logger.error(f"文件内容提取失败: {str(e)}")
            return []

    def _process_zip_subfiles(self, extracted_results: List[Dict],
                              conversation_id: str) -> List[Dict]:
        """
        处理zip文件和PDF文件的子文件上传

        Args:
            extracted_results: 提取结果列表
            conversation_id: 会话ID

        Returns:
            更新后的提取结果列表
        """
        # 🚨🚨🚨 DEBUG: 在分类前输出第一个文件的详细信息
        logger.info("=" * 100)
        logger.info("🔍🔍🔍 DEBUG - 开始文件分类，第一个文件的完整信息:")
        logger.info("=" * 100)
        if extracted_results:
            first_file = extracted_results[0]
            logger.info(f"📄 第一个文件:")
            logger.info(f"  ├─ file_name: {first_file.get('file_name')}")
            logger.info(f"  ├─ file_uuid: {first_file.get('file_uuid')}")
            logger.info(f"  ├─ source_type: {first_file.get('source_type')}")
            logger.info(f"  ├─ is_from_zip: {first_file.get('is_from_zip')}")
            logger.info(f"  ├─ extraction_mode: {first_file.get('extraction_mode')}")
            logger.info(f"  ├─ original_file_path 存在: {bool(first_file.get('original_file_path'))}")
            logger.info(f"  ├─ original_file_path 值: {first_file.get('original_file_path')}")
            logger.info(f"  └─ temp_file_available: {first_file.get('temp_file_available')}")
        logger.info("=" * 100)

        # 分类文件（优先级：source_type > is_from_zip）
        zip_files = [f for f in extracted_results if f.get('file_name', '').lower().endswith('.zip')]
        pdf_files = [f for f in extracted_results if f.get('extraction_mode') == 'with_images']  # PDF本身（带图片模式）

        # PDF提取/渲染的图片（无论是否来自ZIP）
        pdf_extracted_images = [
            f for f in extracted_results
            if f.get('source_type') in ['extracted_from_pdf', 'rendered_pdf_page']
        ]

        # ZIP子文件（排除PDF提取的图片）
        sub_files = [
            f for f in extracted_results
            if f.get('is_from_zip')
            and f.get('source_type') not in ['extracted_from_pdf', 'rendered_pdf_page']
        ]

        other_files = [
            f for f in extracted_results
            if not f.get('is_from_zip')
            and not f.get('file_name', '').lower().endswith('.zip')
            and f.get('source_type') not in ['extracted_from_pdf', 'rendered_pdf_page']
            and f.get('extraction_mode') != 'with_images'
        ]

        logger.info(
            f"文件分类: zip文件 {len(zip_files)} 个, "
            f"PDF文件(带图片) {len(pdf_files)} 个, "
            f"ZIP子文件 {len(sub_files)} 个, "
            f"PDF提取图片 {len(pdf_extracted_images)} 个, "
            f"其他文件 {len(other_files)} 个"
        )

        # 🚨🚨🚨 DEBUG: 输出分类详情
        logger.info("=" * 100)
        logger.info("🔍🔍🔍 DEBUG - 文件分类详情:")
        logger.info("=" * 100)

        # 🚨 DEBUG: 如果有PDF提取图片，输出第一个的详细信息
        if pdf_extracted_images:
            logger.info(f"✅ PDF提取图片 {len(pdf_extracted_images)} 个，第1个示例:")
            first_pdf_img = pdf_extracted_images[0]
            logger.info(f"  ├─ file_name: {first_pdf_img.get('file_name')}")
            logger.info(f"  ├─ source_type: {first_pdf_img.get('source_type')}")
            logger.info(f"  ├─ original_file_path: {first_pdf_img.get('original_file_path')}")
            logger.info(f"  ├─ temp_file_path: {first_pdf_img.get('temp_file_path')}")
            logger.info(f"  └─ temp_file_available: {first_pdf_img.get('temp_file_available')}")
        else:
            logger.info("❌ 没有PDF提取图片")

        # 🚨 DEBUG: 如果有ZIP子文件，输出第一个的详细信息
        if sub_files:
            logger.info(f"✅ ZIP子文件 {len(sub_files)} 个，第1个示例:")
            first_sub = sub_files[0]
            logger.info(f"  ├─ file_name: {first_sub.get('file_name')}")
            logger.info(f"  ├─ source_type: {first_sub.get('source_type')}")
            logger.info(f"  ├─ is_from_zip: {first_sub.get('is_from_zip')}")
            logger.info(f"  ├─ original_file_path: {first_sub.get('original_file_path')}")
            logger.info(f"  └─ temp_file_available: {first_sub.get('temp_file_available')}")
        else:
            logger.info("❌ 没有ZIP子文件")

        logger.info("=" * 100)

        # 处理原始zip文件上传
        self._upload_zip_files(zip_files)

        # 处理PDF文件上传（PDF本身）
        self._upload_pdf_files(pdf_files)

        # 处理ZIP子文件上传
        self._upload_subfiles(sub_files, conversation_id)

        # 处理PDF提取的图片上传
        self._upload_pdf_images(pdf_extracted_images, conversation_id)

        # 处理其他文件上传
        self._upload_other_files(other_files, conversation_id)

        # 重新组装结果
        final_results = zip_files + pdf_files + sub_files + pdf_extracted_images + other_files

        # 输出上传统计
        self._log_upload_statistics(sub_files, other_files, pdf_extracted_images)

        return final_results

    def _upload_zip_files(self, zip_files: List[Dict]) -> None:
        """上传原始zip文件"""
        for zip_file in zip_files:
            if zip_file.get('cloud_storage_url') and zip_file.get('uploaded_to_qiniu'):
                continue

            zip_file_uuid = zip_file.get('file_uuid')
            zip_file_name = zip_file.get('file_name', '未知zip文件')
            zip_file_path = zip_file.get('file_path')

            if not zip_file_path or not os.path.exists(zip_file_path):
                logger.warning(f"⚠️ ZIP文件路径不存在，跳过上传: {zip_file_path}")
                zip_file['upload_skipped'] = True
                zip_file['skip_reason'] = 'ZIP文件路径不存在'
                continue

            try:
                file_ext = os.path.splitext(zip_file_name)[1]
                qiniu_key = f"{zip_file_uuid}{file_ext}"

                success, cloud_url, error = self.upload_service.upload_file(
                    zip_file_path, qiniu_key
                )

                if success:
                    zip_file['file_url'] = cloud_url
                    zip_file['cloud_storage_url'] = cloud_url
                    zip_file['qiniu_key'] = qiniu_key
                    zip_file['uploaded_to_qiniu'] = True
                    logger.info(f"✅ ZIP文件上传成功: {zip_file_name} -> {cloud_url}")
                else:
                    logger.error(f"❌ ZIP文件上传失败: {zip_file_name}, 错误: {error}")
                    zip_file['upload_failed'] = True

            except Exception as e:
                logger.error(f"处理ZIP文件上传时出错: {zip_file_name}, 错误: {str(e)}")
                zip_file['upload_failed'] = True
                zip_file['upload_error'] = str(e)

    def _upload_subfiles(self, sub_files: List[Dict], conversation_id: str) -> None:
        """上传zip子文件"""
        logger.info(f"开始上传 {len(sub_files)} 个ZIP子文件")
        for idx, sub_file in enumerate(sub_files, 1):
            logger.info(f"DEBUG - 准备上传第 {idx}/{len(sub_files)} 个ZIP子文件:")
            logger.info(f"  file_name: {sub_file.get('file_name')}")
            logger.info(f"  file_content 存在: {bool(sub_file.get('file_content'))}")
            logger.info(f"  original_file_path: {sub_file.get('original_file_path')}")
            logger.info(f"  temp_file_available: {sub_file.get('temp_file_available')}")

            if sub_file.get('file_content'):
                self.upload_service.upload_zip_subfile(sub_file, conversation_id)
            else:
                logger.warning(f"  ⚠️ 跳过上传（无file_content）: {sub_file.get('file_name')}")

    def _upload_pdf_files(self, pdf_files: List[Dict]) -> None:
        """上传PDF文件（带图片提取模式）"""
        for pdf_file in pdf_files:
            # PDF本身需要上传
            if pdf_file.get('cloud_storage_url') and pdf_file.get('uploaded_to_qiniu'):
                continue

            pdf_uuid = pdf_file.get('file_uuid')
            pdf_name = pdf_file.get('file_name', '未知PDF文件')
            pdf_path = pdf_file.get('file_path')

            if not pdf_path or not os.path.exists(pdf_path):
                logger.warning(f"⚠️ PDF文件路径不存在，跳过上传: {pdf_path}")
                pdf_file['upload_skipped'] = True
                pdf_file['skip_reason'] = 'PDF文件路径不存在'
                continue

            try:
                file_ext = os.path.splitext(pdf_name)[1]
                qiniu_key = f"{pdf_uuid}{file_ext}"

                success, cloud_url, error = self.upload_service.upload_file(
                    pdf_path, qiniu_key
                )

                if success:
                    pdf_file['file_url'] = cloud_url
                    pdf_file['cloud_storage_url'] = cloud_url
                    pdf_file['qiniu_key'] = qiniu_key
                    pdf_file['uploaded_to_qiniu'] = True
                    logger.info(f"✅ PDF文件上传成功: {pdf_name} -> {cloud_url}")
                else:
                    logger.error(f"❌ PDF文件上传失败: {pdf_name}, 错误: {error}")
                    pdf_file['upload_failed'] = True

            except Exception as e:
                logger.error(f"处理PDF文件上传时出错: {pdf_name}, 错误: {str(e)}")
                pdf_file['upload_failed'] = True
                pdf_file['upload_error'] = str(e)

    def _upload_pdf_images(self, pdf_images: List[Dict], conversation_id: str) -> None:
        """上传从PDF提取的图片"""
        logger.info(f"开始上传 {len(pdf_images)} 张从PDF提取的图片")

        for pdf_image in pdf_images:
            # 确保 original_file_path 正确设置（优先使用 temp_file_path）
            if not pdf_image.get('original_file_path') and pdf_image.get('temp_file_path'):
                pdf_image['original_file_path'] = pdf_image['temp_file_path']

            # 确保 temp_file_available 已设置
            if pdf_image.get('temp_file_path') and os.path.exists(pdf_image.get('temp_file_path', '')):
                pdf_image['temp_file_available'] = True

            self.upload_service.upload_zip_subfile(pdf_image, conversation_id)

            # 如果有裁剪的医学影像，也上传
            if pdf_image.get('cropped_image_available') and pdf_image.get('cropped_image_path'):
                self._upload_cropped_image(pdf_image, conversation_id)

    def _upload_cropped_image(self, image_file: Dict, conversation_id: str) -> None:
        """上传裁剪后的医学影像"""
        cropped_path = image_file.get('cropped_image_path')
        if not cropped_path or not os.path.exists(cropped_path):
            logger.warning(f"裁剪图片路径无效或不存在: {cropped_path}")
            return

        try:
            # 🔧 修复：使用已有的 cropped_image_uuid，如果没有才生成新的
            cropped_uuid = image_file.get('cropped_image_uuid')
            if not cropped_uuid:
                import uuid
                cropped_uuid = str(uuid.uuid4())
                image_file['cropped_image_uuid'] = cropped_uuid
                logger.warning(f"裁剪图片缺少UUID，已生成新UUID: {cropped_uuid}")

            original_filename = image_file.get('file_name', 'image')
            base_name = os.path.splitext(original_filename)[0]
            cropped_filename = f"cropped_{base_name}.jpg"

            qiniu_key = f"{conversation_id}/cropped/{cropped_uuid}.jpg"

            logger.info(f"上传裁剪图片: {cropped_filename} -> {qiniu_key} (UUID: {cropped_uuid})")

            # 上传到七牛云
            success, cloud_url, error = self.upload_service.upload_file(
                cropped_path,
                qiniu_key
            )

            if success:
                # 更新原文件信息，添加裁剪图片URL和UUID
                image_file['cropped_image_url'] = cloud_url
                image_file['cropped_image_uuid'] = cropped_uuid  # 🔧 确保UUID被保存
                logger.info(f"裁剪图片上传成功: {cloud_url}, UUID: {cropped_uuid}")

                # 清理临时文件
                try:
                    os.unlink(cropped_path)
                    temp_dir = image_file.get('cropped_temp_dir')
                    if temp_dir and os.path.exists(temp_dir):
                        os.rmdir(temp_dir)
                    logger.debug(f"清理裁剪图片临时文件: {cropped_path}")
                except Exception as cleanup_error:
                    logger.warning(f"清理裁剪图片临时文件失败: {cleanup_error}")
            else:
                logger.error(f"裁剪图片上传失败: {error}")
                image_file['cropped_image_available'] = False

        except Exception as e:
            logger.error(f"上传裁剪图片时出错: {str(e)}")
            image_file['cropped_image_available'] = False


    def _upload_other_files(self, other_files: List[Dict], conversation_id: str) -> None:
        """上传其他文件"""
        for other_file in other_files:
            if other_file.get('cloud_storage_url') and other_file.get('uploaded_to_qiniu'):
                continue

            other_file_uuid = other_file.get('file_uuid')
            other_file_name = other_file.get('file_name', '未知文件')
            other_file_path = other_file.get('file_path')

            if not other_file_uuid or not other_file_path or not os.path.exists(other_file_path):
                logger.warning(f"⚠️ 非zip文件缺少必要信息，跳过上传: {other_file_name}")
                other_file['upload_skipped'] = True
                other_file['skip_reason'] = '缺少文件UUID或路径'
                continue

            try:
                file_ext = os.path.splitext(other_file_name)[1]
                qiniu_key = f"{other_file_uuid}{file_ext}"

                success, cloud_url, error = self.upload_service.upload_file(
                    other_file_path, qiniu_key
                )

                if success:
                    other_file['file_url'] = cloud_url
                    other_file['cloud_storage_url'] = cloud_url
                    other_file['qiniu_key'] = qiniu_key
                    other_file['uploaded_to_qiniu'] = True
                    other_file['upload_method'] = 'direct_original_file'
                    logger.info(f"✅ 非zip文件上传成功: {other_file_name} -> {cloud_url}")

                    # 🔧 修复：如果是图片且有裁剪的医学影像，也上传（使用正确的conversation_id）
                    if file_ext.lower() in ['.png', '.jpg', '.jpeg', '.webp', '.heic', '.heif']:
                        if other_file.get('cropped_image_available') and other_file.get('cropped_image_path'):
                            self._upload_cropped_image(other_file, conversation_id)
                else:
                    logger.error(f"❌ 非zip文件上传失败: {other_file_name}, 错误: {error}")
                    other_file['upload_failed'] = True
                    other_file['upload_error'] = error

            except Exception as e:
                logger.error(f"处理非zip文件上传时出错: {other_file_name}, 错误: {str(e)}")
                other_file['upload_failed'] = True
                other_file['upload_error'] = str(e)

    def _log_upload_statistics(self, sub_files: List[Dict], other_files: List[Dict],
                              pdf_images: List[Dict] = None) -> None:
        """记录上传统计信息"""
        # zip子文件统计
        uploaded_sub = [f for f in sub_files if f.get('uploaded_to_qiniu')]
        skipped_sub = [f for f in sub_files if f.get('upload_skipped')]
        failed_sub = [f for f in sub_files if f.get('upload_failed')]

        if sub_files:
            logger.info(f"zip子文件统计: 总计 {len(sub_files)} 个")
            logger.info(f"  ✅ 成功上传: {len(uploaded_sub)} 个")
            logger.info(f"  ⚠️ 跳过上传: {len(skipped_sub)} 个")
            logger.info(f"  ❌ 上传失败: {len(failed_sub)} 个")

        # PDF提取图片统计（新增）
        if pdf_images:
            uploaded_pdf_imgs = [f for f in pdf_images if f.get('uploaded_to_qiniu')]
            skipped_pdf_imgs = [f for f in pdf_images if f.get('upload_skipped')]
            failed_pdf_imgs = [f for f in pdf_images if f.get('upload_failed')]

            logger.info(f"PDF提取图片统计: 总计 {len(pdf_images)} 个")
            logger.info(f"  ✅ 成功上传: {len(uploaded_pdf_imgs)} 个")
            logger.info(f"  ⚠️ 跳过上传: {len(skipped_pdf_imgs)} 个")
            logger.info(f"  ❌ 上传失败: {len(failed_pdf_imgs)} 个")

        # 非zip文件统计
        uploaded_other = [f for f in other_files if f.get('uploaded_to_qiniu')]
        skipped_other = [f for f in other_files if f.get('upload_skipped')]
        failed_other = [f for f in other_files if f.get('upload_failed')]

        if other_files:
            logger.info(f"非zip文件统计: 总计 {len(other_files)} 个")
            logger.info(f"  ✅ 成功上传: {len(uploaded_other)} 个")
            logger.info(f"  ⚠️ 跳过上传: {len(skipped_other)} 个")
            logger.info(f"  ❌ 上传失败: {len(failed_other)} 个")

    def _cleanup_temp_files(self, formatted_files: List[Dict],
                           extracted_results: List[Dict]) -> None:
        """
        清理临时文件

        Args:
            formatted_files: 格式化的文件信息列表
            extracted_results: 提取结果列表
        """
        # 清理formatted_files中的临时文件
        temp_files_cleaned = 0
        for file_info in formatted_files:
            if file_info.get('temp_file_created') and file_info.get('file_path'):
                try:
                    temp_file_path = file_info['file_path']
                    if os.path.exists(temp_file_path):
                        os.unlink(temp_file_path)
                        temp_files_cleaned += 1
                        logger.debug(f"Cleaned temp file: {temp_file_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean temp file {file_info.get('file_path')}: {str(e)}")

        if temp_files_cleaned > 0:
            logger.info(f"清理了 {temp_files_cleaned} 个临时文件")

        # 清理zip文件的持久临时目录
        persistent_temp_dirs = set()
        for result in extracted_results:
            if isinstance(result, dict) and result.get('cleanup_temp_dir'):
                persistent_temp_dirs.add(result['cleanup_temp_dir'])

        persistent_dirs_cleaned = 0
        for temp_dir in persistent_temp_dirs:
            try:
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                    persistent_dirs_cleaned += 1
                    logger.info(f"清理了zip持久临时目录: {temp_dir}")
            except Exception as e:
                logger.warning(f"清理zip持久临时目录失败 {temp_dir}: {str(e)}")

        if persistent_dirs_cleaned > 0:
            logger.info(f"总计清理了 {persistent_dirs_cleaned} 个zip持久临时目录")
