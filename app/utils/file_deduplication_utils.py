"""
文件去重工具
用于检测和剔除重复文件，基于文件哈希和文件名
"""
import logging
from typing import List, Dict, Tuple
from app.utils.file_hash_utils import calculate_file_or_content_hash

logger = logging.getLogger(__name__)


def detect_duplicate_files(files: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    """
    检测并剔除重复文件
    
    Args:
        files: 文件列表，每个文件是包含file_name、file_content、file_path等字段的字典
        
    Returns:
        Tuple[unique_files, duplicate_files]
        - unique_files: 去重后的唯一文件列表
        - duplicate_files: 重复文件信息列表
    """
    unique_files = []
    duplicate_files = []
    seen_hashes = set()
    seen_names = set()
    
    logger.info(f"开始检测重复文件，总计 {len(files)} 个文件")
    
    for i, file in enumerate(files):
        file_name = file.get('file_name', f'未知文件_{i}')
        file_content = file.get('file_content')
        file_path = file.get('file_path')
        
        # 计算文件哈希值
        file_hash = calculate_file_or_content_hash(
            file_path=file_path,
            content=file_content
        )
        
        # 检查是否重复
        is_duplicate = False
        duplicate_reason = ""
        
        if file_hash and file_hash in seen_hashes:
            is_duplicate = True
            duplicate_reason = "文件内容相同"
        elif file_name in seen_names:
            # 文件名相同但内容不同的情况（也视为重复，避免覆盖）
            is_duplicate = True
            duplicate_reason = "文件名相同"
        
        if is_duplicate:
            duplicate_info = {
                "file_name": file_name,
                "file_uuid": file.get('file_uuid', file.get('file_id')),
                "duplicate_reason": duplicate_reason,
                "file_hash": file_hash,
                "original_index": i
            }
            duplicate_files.append(duplicate_info)
            logger.info(f"发现重复文件 #{i}: {file_name} - {duplicate_reason}")
        else:
            # 不是重复文件，添加到唯一文件列表
            unique_files.append(file)
            if file_hash:
                seen_hashes.add(file_hash)
            seen_names.add(file_name)
            
            # 为文件添加哈希信息（用于后续处理）
            file['file_hash'] = file_hash
    
    logger.info(f"重复文件检测完成: 唯一文件 {len(unique_files)} 个, 重复文件 {len(duplicate_files)} 个")
    
    # 输出重复文件详情
    if duplicate_files:
        logger.info("重复文件详情:")
        for dup in duplicate_files:
            logger.info(f"  - {dup['file_name']} ({dup['duplicate_reason']})")
    
    return unique_files, duplicate_files


def merge_file_lists(existing_files: List[Dict], new_files: List[Dict]) -> List[Dict]:
    """
    合并两个文件列表，自动去重
    
    Args:
        existing_files: 现有文件列表
        new_files: 新文件列表
        
    Returns:
        合并并去重后的文件列表
    """
    if not existing_files:
        return new_files
    
    if not new_files:
        return existing_files
    
    logger.info(f"合并文件列表: 现有 {len(existing_files)} 个, 新增 {len(new_files)} 个")
    
    # 合并文件列表
    all_files = existing_files + new_files
    
    # 去重
    unique_files, duplicate_files = detect_duplicate_files(all_files)
    
    logger.info(f"合并后文件列表: 唯一文件 {len(unique_files)} 个, 去除重复 {len(duplicate_files)} 个")
    
    return unique_files


def find_duplicate_by_name(files: List[Dict], target_name: str) -> List[Dict]:
    """
    根据文件名查找重复文件
    
    Args:
        files: 文件列表
        target_name: 目标文件名
        
    Returns:
        匹配的文件列表
    """
    matches = [f for f in files if f.get('file_name') == target_name]
    
    if len(matches) > 1:
        logger.warning(f"发现重复文件名: {target_name}, 共 {len(matches)} 个")
    
    return matches


def find_duplicate_by_hash(files: List[Dict], target_hash: str) -> List[Dict]:
    """
    根据哈希值查找重复文件
    
    Args:
        files: 文件列表（需要包含file_hash字段）
        target_hash: 目标哈希值
        
    Returns:
        匹配的文件列表
    """
    matches = [f for f in files if f.get('file_hash') == target_hash]
    
    if len(matches) > 1:
        logger.warning(f"发现重复哈希: {target_hash}, 共 {len(matches)} 个文件")
    
    return matches

