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
                
                # 执行具体的修改操作
                if action == "set":
                    # 直接设置字段值
                    self._set_value_by_path(target_data, target_path, new_value)
                    # 检查是否需要关联更新（如指标异常状态）
                    self._check_and_update_related_fields(target_data, target_path, new_value)
                elif action == "modify_text":
                    # 基于前导上下文的文本修改
                    self._modify_text_by_path(target_data, target_path, new_value, 
                                            leading_context, target_content, trailing_context)
                elif action == "delete":
                    # 删除操作保留，用于删除整个条目
                    self._delete_value_by_path(target_data, target_path)
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
    
    def _set_value_by_path(self, target_data: Any, path: str, new_value: Any):
        """通过路径设置值 - 核心方法"""
        try:
            parts = path.split('.')
            current = target_data
            
            # 遍历到倒数第二层
            for part in parts[:-1]:
                if '[' in part and ']' in part:
                    # 处理数组索引
                    key = part.split('[')[0]
                    index = int(part.split('[')[1].split(']')[0])
                    if key not in current:
                        logger.error(f"键 '{key}' 不存在于当前数据中")
                        return
                    if not isinstance(current[key], list) or index >= len(current[key]):
                        logger.error(f"数组索引 {index} 超出范围或 '{key}' 不是数组")
                        return
                    current = current[key][index]
                else:
                    if part not in current:
                        logger.error(f"键 '{part}' 不存在于当前数据中")
                        return
                    current = current[part]
            
            # 设置最后一层的值
            final_key = parts[-1]
            if '[' in final_key and ']' in final_key:
                key = final_key.split('[')[0]
                index = int(final_key.split('[')[1].split(']')[0])
                if key not in current:
                    logger.error(f"键 '{key}' 不存在于当前数据中")
                    return
                if not isinstance(current[key], list) or index >= len(current[key]):
                    logger.error(f"数组索引 {index} 超出范围或 '{key}' 不是数组")
                    return
                current[key][index] = new_value
            else:
                current[final_key] = new_value
                
            logger.info(f"✓ 成功设置路径 {path} 的值为: {new_value}")
            
        except Exception as e:
            logger.error(f"通过路径设置值时出错 - 路径: {path}, 新值: {new_value}, 错误: {e}")
            import traceback
            logger.error(f"错误堆栈: {traceback.format_exc()}")
    
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
            parts = path.split('.')
            current = target_data
            
            # 遍历到倒数第二层
            for part in parts[:-1]:
                if '[' in part and ']' in part:
                    # 处理数组索引
                    key = part.split('[')[0]
                    index = int(part.split('[')[1].split(']')[0])
                    if key not in current or not isinstance(current[key], list):
                        logger.error(f"路径错误: {part}")
                        return
                    current = current[key][index]
                else:
                    if part not in current:
                        logger.error(f"路径错误: {part}")
                        return
                    current = current[part]
            
            # 修改最后一层的文本内容
            final_key = parts[-1]
            if '[' in final_key and ']' in final_key:
                key = final_key.split('[')[0]
                index = int(final_key.split('[')[1].split(']')[0])
                if key in current and isinstance(current[key], list):
                    original_text = current[key][index]
                    if isinstance(original_text, str):
                        modified_text = self._replace_text_with_context(
                            original_text, leading_context, target_content, 
                            trailing_context, new_value
                        )
                        current[key][index] = modified_text
                        logger.info(f"✓ 成功修改文本: {original_text} -> {modified_text}")
            else:
                if final_key in current and isinstance(current[final_key], str):
                    original_text = current[final_key]
                    modified_text = self._replace_text_with_context(
                        original_text, leading_context, target_content, 
                        trailing_context, new_value
                    )
                    current[final_key] = modified_text
                    logger.info(f"✓ 成功修改文本: {original_text} -> {modified_text}")
                    
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
    def update_analyzer(self) -> Agent:
        """更新分析专家：分析用户的更新需求并返回修改指令"""
        return Agent(
            config=self.agents_config['update_analyzer'],
            llm=general_llm,
            verbose=True
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
            
            # 使用agent分析并生成修改指令
            inputs = {
                "user_request": user_request,
                "current_patient_data": current_patient_data
            }
            
            self.analyze_and_modify_task().interpolate_inputs_and_add_conversation_history(inputs)
            result = self.update_analyzer().execute_task(self.analyze_and_modify_task())
            
            # 记录原始结果用于调试
            logger.info(f"Agent 原始返回结果类型: {type(result)}")
            logger.info(f"Agent 原始返回结果: {str(result)[:500]}...")  # 只显示前500个字符
            
            # 解析修改指令
            parsed_instructions = JsonUtils.safe_parse_json(result, debug_prefix="Modification instructions")
            
            # 记录解析结果用于调试
            logger.info(f"解析后的指令类型: {type(parsed_instructions)}")
            logger.info(f"解析后的指令内容: {parsed_instructions}")
            
            # 检查解析结果是否为空或无效
            if not parsed_instructions:
                logger.error("Agent返回的结果无法解析为有效的JSON格式")
                logger.error(f"原始结果: {str(result)}")
                return {
                    "error": f"Agent返回的结果无法解析为有效的JSON格式。原始结果: {str(result)[:200]}..."
                }
            
            if parsed_instructions and isinstance(parsed_instructions, dict):
                modifications = parsed_instructions.get("modifications", [])
                operation_type = parsed_instructions.get("operation_type", "single")
                total_modifications = parsed_instructions.get("total_modifications", len(modifications))
                consistency_updates = parsed_instructions.get("consistency_updates", [])
                reasoning = parsed_instructions.get("reasoning", "")
                
                logger.info(f"收到修改指令 - 操作类型: {operation_type}, 总修改数: {total_modifications}")
                logger.info(f"分析推理: {reasoning}")
                
                # 记录一致性更新信息
                if consistency_updates:
                    for update in consistency_updates:
                        logger.info(f"一致性更新: {update.get('description', '')}")
                        logger.info(f"涉及模块: {update.get('affected_modules', [])}")
                
                # 使用代码执行修改指令
                logger.info(f"开始执行修改操作，修改指令数量: {len(modifications)}")
                updated_data = self._execute_modifications(current_patient_data, modifications)
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
                
            else:
                logger.warning("Failed to parse modification instructions")
                return {
                    "error": "Failed to parse modification instructions",
                    "raw": result
                }
            
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