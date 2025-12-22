"""
文件哈希计算工具
用于计算文件或内容的MD5哈希值，支持重复文件检测
"""
import hashlib
import os
import logging

logger = logging.getLogger(__name__)


def calculate_file_hash(file_path: str) -> str:
    """
    计算文件的MD5哈希值
    
    Args:
        file_path: 文件路径
        
    Returns:
        MD5哈希值的十六进制字符串，失败返回None
    """
    if not file_path or not os.path.exists(file_path):
        logger.warning(f"文件路径无效或文件不存在: {file_path}")
        return None
    
    try:
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            # 分块读取，避免大文件占用过多内存
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        
        hash_value = hash_md5.hexdigest()
        logger.debug(f"计算文件哈希成功: {file_path} -> {hash_value}")
        return hash_value
        
    except Exception as e:
        logger.error(f"计算文件哈希值失败 {file_path}: {str(e)}")
        return None


def calculate_content_hash(content) -> str:
    """
    计算文件内容的MD5哈希值
    
    Args:
        content: 文件内容（字符串、字节或其他类型）
        
    Returns:
        MD5哈希值的十六进制字符串，失败返回None
    """
    if not content:
        logger.warning("内容为空，无法计算哈希")
        return None
    
    try:
        # 统一转换为字节
        if isinstance(content, str):
            content_bytes = content.encode('utf-8')
        elif isinstance(content, bytes):
            content_bytes = content
        else:
            content_bytes = str(content).encode('utf-8')
        
        hash_value = hashlib.md5(content_bytes).hexdigest()
        logger.debug(f"计算内容哈希成功，长度: {len(content_bytes)} 字节 -> {hash_value}")
        return hash_value
        
    except Exception as e:
        logger.error(f"计算内容哈希值失败: {str(e)}")
        return None


def calculate_file_or_content_hash(file_path: str = None, content = None) -> str:
    """
    自动选择计算文件或内容的哈希值
    优先使用文件路径，如果不存在则使用内容
    
    Args:
        file_path: 文件路径（可选）
        content: 文件内容（可选）
        
    Returns:
        MD5哈希值的十六进制字符串，失败返回None
    """
    # 优先使用文件路径
    if file_path and os.path.exists(file_path):
        return calculate_file_hash(file_path)
    
    # 如果没有文件路径，使用内容
    if content:
        return calculate_content_hash(content)
    
    logger.warning("既没有有效的文件路径也没有内容，无法计算哈希")
    return None

