"""
七牛云文件上传服务
封装文件上传到七牛云的所有逻辑
"""
import os
import base64
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from src.utils.qiniu_client import create_qiniu_client
from src.utils.logger import BeijingLogger
from app.config.file_constants import (
    IMAGE_EXTENSIONS, BINARY_EXTENSIONS, DOCUMENT_EXTENSIONS,
    TEXT_EXTENSIONS, MIME_TYPE_TO_EXTENSION, TEMP_FILE_PATH_TEMPLATE
)

logger = BeijingLogger().get_logger()


class QiniuUploadService:
    """七牛云上传服务类"""

    def __init__(self):
        self.qiniu_client = create_qiniu_client()

    def get_file_extension(self, file_name: str, file_type: str) -> str:
        """获取文件扩展名"""
        if file_name and "." in file_name:
            return os.path.splitext(file_name)[1]
        elif file_type and file_type != "unknown":
            return MIME_TYPE_TO_EXTENSION.get(file_type, "")
        return ""

    def decode_file_content(self, file_content) -> Optional[bytes]:
        """解码文件内容为字节数据"""
        if isinstance(file_content, str) and os.path.exists(file_content):
            # 如果是文件路径，直接返回None，后续使用路径上传
            return None
        elif isinstance(file_content, str) and file_content.startswith('data:'):
            # 处理data URL格式
            _, data = file_content.split(',', 1)
            return base64.b64decode(data)
        elif isinstance(file_content, str):
            # 假设是base64编码的字符串
            try:
                return base64.b64decode(file_content)
            except:
                # 如果不是base64，当作普通字符串处理
                return file_content.encode('utf-8')
        elif isinstance(file_content, bytes):
            return file_content
        else:
            # 其他类型，尝试转换为字符串再编码
            return str(file_content).encode('utf-8')

    def create_temp_file(self, file_data: bytes, file_uuid: str, file_ext: str,
                        conversation_id: str) -> str:
        """创建临时文件"""
        temp_dir = Path(TEMP_FILE_PATH_TEMPLATE.format(conversation_id=conversation_id))
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file_path = temp_dir / f"{file_uuid}{file_ext}"

        with open(temp_file_path, "wb") as temp_f:
            temp_f.write(file_data)

        logger.info(f"Created temp file: {temp_file_path}")
        return str(temp_file_path)

    def upload_file(self, file_path: str, qiniu_key: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        上传文件到七牛云

        Returns:
            (成功标志, 云存储URL, 错误信息)
        """
        try:
            ret, info = self.qiniu_client.upload_file(file_path, qiniu_key)

            if info.status_code == 200:
                cloud_url = f"http://{self.qiniu_client.bucket_domain}/{qiniu_key}"
                return True, cloud_url, None
            else:
                return False, None, f"上传失败: {info}"
        except Exception as e:
            return False, None, str(e)

    def process_file_upload(self, file: Dict, conversation_id: str,
                           file_uuid: str) -> Optional[Dict]:
        """
        处理单个文件的上传流程

        Returns:
            包含文件信息的字典，失败返回None
        """
        file_name = file.get("file_name", "unknown_file")
        file_content = file.get("file_content")
        file_type = file.get("file_type", "unknown")
        file_size = file.get("file_size", 0)

        # 获取文件扩展名
        file_ext = self.get_file_extension(file_name, file_type)
        qiniu_key = f"{file_uuid}{file_ext}"

        local_file_path = None
        temp_file_created = False
        cloud_storage_url = None

        if not file_content:
            logger.warning(f"File has no content: {file_name}")
            return None

        try:
            # 检查是否是已存在的文件路径
            if isinstance(file_content, str) and os.path.exists(file_content):
                local_file_path = file_content
            else:
                # 解码文件内容
                file_data = self.decode_file_content(file_content)

                if file_data:
                    # 创建临时文件
                    local_file_path = self.create_temp_file(
                        file_data, file_uuid, file_ext, conversation_id
                    )
                    temp_file_created = True
                else:
                    logger.warning(f"Cannot decode file content: {file_name}")
                    return None

            # 上传到七牛云
            success, cloud_url, error = self.upload_file(local_file_path, qiniu_key)

            cloud_storage_url = None
            if not success:
                logger.warning(f"Upload to Qiniu failed for {file_name}: {error}")
                logger.info(f"Fallback: Using local file path instead: {local_file_path}")
                # 即使上传失败，也返回本地文件信息，使用本地路径进行后续处理
            else:
                cloud_storage_url = cloud_url
                logger.info(f"File upload success: {file_name} -> {cloud_storage_url}")

            # 构建文件信息（无论上传成功与否）
            file_info = {
                "file_id": file_uuid,
                "file_uuid": file_uuid,
                "file_name": file_name,
                "file_url": cloud_storage_url,  # 上传失败时为None
                "file_extension": file_ext.lstrip('.').lower() if file_ext else "",
                "file_type": file_type,
                "file_size": file_size,
                "file_content": file.get("file_content"),
                "cloud_storage_url": cloud_storage_url,  # 上传失败时为None
                "qiniu_key": qiniu_key,
                "file_path": local_file_path,  # 🔥 关键：保留本地文件路径
                "temp_file_created": temp_file_created,
                "upload_success": success  # 🔥 标记上传是否成功
            }

            return file_info

        except Exception as e:
            logger.error(f"Error processing file upload for {file_name}: {str(e)}")
            return None

    def upload_zip_subfile(self, extracted_file: Dict, conversation_id: str) -> bool:
        """
        上传zip子文件到七牛云

        Returns:
            是否成功上传
        """
        sub_file_uuid = extracted_file.get('file_uuid')
        sub_file_name = extracted_file.get('file_name', '未知文件')
        sub_file_content = extracted_file.get('file_content', '')
        file_ext = ""

        if sub_file_name and "." in sub_file_name:
            file_ext = os.path.splitext(sub_file_name)[1]

        qiniu_key = f"{sub_file_uuid}{file_ext}"
        file_extension = file_ext.lstrip('.').lower()

        # 🚨 DEBUG: 输出接收到的字段
        logger.info(f"DEBUG upload_zip_subfile - 文件: {sub_file_name}")
        logger.info(f"  file_extension: {file_extension}")
        logger.info(f"  original_file_path: {extracted_file.get('original_file_path')}")
        logger.info(f"  temp_file_available: {extracted_file.get('temp_file_available')}")
        logger.info(f"  temp_file_path: {extracted_file.get('temp_file_path')}")
        logger.info(f"  persistent_temp_file: {extracted_file.get('persistent_temp_file')}")

        # 优先使用原始文件路径，也检查 temp_file_path（PDF提取的图片用这个字段）
        original_file_path = extracted_file.get('original_file_path') or extracted_file.get('temp_file_path')
        temp_file_available = extracted_file.get('temp_file_available', False)

        logger.info(f"  检查条件: original_file_path={bool(original_file_path)}, temp_file_available={temp_file_available}, exists={os.path.exists(original_file_path) if original_file_path else False}")

        if original_file_path and temp_file_available and os.path.exists(original_file_path):
            logger.info(f"📁 直接上传原始文件: {sub_file_name}")
            success, cloud_url, error = self.upload_file(original_file_path, qiniu_key)

            if success:
                extracted_file['file_url'] = cloud_url
                extracted_file['cloud_storage_url'] = cloud_url
                extracted_file['qiniu_key'] = qiniu_key
                extracted_file['uploaded_to_qiniu'] = True
                extracted_file['upload_method'] = 'direct_original_file'
                logger.info(f"✅ 原始文件上传成功: {sub_file_name} -> {cloud_url}")
                return True
            else:
                logger.error(f"❌ 原始文件上传失败: {sub_file_name}, 错误: {error}")
                extracted_file['upload_failed'] = True
                extracted_file['upload_error'] = error

        # 降级策略：根据文件类型处理
        if file_extension in BINARY_EXTENSIONS:
            logger.warning(f"⚠️ 子文件 {sub_file_name} 是二进制文件，且原始文件不可用，跳过上传")
            extracted_file['upload_skipped'] = True
            extracted_file['skip_reason'] = '二进制文件且原始文件不可用'
            return False
        elif file_extension in DOCUMENT_EXTENSIONS:
            logger.warning(f"⚠️ 子文件 {sub_file_name} 是Office文档，无法从提取文本重建，跳过上传")
            extracted_file['upload_skipped'] = True
            extracted_file['skip_reason'] = 'Office文档无法从提取文本重建'
            return False
        elif file_extension in TEXT_EXTENSIONS or not file_extension:
            # 文本文件：从提取的内容重建
            logger.info(f"📝 从提取内容重建文本文件: {sub_file_name}")
            try:
                temp_file_path = self.create_temp_file(
                    sub_file_content.encode('utf-8'),
                    sub_file_uuid,
                    file_ext,
                    conversation_id
                )

                success, cloud_url, error = self.upload_file(temp_file_path, qiniu_key)

                # 清理临时文件
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)

                if success:
                    extracted_file['file_url'] = cloud_url
                    extracted_file['cloud_storage_url'] = cloud_url
                    extracted_file['qiniu_key'] = qiniu_key
                    extracted_file['uploaded_to_qiniu'] = True
                    extracted_file['upload_method'] = 'reconstructed_from_content'
                    logger.info(f"✅ 重建文件上传成功: {sub_file_name} -> {cloud_url}")
                    return True
                else:
                    logger.error(f"❌ 重建文件上传失败: {sub_file_name}, 错误: {error}")
                    extracted_file['upload_failed'] = True
                    extracted_file['upload_error'] = error
                    return False

            except Exception as e:
                logger.error(f"重建文本文件失败: {sub_file_name}, 错误: {str(e)}")
                extracted_file['upload_failed'] = True
                extracted_file['upload_error'] = str(e)
                return False

        return False
