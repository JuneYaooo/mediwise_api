import os
from dotenv import load_dotenv
load_dotenv()
from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
from src.llms import *
from src.utils.json_utils import JsonUtils
from src.utils.logger import BeijingLogger
from datetime import datetime
import time
import json
import uuid
import copy
import re
from typing import Dict, List, Any, Optional
from pathlib import Path

# 🆕 Token管理和数据压缩模块
from src.utils.token_manager import TokenManager
from src.utils.data_compressor import PatientDataCompressor

# 初始化 logger
logger = BeijingLogger().get_logger()

@CrewBase
class PatientInfoUpdateCrew():
    """简化的患者信息更新crew，专注于分析和修改操作"""

    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"
    
    def __init__(self):
        """
        初始化PatientInfoUpdateCrew
        """
        pass
    
    def _execute_modifications(self, patient_data: Dict, modifications: List[Dict]) -> Dict:
        """
        根据修改指令执行具体的修改操作，支持复杂的多处修改
        
        Args:
            patient_data: 当前的患者数据
            modifications: 修改指令列表，按sequence排序
            
        Returns:
            修改后的患者数据
        """
        try:
            # 深拷贝数据，避免修改原始数据
            updated_data = copy.deepcopy(patient_data)
            
            # 按sequence排序执行修改
            sorted_modifications = sorted(modifications, key=lambda x: x.get("sequence", 0))
            
            for mod in sorted_modifications:
                target_module = mod.get("target_module", "")
                target_path = mod.get("target_path", "")
                action = mod.get("action", "")
                new_value = mod.get("new_value")
                condition = mod.get("condition")
                leading_context = mod.get("leading_context")
                target_content = mod.get("target_content")
                trailing_context = mod.get("trailing_context")
                description = mod.get("description", "")
                sequence = mod.get("sequence", 0)
                reason = mod.get("reason", "")
                
                logger.info(f"执行修改 #{sequence}: {description} - {reason}")
                
                # 根据目标模块获取数据
                if target_module == "patient_timeline":
                    target_data = updated_data.get("patient_timeline", {})
                elif target_module == "patient_journey":
                    target_data = updated_data.get("patient_journey", {})
                elif target_module == "mdt_simple_report":
                    target_data = updated_data.get("mdt_simple_report", [])
                else:
                    logger.warning(f"未知的目标模块: {target_module}")
                    continue
                
                # 清理路径：如果路径以模块名开头，去除模块名前缀
                # 例如: "mdt_simple_report[12].rows[0][3]" -> "[12].rows[0][3]"
                logger.info(f"🔍 原始路径: {target_path}, 目标模块: {target_module}")
                clean_path = target_path
                if target_path.startswith(f"{target_module}."):
                    clean_path = target_path[len(target_module) + 1:]  # +1 是为了去掉点号
                    logger.info(f"✂️ 清理路径前缀（点号）: {target_path} -> {clean_path}")
                elif target_path.startswith(f"{target_module}["):
                    clean_path = target_path[len(target_module):]  # 保留 [ 号
                    logger.info(f"✂️ 清理路径前缀（括号）: {target_path} -> {clean_path}")
                else:
                    logger.info(f"⚠️ 路径不需要清理: {target_path}")
                
                logger.info(f"📍 最终使用的路径: {clean_path}")
                logger.info(f"📦 目标数据类型: {type(target_data).__name__}, 长度/键: {len(target_data) if isinstance(target_data, (list, dict)) else 'N/A'}")
                
                # 执行具体的修改操作（使用清理后的路径）
                if action == "set":
                    # 直接设置字段值
                    self._set_value_by_path(target_data, clean_path, new_value)
                    # 检查是否需要关联更新（如指标异常状态）
                    self._check_and_update_related_fields(target_data, clean_path, new_value)
                elif action == "modify_text":
                    # 基于前导上下文的文本修改
                    self._modify_text_by_path(target_data, clean_path, new_value, 
                                            leading_context, target_content, trailing_context)
                elif action == "delete":
                    # 删除操作保留，用于删除整个条目
                    self._delete_value_by_path(target_data, clean_path)
                else:
                    logger.warning(f"未知的操作类型: {action}，支持的操作类型: set, modify_text, delete")
                
                # 将修改后的数据写回
                if target_module == "patient_timeline":
                    updated_data["patient_timeline"] = target_data
                elif target_module == "patient_journey":
                    updated_data["patient_journey"] = target_data
                elif target_module == "mdt_simple_report":
                    updated_data["mdt_simple_report"] = target_data
            
            return updated_data
            
        except Exception as e:
            logger.error(f"执行修改操作时出错: {e}")
            logger.error(f"错误类型: {type(e)}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            return patient_data
    
    def _update_value(self, target_data: Any, path: str, new_value: Any, condition: Dict = None):
        """更新值，已废弃，使用简化的方法替代"""
        logger.warning("_update_value方法已废弃，请使用set或modify_text操作")
        self._set_value_by_path(target_data, path, new_value)
    
    def _set_value(self, target_data: Any, path: str, new_value: Any, condition: Dict = None):
        """设置值，已废弃，使用简化的方法替代"""
        logger.warning("_set_value方法已废弃，请使用set操作")
        self._set_value_by_path(target_data, path, new_value)
    
    def _delete_value(self, target_data: Any, path: str, condition: Dict = None):
        """删除值，已废弃，使用简化的方法替代"""
        logger.warning("_delete_value方法已废弃，请使用delete操作")
        self._delete_value_by_path(target_data, path)
    
    def _append_value(self, target_data: Any, path: str, new_value: Any):
        """追加值，已废弃"""
        logger.warning("_append_value方法已废弃")
    
    def _insert_value(self, target_data: Any, path: str, new_value: Any, condition: Dict = None):
        """插入值，已废弃"""
        logger.warning("_insert_value方法已废弃")
    
    def _parse_path_to_tokens(self, path: str) -> List[str]:
        """将路径解析为标准化的token列表

        例如：
        - "[12].rows[4][3]" -> ["[12]", "rows", "[4]", "[3]"]
        - "key.array[0].field" -> ["key", "array", "[0]", "field"]
        - "rows[4][3]" -> ["rows", "[4]", "[3]"]
        """
        tokens = []

        # 先按点分割
        parts = path.split('.')

        for part in parts:
            if not part:
                continue

            # 检查是否包含数组索引
            if '[' not in part:
                # 普通键
                tokens.append(part)
            else:
                # 包含数组索引，需要进一步解析
                # 例如 "rows[4][3]" -> ["rows", "[4]", "[3]"]
                # 例如 "[12]" -> ["[12]"]
                current_pos = 0
                while current_pos < len(part):
                    bracket_start = part.find('[', current_pos)

                    if bracket_start == -1:
                        # 没有更多的括号
                        if current_pos < len(part):
                            remaining = part[current_pos:]
                            if remaining:
                                tokens.append(remaining)
                        break

                    # 先添加括号前的部分（如果有）
                    if bracket_start > current_pos:
                        prefix = part[current_pos:bracket_start]
                        if prefix:
                            tokens.append(prefix)

                    # 找到对应的右括号
                    bracket_end = part.find(']', bracket_start)
                    if bracket_end == -1:
                        logger.error(f"路径格式错误，缺少右括号: {part}")
                        break

                    # 添加数组索引 token（包括括号）
                    index_token = part[bracket_start:bracket_end + 1]
                    tokens.append(index_token)

                    current_pos = bracket_end + 1

        return tokens

    def _set_value_by_path(self, target_data: Any, path: str, new_value: Any):
        """通过路径设置值 - 核心方法

        支持的路径格式：
        - "key1.key2.key3": 嵌套字典访问
        - "array[0]": 数组索引访问
        - "[0].key": 从数组开始的路径
        - "key.array[0].key2": 混合访问
        - "rows[4][3]": 连续数组索引
        """
        try:
            logger.info(f"🔧 _set_value_by_path 被调用")
            logger.info(f"   - 路径: {path}")
            logger.info(f"   - 新值: {new_value}")
            logger.info(f"   - 数据类型: {type(target_data).__name__}")

            # 使用新的路径解析方法
            tokens = self._parse_path_to_tokens(path)
            logger.info(f"   - 路径token: {tokens}")

            if not tokens:
                logger.error("路径解析结果为空")
                return

            current = target_data

            # 遍历到倒数第二层
            for token in tokens[:-1]:
                current = self._navigate_by_token(current, token)
                if current is None:
                    return

            # 设置最后一层的值
            final_token = tokens[-1]
            self._set_final_value_by_token(current, final_token, new_value)

            logger.info(f"✓ 成功设置路径 {path} 的值为: {new_value}")

        except Exception as e:
            logger.error(f"通过路径设置值时出错 - 路径: {path}, 新值: {new_value}, 错误: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")

    def _navigate_by_token(self, current: Any, token: str) -> Any:
        """根据单个token导航

        Args:
            current: 当前数据节点
            token: 路径token，例如 "key", "[0]"

        Returns:
            导航后的数据节点，失败返回 None
        """
        if token.startswith('[') and token.endswith(']'):
            # 纯数组索引
            try:
                index = int(token[1:-1])
            except ValueError:
                logger.error(f"无效的数组索引: {token}")
                return None

            if not isinstance(current, list):
                logger.error(f"期望数组但得到 {type(current).__name__}")
                return None
            if index >= len(current):
                logger.error(f"数组索引 {index} 超出范围（长度: {len(current)}）")
                return None
            return current[index]
        else:
            # 普通键访问
            if not isinstance(current, dict):
                logger.error(f"期望字典但得到 {type(current).__name__}")
                return None
            if token not in current:
                logger.error(f"键 '{token}' 不存在于当前数据中")
                return None
            return current[token]

    def _set_final_value_by_token(self, current: Any, token: str, new_value: Any):
        """根据单个token设置最终值

        Args:
            current: 当前数据节点
            token: 路径token，例如 "key", "[0]"
            new_value: 要设置的新值
        """
        if token.startswith('[') and token.endswith(']'):
            # 纯数组索引
            try:
                index = int(token[1:-1])
            except ValueError:
                logger.error(f"无效的数组索引: {token}")
                return

            if not isinstance(current, list):
                logger.error(f"期望数组但得到 {type(current).__name__}")
                return
            if index >= len(current):
                logger.error(f"数组索引 {index} 超出范围（长度: {len(current)}）")
                return
            current[index] = new_value
        else:
            # 普通键赋值
            if not isinstance(current, dict):
                logger.error(f"期望字典但得到 {type(current).__name__}")
                return
            current[token] = new_value
    
    def _navigate_to_part(self, current: Any, part: str) -> Any:
        """导航到路径的某个部分
        
        Args:
            current: 当前数据节点
            part: 路径部分，例如 "key", "array[0]", "[0]"
            
        Returns:
            导航后的数据节点，失败返回 None
        """
        if '[' in part and ']' in part:
            # 处理数组索引
            key = part.split('[')[0]
            index = int(part.split('[')[1].split(']')[0])
            
            if key == '':
                # 纯数组索引，例如 "[0]"
                if not isinstance(current, list):
                    logger.error(f"期望数组但得到 {type(current).__name__}")
                    return None
                if index >= len(current):
                    logger.error(f"数组索引 {index} 超出范围（长度: {len(current)}）")
                    return None
                return current[index]
            else:
                # 键名 + 数组索引，例如 "rows[0]"
                if not isinstance(current, dict):
                    logger.error(f"期望字典但得到 {type(current).__name__}")
                    return None
                if key not in current:
                    logger.error(f"键 '{key}' 不存在于当前数据中")
                    return None
                if not isinstance(current[key], list):
                    logger.error(f"'{key}' 不是数组")
                    return None
                if index >= len(current[key]):
                    logger.error(f"数组 '{key}' 的索引 {index} 超出范围（长度: {len(current[key])}）")
                    return None
                return current[key][index]
        else:
            # 普通键访问
            if not isinstance(current, dict):
                logger.error(f"期望字典但得到 {type(current).__name__}")
                return None
            if part not in current:
                logger.error(f"键 '{part}' 不存在于当前数据中")
                return None
            return current[part]
    
    def _set_final_value(self, current: Any, final_part: str, new_value: Any):
        """设置最终值
        
        Args:
            current: 当前数据节点
            final_part: 最后一个路径部分
            new_value: 要设置的新值
        """
        if '[' in final_part and ']' in final_part:
            # 处理数组索引
            key = final_part.split('[')[0]
            index = int(final_part.split('[')[1].split(']')[0])
            
            if key == '':
                # 纯数组索引，例如 "[3]"
                if not isinstance(current, list):
                    logger.error(f"期望数组但得到 {type(current).__name__}")
                    return
                if index >= len(current):
                    logger.error(f"数组索引 {index} 超出范围（长度: {len(current)}）")
                    return
                current[index] = new_value
            else:
                # 键名 + 数组索引，例如 "items[0]"
                if not isinstance(current, dict):
                    logger.error(f"期望字典但得到 {type(current).__name__}")
                    return
                if key not in current:
                    logger.error(f"键 '{key}' 不存在于当前数据中")
                    return
                if not isinstance(current[key], list):
                    logger.error(f"'{key}' 不是数组")
                    return
                if index >= len(current[key]):
                    logger.error(f"数组 '{key}' 的索引 {index} 超出范围（长度: {len(current[key])}）")
                    return
                current[key][index] = new_value
        else:
            # 普通键赋值
            if not isinstance(current, dict):
                logger.error(f"期望字典但得到 {type(current).__name__}")
                return
            current[final_part] = new_value
    
    def _delete_value_by_path(self, target_data: Any, path: str):
        """通过路径删除值 - 核心方法"""
        try:
            parts = path.split('.')
            current = target_data
            
            # 遍历到倒数第二层
            for part in parts[:-1]:
                if '[' in part and ']' in part:
                    key = part.split('[')[0]
                    index = int(part.split('[')[1].split(']')[0])
                    current = current[key][index]
                else:
                    current = current[part]
            
            # 删除最后一层的值
            final_key = parts[-1]
            if '[' in final_key and ']' in final_key:
                key = final_key.split('[')[0]
                index = int(final_key.split('[')[1].split(']')[0])
                if isinstance(current[key], list):
                    current[key].pop(index)
                    logger.info(f"✓ 成功删除路径 {path} 的数组元素")
            else:
                if final_key in current:
                    del current[final_key]
                    logger.info(f"✓ 成功删除路径 {path} 的字段")
                    
        except Exception as e:
            logger.error(f"通过路径删除值时出错 - 路径: {path}, 错误: {e}")
    
    def _modify_text_with_context(self, target_data: Any, path: str, new_value: Any,
                                leading_context: str = None, target_content: str = None,
                                trailing_context: str = None, condition: Dict = None):
        """
        基于前导上下文精确定位并修改文本内容
        
        Args:
            target_data: 目标数据结构
            path: JSON路径
            new_value: 新值
            leading_context: 前导上下文
            target_content: 要修改的目标内容
            trailing_context: 后导上下文
            condition: 查找条件（仅在特殊情况下使用）
        """
        try:
            logger.info(f"执行文本上下文修改 - 路径: {path}")
            logger.info(f"前导上下文: '{leading_context}', 目标内容: '{target_content}', 新值: '{new_value}'")
            
            # 如果没有提供上下文信息，回退到普通的设置方法
            if not leading_context and not target_content:
                logger.warning("未提供上下文信息，回退到普通设置方法")
                self._set_value_by_path(target_data, path, new_value)
                return
            
            # 使用路径直接定位到字段，然后在字段内进行上下文修改
            self._modify_text_by_path(target_data, path, new_value, 
                                    leading_context, target_content, 
                                    trailing_context)
                                    
        except Exception as e:
            logger.error(f"基于上下文修改文本时出错: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
    
    def _modify_text_by_path(self, target_data: Any, path: str, new_value: Any,
                           leading_context: str, target_content: str,
                           trailing_context: str):
        """通过路径直接修改文本内容"""
        try:
            # 使用统一的路径解析方法
            tokens = self._parse_path_to_tokens(path)
            logger.info(f"🔧 _modify_text_by_path 路径token: {tokens}")

            if not tokens:
                logger.error("路径解析结果为空")
                return

            current = target_data

            # 遍历到倒数第二层
            for token in tokens[:-1]:
                current = self._navigate_by_token(current, token)
                if current is None:
                    return

            # 修改最后一层的文本内容
            final_token = tokens[-1]

            if final_token.startswith('[') and final_token.endswith(']'):
                # 纯数组索引，例如 "[3]"
                try:
                    index = int(final_token[1:-1])
                except ValueError:
                    logger.error(f"无效的数组索引: {final_token}")
                    return

                if not isinstance(current, list):
                    logger.error(f"期望数组但得到 {type(current).__name__}")
                    return
                if index >= len(current):
                    logger.error(f"数组索引 {index} 超出范围（长度: {len(current)}）")
                    return

                original_text = current[index]
                if isinstance(original_text, str):
                    modified_text = self._replace_text_with_context(
                        original_text, leading_context, target_content,
                        trailing_context, new_value
                    )
                    current[index] = modified_text
                    logger.info(f"✓ 成功修改文本: {original_text} -> {modified_text}")
                else:
                    logger.error(f"索引 {index} 处的值不是字符串: {type(original_text).__name__}")
            else:
                # 普通键访问
                if not isinstance(current, dict):
                    logger.error(f"期望字典但得到 {type(current).__name__}")
                    return
                if final_token not in current:
                    logger.error(f"键 '{final_token}' 不存在于当前数据中")
                    return

                if isinstance(current[final_token], str):
                    original_text = current[final_token]
                    modified_text = self._replace_text_with_context(
                        original_text, leading_context, target_content,
                        trailing_context, new_value
                    )
                    current[final_token] = modified_text
                    logger.info(f"✓ 成功修改文本: {original_text} -> {modified_text}")
                else:
                    logger.error(f"键 '{final_token}' 的值不是字符串: {type(current[final_token]).__name__}")
                    
        except Exception as e:
            logger.error(f"通过路径修改文本时出错: {e}")
    
    def _modify_nested_text(self, data: Any, path_parts: List[str], new_value: Any,
                          leading_context: str, target_content: str, 
                          trailing_context: str) -> bool:
        """递归修改嵌套结构中的文本"""
        try:
            if not path_parts:
                return False
                
            current_part = path_parts[0]
            remaining_parts = path_parts[1:]
            
            if isinstance(data, dict):
                if '[' in current_part and ']' in current_part:
                    # 处理数组索引
                    key = current_part.split('[')[0]
                    index = int(current_part.split('[')[1].split(']')[0])
                    if key in data and isinstance(data[key], list) and index < len(data[key]):
                        if not remaining_parts:
                            # 到达目标位置
                            original_text = data[key][index]
                            if isinstance(original_text, str):
                                modified_text = self._replace_text_with_context(
                                    original_text, leading_context, target_content, 
                                    trailing_context, new_value
                                )
                                data[key][index] = modified_text
                                return True
                        else:
                            # 继续递归
                            return self._modify_nested_text(data[key][index], remaining_parts, 
                                                          new_value, leading_context, 
                                                          target_content, trailing_context)
                else:
                    if current_part in data:
                        if not remaining_parts:
                            # 到达目标位置
                            if isinstance(data[current_part], str):
                                original_text = data[current_part]
                                modified_text = self._replace_text_with_context(
                                    original_text, leading_context, target_content, 
                                    trailing_context, new_value
                                )
                                data[current_part] = modified_text
                                return True
                        else:
                            # 继续递归
                            return self._modify_nested_text(data[current_part], remaining_parts, 
                                                          new_value, leading_context, 
                                                          target_content, trailing_context)
            elif isinstance(data, list):
                # 如果当前是列表，尝试在所有项中查找
                for item in data:
                    if self._modify_nested_text(item, path_parts, new_value, 
                                              leading_context, target_content, 
                                              trailing_context):
                        return True
                        
        except Exception as e:
            logger.error(f"递归修改嵌套文本时出错: {e}")
            
        return False
    
    def _replace_text_with_context(self, original_text: str, leading_context: str,
                                 target_content: str, trailing_context: str, 
                                 new_value: str) -> str:
        """
        基于前导上下文替换文本内容，遵循最小上下文定位原则
        
        Args:
            original_text: 原始文本
            leading_context: 前导上下文
            target_content: 要替换的目标内容
            trailing_context: 后导上下文
            new_value: 新值
            
        Returns:
            替换后的文本
        """
        try:
            if not original_text or not isinstance(original_text, str):
                return original_text
            
            if not target_content:
                logger.warning("未提供目标内容，无法进行替换")
                return original_text
            
            # 1. 首先尝试最小上下文定位（只用leading_context + target_content）
            if leading_context:
                minimal_pattern = re.escape(leading_context) + re.escape(target_content)
                if re.search(minimal_pattern, original_text):
                    # 检查是否唯一匹配
                    matches = list(re.finditer(minimal_pattern, original_text))
                    if len(matches) == 1:
                        # 唯一匹配，使用最小上下文
                        replacement = leading_context + new_value
                        modified_text = re.sub(minimal_pattern, replacement, original_text, count=1)
                        logger.info(f"✓ 使用最小上下文定位成功: '{leading_context}{target_content}' -> '{leading_context}{new_value}'")
                        return modified_text
                    else:
                        logger.info(f"最小上下文匹配到{len(matches)}个结果，尝试使用完整上下文")
                
                # 2. 如果最小上下文不唯一，使用完整上下文
                if trailing_context:
                    full_pattern = re.escape(leading_context) + re.escape(target_content) + re.escape(trailing_context)
                    if re.search(full_pattern, original_text):
                        replacement = leading_context + new_value + trailing_context
                        modified_text = re.sub(full_pattern, replacement, original_text, count=1)
                        logger.info(f"✓ 使用完整上下文定位成功")
                        return modified_text
                    else:
                        logger.warning(f"完整上下文模式未匹配: '{leading_context}{target_content}{trailing_context}'")
                
                # 3. 回退到简单的目标内容替换
                if target_content in original_text:
                    # 检查目标内容是否唯一
                    occurrences = original_text.count(target_content)
                    if occurrences == 1:
                        modified_text = original_text.replace(target_content, new_value, 1)
                        logger.info(f"✓ 使用目标内容直接替换成功（唯一匹配）")
                        return modified_text
                    else:
                        logger.warning(f"目标内容 '{target_content}' 在文本中出现{occurrences}次，无法唯一定位")
                        return original_text
            
            # 4. 如果没有前导上下文，只能直接替换目标内容
            elif target_content in original_text:
                occurrences = original_text.count(target_content)
                if occurrences == 1:
                    modified_text = original_text.replace(target_content, new_value, 1)
                    logger.info(f"✓ 直接替换目标内容成功（唯一匹配）")
                    return modified_text
                else:
                    logger.warning(f"目标内容 '{target_content}' 在文本中出现{occurrences}次，建议提供前导上下文")
                    return original_text
                    
            logger.warning(f"未找到匹配的文本进行替换")
            return original_text
            
        except Exception as e:
            logger.error(f"替换文本时出错: {e}")
            return original_text
    
    def _check_and_update_related_fields(self, target_data: Any, path: str, new_value: Any):
        """
        检查并更新相关联的字段，如指标值修改时更新异常状态
        
        Args:
            target_data: 目标数据结构
            path: 修改的字段路径
            new_value: 新值
        """
        try:
            # 检查是否是指标数据的修改
            if "indicator_series" in path and "value" in path:
                self._update_indicator_abnormal_status(target_data, path, new_value)
            elif "series" in path and isinstance(new_value, (int, float)):
                self._update_indicator_abnormal_status(target_data, path, new_value)
            
            # 可以在这里添加其他关联更新逻辑
            
        except Exception as e:
            logger.error(f"更新关联字段时出错: {e}")
    
    def _update_indicator_abnormal_status(self, target_data: Any, path: str, new_value: Any):
        """
        更新指标的异常状态标识
        
        Args:
            target_data: 目标数据结构
            path: 指标值的路径
            new_value: 新的指标值
        """
        try:
            if not isinstance(new_value, (int, float)):
                return
            
            # 解析路径获取指标信息
            path_parts = path.split('.')
            
            # 查找指标序列数据
            indicators = target_data.get("indicator_series", [])
            if not indicators:
                return
            
            # 根据路径定位到具体的指标和时间点
            for indicator in indicators:
                if not isinstance(indicator, dict):
                    continue
                    
                series = indicator.get("series", [])
                normal_min = indicator.get("normal_min")
                normal_max = indicator.get("normal_max")
                
                # 如果有正常范围，更新异常状态
                if normal_min is not None and normal_max is not None:
                    for series_item in series:
                        if isinstance(series_item, dict) and series_item.get("value") == new_value:
                            # 判断是否异常
                            is_abnormal = not (normal_min <= new_value <= normal_max)
                            series_item["is_abnormal"] = is_abnormal
                            
                            # 更新异常状态描述
                            if is_abnormal:
                                if new_value > normal_max:
                                    series_item["abnormal_type"] = "偏高"
                                elif new_value < normal_min:
                                    series_item["abnormal_type"] = "偏低"
                            else:
                                series_item.pop("abnormal_type", None)
                            
                            logger.info(f"✓ 更新指标异常状态: {indicator.get('name', '')} = {new_value}, 异常: {is_abnormal}")
                            
        except Exception as e:
            logger.error(f"更新指标异常状态时出错: {e}")
    
    def _find_and_replace_text_recursive(self, data: Any, path: str, search_text: str, new_value: str) -> bool:
        """
        递归查找并替换数据结构中包含特定文本的内容
        
        Args:
            data: 要搜索的数据结构
            path: 目标路径（用于日志记录）
            search_text: 要查找的文本
            new_value: 替换的新值
            
        Returns:
            是否成功找到并替换了文本
        """
        try:
            modified = False
            
            if isinstance(data, dict):
                for key, value in data.items():
                    if isinstance(value, str) and search_text in value:
                        # 找到包含目标文本的字符串
                        old_value = value
                        if "替换为" in new_value:
                            # 处理"A替换为B"格式的指令
                            parts = new_value.split("替换为")
                            if len(parts) == 2:
                                replacement_text = parts[1].strip()
                                data[key] = value.replace(search_text, replacement_text)
                                logger.info(f"✓ 替换文本 '{key}': {old_value} -> {data[key]}")
                                modified = True
                        else:
                            # 直接替换
                            data[key] = value.replace(search_text, new_value)
                            logger.info(f"✓ 替换文本 '{key}': {old_value} -> {data[key]}")
                            modified = True
                    elif isinstance(value, (dict, list)):
                        # 递归搜索嵌套结构
                        if self._find_and_replace_text_recursive(value, f"{path}.{key}", search_text, new_value):
                            modified = True
                            
            elif isinstance(data, list):
                for i, item in enumerate(data):
                    if isinstance(item, str) and search_text in item:
                        # 找到包含目标文本的字符串
                        old_value = item
                        if "替换为" in new_value:
                            # 处理"A替换为B"格式的指令
                            parts = new_value.split("替换为")
                            if len(parts) == 2:
                                replacement_text = parts[1].strip()
                                data[i] = item.replace(search_text, replacement_text)
                                logger.info(f"✓ 替换数组文本 [{i}]: {old_value} -> {data[i]}")
                                modified = True
                        else:
                            # 直接替换
                            data[i] = item.replace(search_text, new_value)
                            logger.info(f"✓ 替换数组文本 [{i}]: {old_value} -> {data[i]}")
                            modified = True
                    elif isinstance(item, (dict, list)):
                        # 递归搜索嵌套结构
                        if self._find_and_replace_text_recursive(item, f"{path}[{i}]", search_text, new_value):
                            modified = True
                            
            return modified
            
        except Exception as e:
            logger.error(f"递归文本查找替换时出错: {e}")
            return False
    
    def _save_patient_data_to_output(self, session_id, patient_content, full_structure_data, patient_journey=None, mdt_simple_report=None):
        """将患者数据保存到输出目录"""
        try:
            if not session_id:
                logger.warning("No session_id provided, skipping patient data save")
                return None
            
            # 创建输出目录结构（与intent_determine_crew相同的目录结构）
            output_dir = Path("output/files_extract") / session_id
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # 确保数据中的Unicode编码被正确解码
            def decode_unicode_recursive(obj):
                """递归解码对象中的Unicode转义序列"""
                if isinstance(obj, dict):
                    return {key: decode_unicode_recursive(value) for key, value in obj.items()}
                elif isinstance(obj, list):
                    return [decode_unicode_recursive(item) for item in obj]
                elif isinstance(obj, str):
                    try:
                        # 处理Unicode转义序列
                        if '\\u' in obj:
                            return obj.encode().decode('unicode_escape')
                        return obj
                    except Exception:
                        return obj
                else:
                    return obj
            
            # 准备要保存的数据
            patient_data = {
                "session_id": session_id,
                "timestamp": time.time(),
                "processing_date": datetime.now().isoformat(),
                "patient_content": decode_unicode_recursive(patient_content) if isinstance(patient_content, str) else patient_content,
                "full_structure_data": decode_unicode_recursive(full_structure_data),
                "patient_journey": decode_unicode_recursive(patient_journey) if patient_journey is not None else None,
                "mdt_simple_report": decode_unicode_recursive(mdt_simple_report) if mdt_simple_report is not None else None
            }
            
            # 保存到JSON文件
            output_file = output_dir / "patient_data.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(patient_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"患者数据已保存到: {output_file}")
            
            return str(output_file)
            
        except Exception as e:
            logger.error(f"保存患者数据时出错: {str(e)}")
            return None

    @agent
    def modification_summary_analyzer(self) -> Agent:
        """修改摘要分析专家：识别所有需要修改的位置"""
        return Agent(
            config=self.agents_config['modification_summary_analyzer'],
            llm=general_llm,
            verbose=True
        )

    @agent
    def modification_details_generator(self) -> Agent:
        """修改明细生成专家：生成详细的修改指令"""
        return Agent(
            config=self.agents_config['modification_details_generator'],
            llm=general_llm,
            verbose=True
        )

    @agent
    def update_analyzer(self) -> Agent:
        """更新分析专家：分析用户的更新需求并返回修改指令"""
        return Agent(
            config=self.agents_config['update_analyzer'],
            llm=general_llm,
            verbose=True
        )

    @task
    def analyze_modification_summary_task(self) -> Task:
        """分析修改摘要任务"""
        return Task(
            config=self.tasks_config['analyze_modification_summary_task']
        )

    @task
    def generate_modification_details_task(self) -> Task:
        """生成修改明细任务"""
        return Task(
            config=self.tasks_config['generate_modification_details_task']
        )

    @task
    def analyze_and_modify_task(self) -> Task:
        """分析并生成修改指令任务"""
        return Task(
            config=self.tasks_config['analyze_and_modify_task']
        )

    @crew
    def crew(self) -> Crew:
        """创建患者信息更新crew"""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True
        )

    async def update_patient_info(self, user_request: str, current_patient_data: Dict,
                                  session_id: str = None) -> Dict:
        """
        更新患者信息的主要方法

        Args:
            user_request: 用户的更新请求
            current_patient_data: 当前的患者数据
            session_id: 会话ID

        Returns:
            更新后的患者数据，格式与patient_data_crew保持一致
        """
        try:
            logger.info("Starting patient info update process")
            current_date = datetime.now().strftime("%Y-%m-%d")

            # 🆕 初始化Token管理和数据压缩模块（可选功能）
            # 优先使用主开关 ENABLE_NEW_FEATURES，如果未设置则使用 ENABLE_DATA_COMPRESSION
            enable_new_features = os.getenv('ENABLE_NEW_FEATURES', '').lower()

            if enable_new_features in ('true', '1', 'yes'):
                # 主开关启用 - 启用所有新功能
                enable_compression = True
                logger.info("✅ 主开关已启用 (ENABLE_NEW_FEATURES=true)，将使用所有新功能")
            elif enable_new_features in ('false', '0', 'no'):
                # 主开关禁用 - 使用原有逻辑
                enable_compression = False
                logger.info("ℹ️ 主开关已禁用 (ENABLE_NEW_FEATURES=false)，使用原有逻辑")
            else:
                # 未设置主开关 - 使用细粒度控制
                enable_compression = os.getenv('ENABLE_DATA_COMPRESSION', 'false').lower() in ('true', '1', 'yes')
                if enable_compression:
                    logger.info("✅ 数据压缩功能已启用 (ENABLE_DATA_COMPRESSION=true)")
                else:
                    logger.info("ℹ️ 数据压缩功能未启用（使用原有逻辑），可通过 ENABLE_NEW_FEATURES=true 或 ENABLE_DATA_COMPRESSION=true 启用")

            if not enable_compression:
                # 直接使用原始数据，不压缩
                compressed_patient_data = current_patient_data
            else:
                logger.info("✅ 数据压缩功能已启用")
                token_manager = TokenManager(logger=logger)
                data_compressor = PatientDataCompressor(logger=logger, token_manager=token_manager)

                # 🆕 压缩患者数据（在传递给LLM前）
                model_name = 'deepseek-chat'  # 使用general_llm的模型

                # 检查数据大小
                check_result = token_manager.check_input_limit(current_patient_data, model_name)
                logger.info(f"📊 患者数据统计:")
                logger.info(f"  ├─ 估算总tokens: {check_result['total_tokens']}")
                logger.info(f"  ├─ 模型限制: {check_result['limit']} tokens")
                logger.info(f"  ├─ 安全限制: {check_result['safe_limit']} tokens")
                logger.info(f"  ├─ 使用率: {check_result['usage_ratio']:.1%}")
                logger.info(f"  └─ 需要压缩: {'是 ⚠️' if check_result['compression_needed'] else '否 ✅'}")

                # 如果需要压缩，进行数据压缩
                compressed_patient_data = current_patient_data
                if check_result['compression_needed']:
                    try:
                        logger.warning("=" * 100)
                        logger.warning(f"⚠️ 患者数据超过安全限制，启动自动压缩流程")
                        logger.warning(f"⚠️ 当前: {check_result['total_tokens']} tokens > 安全限制: {check_result['safe_limit']} tokens")
                        logger.warning("=" * 100)

                        # 计算目标token数
                        target_tokens = check_result['safe_limit']

                        # 压缩各个模块的数据
                        compressed_patient_data = {}

                        # 1. 压缩patient_timeline（分配40%的目标token）
                        if "patient_timeline" in current_patient_data:
                            logger.info(f"📦 开始压缩patient_timeline数据 (目标: {int(target_tokens * 0.4)} tokens)...")
                            compressed_patient_data["patient_timeline"] = data_compressor.compress_timeline(
                                current_patient_data["patient_timeline"],
                                max_tokens=int(target_tokens * 0.4),
                                model_name=model_name
                            )
                            logger.info(f"  ✅ patient_timeline压缩完成")

                        # 2. 压缩patient_journey（分配30%的目标token）
                        if "patient_journey" in current_patient_data:
                            logger.info(f"📦 开始压缩patient_journey数据 (目标: {int(target_tokens * 0.3)} tokens)...")
                            compressed_patient_data["patient_journey"] = data_compressor.compress_data(
                                current_patient_data["patient_journey"],
                                max_tokens=int(target_tokens * 0.3),
                                model_name=model_name
                            )
                            logger.info(f"  ✅ patient_journey压缩完成")

                        # 3. 压缩mdt_simple_report（分配30%的目标token）
                        if "mdt_simple_report" in current_patient_data:
                            logger.info(f"📦 开始压缩mdt_simple_report数据 (目标: {int(target_tokens * 0.3)} tokens)...")
                            compressed_patient_data["mdt_simple_report"] = data_compressor.compress_data(
                                current_patient_data["mdt_simple_report"],
                                max_tokens=int(target_tokens * 0.3),
                                model_name=model_name
                            )
                            logger.info(f"  ✅ mdt_simple_report压缩完成")

                        # 保留其他字段
                        for key in current_patient_data:
                            if key not in ["patient_timeline", "patient_journey", "mdt_simple_report"]:
                                compressed_patient_data[key] = current_patient_data[key]

                        # 重新检查压缩后的token数
                        compressed_check = token_manager.check_input_limit(compressed_patient_data, model_name)
                        logger.info("=" * 100)
                        logger.info(f"✅ 数据压缩完成！")
                        logger.info(f"📊 压缩效果:")
                        logger.info(f"  ├─ 原始tokens: {check_result['total_tokens']}")
                        logger.info(f"  ├─ 压缩后tokens: {compressed_check['total_tokens']}")
                        logger.info(f"  ├─ 压缩比例: {compressed_check['total_tokens']/check_result['total_tokens']:.1%}")
                        logger.info(f"  ├─ 新使用率: {compressed_check['usage_ratio']:.1%}")
                        logger.info(f"  └─ 在限制内: {'是 ✅' if compressed_check['within_limit'] else '否 ❌'}")
                        logger.info("=" * 100)
                    except Exception as e:
                        logger.error(f"❌ 数据压缩失败，使用原始数据: {e}")
                        compressed_patient_data = current_patient_data
                else:
                    logger.info("=" * 100)
                    logger.info(f"✅ 数据量在安全范围内，无需压缩")
                    logger.info("=" * 100)

            # ========== 阶段1: 生成修改摘要 ==========
            logger.info("=" * 80)
            logger.info("【阶段1】开始生成修改摘要")
            logger.info("=" * 80)

            summary_inputs = {
                "user_request": user_request,
                "current_patient_data": compressed_patient_data
            }

            # 创建新的Task实例
            summary_task = Task(
                config=self.tasks_config['analyze_modification_summary_task']
            )
            summary_task.interpolate_inputs_and_add_conversation_history(summary_inputs)
            summary_result = self.modification_summary_analyzer().execute_task(summary_task)

            # 解析修改摘要
            modification_summary = JsonUtils.safe_parse_json(summary_result, debug_prefix="Modification summary")
            if not modification_summary or not isinstance(modification_summary, list):
                logger.error("修改摘要解析失败或格式不正确")
                return {
                    "error": f"修改摘要解析失败。原始结果: {str(summary_result)[:200]}..."
                }

            logger.info(f"成功生成修改摘要，包含 {len(modification_summary)} 个修改操作")
            for item in modification_summary:
                logger.info(f"  - {item.get('id')}: {item.get('target_location')} - {item.get('brief_description')}")

            # ========== 阶段2: 分批生成修改明细 ==========
            logger.info("=" * 80)
            logger.info("【阶段2】开始分批生成修改明细")
            logger.info("=" * 80)

            batch_size = 2  # 每批处理2个修改操作
            all_modifications = []

            # 分批处理
            for batch_start in range(0, len(modification_summary), batch_size):
                batch_items = modification_summary[batch_start:batch_start + batch_size]
                batch_num = batch_start // batch_size + 1
                total_batches = (len(modification_summary) + batch_size - 1) // batch_size
                batch_ids = [item.get('id') for item in batch_items]

                logger.info(f"处理第 {batch_num}/{total_batches} 批，包含 {len(batch_items)} 个修改操作")
                logger.info(f"  修改ID: {batch_ids}")

                try:
                    # 创建新的Task实例
                    details_task = Task(
                        config=self.tasks_config['generate_modification_details_task']
                    )

                    details_inputs = {
                        "current_patient_data": compressed_patient_data,
                        "modification_summary": modification_summary,
                        "target_modification_ids": batch_ids
                    }

                    details_task.interpolate_inputs_and_add_conversation_history(details_inputs)
                    details_result = self.modification_details_generator().execute_task(details_task)

                    # 解析修改明细
                    batch_modifications = JsonUtils.safe_parse_json(details_result, debug_prefix=f"Modification details batch {batch_num}")
                    if batch_modifications and isinstance(batch_modifications, list):
                        all_modifications.extend(batch_modifications)
                        logger.info(f"  成功生成 {len(batch_modifications)} 个修改指令")
                    else:
                        logger.warning(f"  批次 {batch_num} 的修改明细解析失败")
                except Exception as e:
                    logger.error(f"处理批次 {batch_num} 时出错: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            logger.info(f"所有修改明细生成完成，共 {len(all_modifications)} 个修改指令")

            # ========== 阶段3: 执行修改操作 ==========
            logger.info("=" * 80)
            logger.info("【阶段3】开始执行修改操作")
            logger.info("=" * 80)

            if not all_modifications:
                logger.warning("没有生成任何修改指令")
                return {
                    "error": "没有生成任何修改指令"
                }

            # 为修改指令添加sequence字段（如果没有的话）
            for idx, mod in enumerate(all_modifications):
                if 'sequence' not in mod:
                    mod['sequence'] = idx + 1

            # 使用代码执行修改指令
            logger.info(f"开始执行修改操作，修改指令数量: {len(all_modifications)}")
            updated_data = self._execute_modifications(current_patient_data, all_modifications)
            logger.info(f"修改操作完成")

            # 准备返回的结果，格式与patient_data_crew保持一致
            # 直接使用原有的patient_content，不做修改
            original_patient_content = current_patient_data.get("patient_content", "")

            result_data = {
                "patient_content": original_patient_content,
                "full_structure_data": updated_data.get("patient_timeline", {}),
                "patient_journey": updated_data.get("patient_journey", {}),
                "mdt_simple_report": updated_data.get("mdt_simple_report", {})
            }

            # 保存患者数据到输出目录（与intent_determine_crew相同的session目录）
            if session_id:
                output_file_path = self._save_patient_data_to_output(
                    session_id,
                    result_data["patient_content"],
                    result_data["full_structure_data"],
                    result_data.get("patient_journey"),
                    result_data.get("mdt_simple_report")
                )
                if output_file_path:
                    logger.info(f"患者数据已保存到输出目录: {output_file_path}")
                else:
                    logger.warning("保存患者数据到输出目录失败")
            else:
                logger.warning("No agent_session_id provided, skipping patient data save")

            return result_data

        except Exception as e:
            logger.error(f"Error updating patient info: {e}")
            logger.error(f"错误类型: {type(e)}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            return {"error": str(e)}

    async def task_async(self, central_command: str, user_requirement: str, 
                        current_patient_data: Dict,
                        writer=None, show_status_realtime: bool = False,
                        agent_session_id: str = None) -> Dict:
        """
        异步任务接口，与其他crew保持一致
        """
        try:
            if show_status_realtime and writer:
                # 发送开始状态
                writer({
                    "type": "status",
                    "agent_name": "患者信息修改专家",
                    "agent_session_id": agent_session_id,
                    "status": "analyzing",
                    "status_msg": "正在分析修改需求并生成修改指令...",
                    "need_feedback": False
                })
            
            # 执行更新操作
            result = await self.update_patient_info(
                user_request=user_requirement,
                current_patient_data=current_patient_data,
                session_id=agent_session_id
            )
            
            if show_status_realtime and writer:
                # 发送完成状态
                if "error" not in result:
                    # 成功情况
                    writer({
                        "type": "status",
                        "agent_name": "患者信息修改专家",
                        "agent_session_id": agent_session_id,
                        "status": "completed",
                        "status_msg": "患者信息修改完成",
                        "need_feedback": False
                    })
                else:
                    # 错误情况
                    writer({
                        "type": "status",
                        "agent_name": "患者信息修改专家",
                        "agent_session_id": agent_session_id,
                        "status": "error",
                        "status_msg": f"患者信息更新失败: {result.get('error', '未知错误')}",
                        "need_feedback": False
                    })
            
            return result
            
        except Exception as e:
            logger.error(f"Error in patient info update task: {e}")
            if show_status_realtime and writer:
                writer({
                    "type": "status",
                    "agent_name": "患者信息修改专家",
                    "agent_session_id": agent_session_id,
                    "status": "error",
                    "status_msg": f"患者信息更新过程中发生错误: {str(e)}",
                    "need_feedback": False
                })
            
            return {"error": str(e)} 