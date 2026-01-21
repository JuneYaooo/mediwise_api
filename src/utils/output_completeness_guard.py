"""
输出完整性保护 - 确保所有必需信息都被输出

功能：
1. 验证PPT数据完整性
2. 检测缺失字段
3. 请求LLM补全缺失数据
"""

import json
from typing import Dict, List, Any, Set


class OutputCompletenessGuard:
    """输出完整性保护 - 确保所有必需信息都被输出"""

    # PPT模板必需字段（根据实际模板调整）
    REQUIRED_FIELDS = {
        'pptTemplate2Vm': {
            'title': str,  # 标题
            'patient': dict,  # 患者信息
            'diag': dict,  # 诊断信息
        }
    }

    # 重要字段（建议包含但非必需）
    IMPORTANT_FIELDS = {
        'pptTemplate2Vm': {
            'treatments': list,  # 治疗信息
            'examinations': list,  # 检查信息
            'images': list,  # 图片信息
        }
    }

    def __init__(self, logger=None):
        """初始化输出完整性保护

        Args:
            logger: 日志记录器（可选）
        """
        self.logger = logger

    def validate_ppt_data(self, ppt_data: Dict[str, Any], patient_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """验证PPT数据完整性

        Args:
            ppt_data: PPT数据
            patient_data: 患者数据（可选，用于验证数据一致性）

        Returns:
            dict: 验证结果
                - is_complete: bool, 是否完整
                - missing_required_fields: list, 缺失的必需字段
                - missing_important_fields: list, 缺失的重要字段
                - suggestions: list, 补全建议
        """
        if not ppt_data:
            return {
                'is_complete': False,
                'missing_required_fields': ['pptTemplate2Vm'],
                'missing_important_fields': [],
                'suggestions': ['PPT数据为空，需要重新生成']
            }

        missing_required = []
        missing_important = []
        suggestions = []

        # 检查必需字段
        for parent_key, fields in self.REQUIRED_FIELDS.items():
            if parent_key not in ppt_data:
                missing_required.append(parent_key)
                suggestions.append(f"缺少顶层字段: {parent_key}")
                continue

            parent_data = ppt_data[parent_key]
            if not isinstance(parent_data, dict):
                missing_required.append(parent_key)
                suggestions.append(f"字段 {parent_key} 类型错误，应为dict")
                continue

            for field_name, field_type in fields.items():
                if field_name not in parent_data:
                    missing_required.append(f"{parent_key}.{field_name}")
                    suggestions.append(f"缺少必需字段: {parent_key}.{field_name}")
                elif not isinstance(parent_data[field_name], field_type):
                    missing_required.append(f"{parent_key}.{field_name}")
                    suggestions.append(f"字段 {parent_key}.{field_name} 类型错误，应为{field_type.__name__}")

        # 检查重要字段
        for parent_key, fields in self.IMPORTANT_FIELDS.items():
            if parent_key not in ppt_data:
                continue

            parent_data = ppt_data[parent_key]
            if not isinstance(parent_data, dict):
                continue

            for field_name, field_type in fields.items():
                if field_name not in parent_data:
                    missing_important.append(f"{parent_key}.{field_name}")
                    suggestions.append(f"建议添加字段: {parent_key}.{field_name}")
                elif not isinstance(parent_data[field_name], field_type):
                    missing_important.append(f"{parent_key}.{field_name}")
                    suggestions.append(f"字段 {parent_key}.{field_name} 类型错误，应为{field_type.__name__}")

        is_complete = len(missing_required) == 0

        result = {
            'is_complete': is_complete,
            'missing_required_fields': missing_required,
            'missing_important_fields': missing_important,
            'suggestions': suggestions
        }

        if self.logger:
            if is_complete:
                self.logger.info("✅ PPT数据完整性验证通过")
                if missing_important:
                    self.logger.warning(f"⚠️ 缺少 {len(missing_important)} 个重要字段: {missing_important}")
            else:
                self.logger.error(f"❌ PPT数据不完整，缺少 {len(missing_required)} 个必需字段: {missing_required}")

        return result

    def request_missing_data(self, llm, missing_fields: List[str], context: Dict[str, Any]) -> Dict[str, Any]:
        """针对缺失字段单独请求LLM生成

        策略：
        - 只请求缺失的部分
        - 使用更小的上下文
        - 合并到原始结果

        Args:
            llm: LLM对象
            missing_fields: 缺失字段列表
            context: 上下文信息（包含患者数据等）

        Returns:
            dict: 补全的数据
        """
        if not missing_fields:
            return {}

        if self.logger:
            self.logger.info(f"🔧 请求LLM补全 {len(missing_fields)} 个缺失字段...")

        # 构建补全提示词
        prompt = f"""请根据以下患者数据，生成缺失的PPT字段。

缺失的字段：
{json.dumps(missing_fields, ensure_ascii=False, indent=2)}

患者数据（摘要）：
{self._create_context_summary(context)}

请只输出缺失字段的JSON数据，格式如下：
{{
  "pptTemplate2Vm": {{
    "field_name": "value",
    ...
  }}
}}

只输出JSON，不要包含任何解释文字。"""

        try:
            # 调用LLM
            if hasattr(llm, 'call'):
                response = llm.call(prompt)
                response_text = str(response)
            else:
                response = llm.invoke(prompt)
                response_text = response.content if hasattr(response, 'content') else str(response)

            # 解析JSON
            from src.utils.json_utils import JsonUtils
            补全数据 = JsonUtils.safe_parse_json(response_text, debug_prefix="补全缺失字段")

            if 补全数据:
                if self.logger:
                    self.logger.info(f"✅ 成功补全 {len(missing_fields)} 个字段")
                return 补全数据
            else:
                if self.logger:
                    self.logger.error("❌ 补全失败：无法解析LLM响应")
                return {}

        except Exception as e:
            if self.logger:
                self.logger.error(f"❌ 补全失败: {e}")
            return {}

    def merge_补全数据(self, original: Dict[str, Any], 补全: Dict[str, Any]) -> Dict[str, Any]:
        """合并原始数据和补全数据

        Args:
            original: 原始数据
            补全: 补全数据

        Returns:
            dict: 合并后的数据
        """
        if not 补全:
            return original

        merged = original.copy()

        # 递归合并
        for key, value in 补全.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                # 递归合并字典
                merged[key] = self._merge_dicts(merged[key], value)
            else:
                # 直接覆盖或添加
                merged[key] = value

        if self.logger:
            self.logger.info("✅ 数据合并完成")

        return merged

    def _merge_dicts(self, dict1: Dict, dict2: Dict) -> Dict:
        """递归合并两个字典

        Args:
            dict1: 字典1
            dict2: 字典2

        Returns:
            dict: 合并后的字典
        """
        merged = dict1.copy()

        for key, value in dict2.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = self._merge_dicts(merged[key], value)
            elif key in merged and isinstance(merged[key], list) and isinstance(value, list):
                # 合并列表（去重）
                merged[key] = merged[key] + [item for item in value if item not in merged[key]]
            else:
                merged[key] = value

        return merged

    def _create_context_summary(self, context: Dict[str, Any], max_length: int = 1000) -> str:
        """创建上下文摘要（用于补全提示词）

        Args:
            context: 上下文信息
            max_length: 最大长度

        Returns:
            str: 上下文摘要
        """
        # 提取关键信息
        summary = {}

        if 'patient_name' in context:
            summary['patient_name'] = context['patient_name']

        if 'patient_timeline' in context:
            timeline = context['patient_timeline']
            if isinstance(timeline, list):
                summary['timeline_count'] = len(timeline)
                if timeline:
                    summary['latest_record'] = timeline[0] if isinstance(timeline[0], dict) else str(timeline[0])[:100]

        if 'raw_files_data' in context:
            files = context['raw_files_data']
            if isinstance(files, list):
                summary['files_count'] = len(files)

        # 转换为JSON字符串
        summary_str = json.dumps(summary, ensure_ascii=False, indent=2)

        # 截断到最大长度
        if len(summary_str) > max_length:
            summary_str = summary_str[:max_length] + "..."

        return summary_str

    def check_data_consistency(self, ppt_data: Dict[str, Any], patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """检查PPT数据与患者数据的一致性

        Args:
            ppt_data: PPT数据
            patient_data: 患者数据

        Returns:
            dict: 一致性检查结果
                - is_consistent: bool, 是否一致
                - inconsistencies: list, 不一致的地方
        """
        inconsistencies = []

        # 检查患者姓名
        if 'pptTemplate2Vm' in ppt_data and 'patient' in ppt_data['pptTemplate2Vm']:
            ppt_patient = ppt_data['pptTemplate2Vm']['patient']
            patient_name = patient_data.get('patient_name', '')

            if isinstance(ppt_patient, dict):
                ppt_name = ppt_patient.get('name', '')
                if ppt_name and patient_name and ppt_name != patient_name:
                    inconsistencies.append(f"患者姓名不一致: PPT={ppt_name}, 原始={patient_name}")

        # 可以添加更多一致性检查...

        is_consistent = len(inconsistencies) == 0

        if self.logger:
            if is_consistent:
                self.logger.info("✅ 数据一致性检查通过")
            else:
                self.logger.warning(f"⚠️ 发现 {len(inconsistencies)} 处数据不一致: {inconsistencies}")

        return {
            'is_consistent': is_consistent,
            'inconsistencies': inconsistencies
        }
