"""
文件上传处理工具
处理文件上传到七牛云、文件处理等
"""

import os
import uuid
import time
import base64
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.utils.qiniu_client import create_qiniu_client
from src.utils.logger import BeijingLogger

logger = BeijingLogger().get_logger()


class FileUploadHandler:
    """文件上传处理器"""

    def __init__(self):
        self.qiniu_client = create_qiniu_client()

    def upload_files_to_qiniu(self, files: List[Dict[str, Any]],
                             conversation_id: str) -> tuple[List[Dict], List[str]]:
        """
        上传文件到七牛云

        Args:
            files: 文件列表
            conversation_id: 会话ID

        Returns:
            tuple: (formatted_files, uploaded_file_ids)
        """
        formatted_files = []
        uploaded_file_ids = []

        for file in files:
            try:
                local_file_path = None
                temp_file_created = False
                file_data = None

                # 为每个文件生成唯一UUID
                file_uuid = str(uuid.uuid4())

                # 获取文件信息
                file_name = file.get("file_name", "unknown_file")
                file_content = file.get("file_content")
                file_type = file.get("file_type", "unknown")
                file_size = file.get("file_size", 0)

                # 从文件名中提取文件扩展名
                file_ext = self._extract_file_extension(file_name, file_type)

                # 构造七牛云存储的key
                qiniu_key = f"{file_uuid}{file_ext}"
                cloud_storage_url = None

                # 上传文件到七牛云
                if file_content:
                    try:
                        # 处理不同类型的文件内容
                        local_file_path, file_data, temp_file_created = self._prepare_file_for_upload(
                            file_content, file_uuid, file_ext, conversation_id
                        )

                        if local_file_path:
                            # 上传文件
                            ret, info = self.qiniu_client.upload_file(local_file_path, qiniu_key)
                            if info.status_code == 200:
                                cloud_storage_url = f"http://{self.qiniu_client.bucket_domain}/{qiniu_key}"
                            else:
                                raise Exception(f"上传文件失败: {info}")
                        else:
                            logger.warning(f"⚠️ 跳过文件 - 无法处理文件内容类型: {file_name}")
                            continue
                    except Exception as upload_error:
                        logger.error(f"❌ 文件上传失败: {file_name}, 错误: {str(upload_error)}")
                        continue

                # 只有成功上传才记录文件UUID
                if cloud_storage_url:
                    uploaded_file_ids.append(file_uuid)

                    # 格式化文件信息
                    file_info = {
                        "file_id": file_uuid,
                        "file_uuid": file_uuid,
                        "file_name": file_name,
                        "file_url": cloud_storage_url,
                        "file_extension": file_ext.lstrip('.').lower() if file_ext else "",
                        "file_type": file_type,
                        "file_size": file_size,
                        "file_content": file.get("file_content"),
                        "cloud_storage_url": cloud_storage_url,
                        "qiniu_key": qiniu_key,
                        "file_path": local_file_path,
                        "temp_file_created": temp_file_created
                    }

                    formatted_files.append(file_info)
                    logger.info(f"✅ 文件上传成功: {file_name} -> {cloud_storage_url}")
                else:
                    logger.warning(f"⚠️ 文件上传失败 - 未生成云存储URL: {file_name}")

            except Exception as e:
                logger.error(f"❌ 文件处理异常: {file.get('file_name', 'unknown')}, 错误: {str(e)}")
                continue

        return formatted_files, uploaded_file_ids

    def _extract_file_extension(self, file_name: str, file_type: str) -> str:
        """提取文件扩展名"""
        file_ext = ""
        if file_name and "." in file_name:
            file_ext = os.path.splitext(file_name)[1]
        elif file_type and file_type != "unknown":
            # 如果没有扩展名但有file_type，尝试从file_type推断
            if file_type.startswith("image/"):
                file_ext = f".{file_type.split('/')[-1]}"
            elif file_type.startswith("text/"):
                file_ext = ".txt"
            elif file_type == "application/pdf":
                file_ext = ".pdf"
            elif file_type == "application/json":
                file_ext = ".json"
        return file_ext

    def _prepare_file_for_upload(self, file_content: Any, file_uuid: str, file_ext: str,
                                 conversation_id: str) -> tuple[Optional[str], Optional[bytes], bool]:
        """
        准备文件用于上传

        Returns:
            tuple: (local_file_path, file_data, temp_file_created)
        """
        local_file_path = None
        file_data = None
        temp_file_created = False

        # 如果是已存在的文件路径，直接使用
        if isinstance(file_content, str) and os.path.exists(file_content):
            return file_content, None, False

        # 处理其他类型的内容
        if isinstance(file_content, str) and file_content.startswith('data:'):
            # 处理data URL格式
            header, data = file_content.split(',', 1)
            file_data = base64.b64decode(data)
        elif isinstance(file_content, str):
            # 假设是base64编码的字符串
            try:
                file_data = base64.b64decode(file_content)
            except:
                # 如果不是base64，当作普通字符串处理
                file_data = file_content.encode('utf-8')
        elif isinstance(file_content, bytes):
            # 直接是二进制数据
            file_data = file_content
        else:
            # 其他类型，尝试转换为字符串再编码
            file_data = str(file_content).encode('utf-8')

        # 创建临时文件
        if file_data:
            temp_dir = Path(f"./uploads/temp/{conversation_id}")
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_file_path = temp_dir / f"{file_uuid}{file_ext}"

            with open(temp_file_path, "wb") as temp_f:
                temp_f.write(file_data)
            local_file_path = str(temp_file_path)
            temp_file_created = True
            logger.info(f"Created temp file for upload: {local_file_path}")

        return local_file_path, file_data, temp_file_created

    def upload_sub_files_to_qiniu(self, extracted_files: List[Dict[str, Any]],
                                  conversation_id: str) -> List[Dict[str, Any]]:
        """
        上传子文件（从ZIP提取的文件）到七牛云

        Args:
            extracted_files: 提取的文件列表
            conversation_id: 会话ID

        Returns:
            List: 处理后的文件列表
        """
        zip_files = []
        sub_files = []
        other_files = []

        # 分类文件
        for extracted in extracted_files:
            if extracted.get('is_from_zip'):
                sub_files.append(extracted)
            elif extracted.get('file_name', '').lower().endswith('.zip'):
                zip_files.append(extracted)
            else:
                other_files.append(extracted)

        logger.info(f"文件分类: zip文件 {len(zip_files)} 个, 子文件 {len(sub_files)} 个, 其他文件 {len(other_files)} 个")

        # 处理原始zip文件的上传
        for zip_file in zip_files:
            self._upload_single_zip_file(zip_file)

        # 处理子文件的上传
        additional_extracted_files = []
        for zip_file in zip_files:
            additional_extracted_files.append(zip_file)

        for extracted in sub_files:
            uploaded_file = self._upload_single_sub_file(extracted, conversation_id)
            additional_extracted_files.append(uploaded_file)

        # 处理其他文件的上传
        for other_file in other_files:
            self._upload_single_other_file(other_file)
            additional_extracted_files.append(other_file)

        return additional_extracted_files

    def _upload_single_zip_file(self, zip_file: Dict[str, Any]) -> None:
        """上传单个ZIP文件"""
        zip_file_uuid = zip_file.get('file_uuid')
        zip_file_name = zip_file.get('file_name', '未知zip文件')

        if not zip_file.get('cloud_storage_url') or not zip_file.get('uploaded_to_qiniu'):
            try:
                file_ext = os.path.splitext(zip_file_name)[1]
                qiniu_key = f"{zip_file_uuid}{file_ext}"
                zip_file_path = zip_file.get('file_path')

                if zip_file_path and os.path.exists(zip_file_path):
                    ret, info = self.qiniu_client.upload_file(zip_file_path, qiniu_key)

                    if info.status_code == 200:
                        zip_cloud_url = f"http://{self.qiniu_client.bucket_domain}/{qiniu_key}"
                        zip_file['file_url'] = zip_cloud_url
                        zip_file['cloud_storage_url'] = zip_cloud_url
                        zip_file['qiniu_key'] = qiniu_key
                        zip_file['uploaded_to_qiniu'] = True
                        logger.info(f"✅ ZIP文件上传成功: {zip_file_name} -> {zip_cloud_url}")
                    else:
                        logger.error(f"❌ ZIP文件上传失败: {zip_file_name}, 错误: {info}")
                        zip_file['upload_failed'] = True
                else:
                    logger.warning(f"⚠️ ZIP文件路径不存在，跳过上传: {zip_file_path}")
                    zip_file['upload_skipped'] = True
                    zip_file['skip_reason'] = 'ZIP文件路径不存在'
            except Exception as e:
                logger.error(f"处理ZIP文件上传时出错: {zip_file_name}, 错误: {str(e)}")
                zip_file['upload_failed'] = True
                zip_file['upload_error'] = str(e)

    def _upload_single_sub_file(self, extracted: Dict[str, Any],
                                conversation_id: str) -> Dict[str, Any]:
        """上传单个子文件"""
        if not extracted.get('file_content'):
            return extracted

        try:
            sub_file_uuid = extracted.get('file_uuid')
            sub_file_name = extracted.get('file_name', '未知文件')
            sub_file_content = extracted.get('file_content', '')
            parent_zip_uuid = extracted.get('parent_zip_uuid')
            file_ext = ""

            if sub_file_name and "." in sub_file_name:
                file_ext = os.path.splitext(sub_file_name)[1]

            qiniu_key = f"{sub_file_uuid}{file_ext}"
            file_extension = file_ext.lstrip('.').lower()
            original_file_path = extracted.get('original_file_path')
            temp_file_available = extracted.get('temp_file_available', False)

            # 如果有原始文件路径且文件存在，直接上传原始文件
            if original_file_path and temp_file_available and os.path.exists(original_file_path):
                logger.info(f"📁 直接上传原始文件: {sub_file_name}")
                ret, info = self.qiniu_client.upload_file(original_file_path, qiniu_key)

                if info.status_code == 200:
                    sub_file_cloud_url = f"http://{self.qiniu_client.bucket_domain}/{qiniu_key}"
                    extracted['file_url'] = sub_file_cloud_url
                    extracted['cloud_storage_url'] = sub_file_cloud_url
                    extracted['qiniu_key'] = qiniu_key
                    extracted['uploaded_to_qiniu'] = True
                    extracted['upload_method'] = 'direct_original_file'
                    logger.info(f"✅ 原始文件上传成功: {sub_file_name} -> {sub_file_cloud_url}")
                    return extracted
                else:
                    logger.error(f"❌ 原始文件上传失败: {sub_file_name}, 错误: {info}")

            # 降级策略：根据文件类型处理
            if file_extension in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp', 'heic', 'heif', 'pdf']:
                logger.warning(f"⚠️ 子文件 {sub_file_name} 是二进制文件，且原始文件不可用，跳过上传")
                extracted['upload_skipped'] = True
                extracted['skip_reason'] = '二进制文件且原始文件不可用'
                return extracted

            # 从内容重建文本文件
            temp_dir = Path(f"./uploads/temp/{conversation_id}")
            temp_dir.mkdir(parents=True, exist_ok=True)
            temp_file_path = temp_dir / f"{sub_file_uuid}{file_ext}"

            if file_extension in ['txt', 'md', 'csv', 'json', 'xml', 'html', 'htm']:
                logger.info(f"📝 从提取内容重建文本文件: {sub_file_name}")
                with open(temp_file_path, "w", encoding='utf-8') as temp_f:
                    temp_f.write(sub_file_content)
            elif file_extension in ['docx', 'doc', 'xlsx', 'xls', 'pptx', 'ppt']:
                logger.warning(f"⚠️ 子文件 {sub_file_name} 是Office文档，无法从提取文本重建，跳过上传")
                extracted['upload_skipped'] = True
                extracted['skip_reason'] = 'Office文档无法从提取文本重建'
                return extracted
            else:
                logger.info(f"📄 子文件 {sub_file_name} 类型未知，尝试从提取内容重建")
                with open(temp_file_path, "w", encoding='utf-8') as temp_f:
                    temp_f.write(sub_file_content)

            # 上传重建的文件
            ret, info = self.qiniu_client.upload_file(str(temp_file_path), qiniu_key)

            if info.status_code == 200:
                sub_file_cloud_url = f"http://{self.qiniu_client.bucket_domain}/{qiniu_key}"
                extracted['file_url'] = sub_file_cloud_url
                extracted['cloud_storage_url'] = sub_file_cloud_url
                extracted['qiniu_key'] = qiniu_key
                extracted['uploaded_to_qiniu'] = True
                extracted['upload_method'] = 'reconstructed_from_content'
                logger.info(f"✅ 重建文件上传成功: {sub_file_name} -> {sub_file_cloud_url}")
            else:
                logger.error(f"❌ 子文件上传失败: {sub_file_name}, 错误: {info}")
                extracted['upload_failed'] = True
                extracted['upload_error'] = str(info)

            # 清理临时文件
            try:
                os.unlink(temp_file_path)
            except Exception as e:
                logger.warning(f"清理临时文件失败: {temp_file_path}, 错误: {str(e)}")

        except Exception as e:
            logger.error(f"处理zip子文件上传时出错: {extracted.get('file_name', '未知')}, 错误: {str(e)}")
            extracted['upload_failed'] = True
            extracted['upload_error'] = str(e)

        return extracted

    def _upload_single_other_file(self, other_file: Dict[str, Any]) -> None:
        """上传单个其他文件"""
        if not other_file.get('cloud_storage_url') or not other_file.get('uploaded_to_qiniu'):
            try:
                other_file_uuid = other_file.get('file_uuid')
                other_file_name = other_file.get('file_name', '未知文件')
                other_file_path = other_file.get('file_path')

                if other_file_uuid and other_file_path and os.path.exists(other_file_path):
                    file_ext = os.path.splitext(other_file_name)[1]
                    qiniu_key = f"{other_file_uuid}{file_ext}"

                    ret, info = self.qiniu_client.upload_file(other_file_path, qiniu_key)

                    if info.status_code == 200:
                        other_cloud_url = f"http://{self.qiniu_client.bucket_domain}/{qiniu_key}"
                        other_file['file_url'] = other_cloud_url
                        other_file['cloud_storage_url'] = other_cloud_url
                        other_file['qiniu_key'] = qiniu_key
                        other_file['uploaded_to_qiniu'] = True
                        other_file['upload_method'] = 'direct_original_file'
                        logger.info(f"✅ 非zip文件上传成功: {other_file_name} -> {other_cloud_url}")
                    else:
                        logger.error(f"❌ 非zip文件上传失败: {other_file_name}, 错误: {info}")
                        other_file['upload_failed'] = True
                        other_file['upload_error'] = str(info)
                else:
                    logger.warning(f"⚠️ 非zip文件缺少必要信息，跳过上传: {other_file_name}")
                    other_file['upload_skipped'] = True
                    other_file['skip_reason'] = '缺少文件UUID或路径'

            except Exception as e:
                logger.error(f"处理非zip文件上传时出错: {other_file.get('file_name', '未知')}, 错误: {str(e)}")
                other_file['upload_failed'] = True
                other_file['upload_error'] = str(e)
