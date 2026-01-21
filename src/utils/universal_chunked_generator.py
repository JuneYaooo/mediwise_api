"""
通用JSON分块生成器 - 支持任意JSON结构的分块生成

适用场景：
1. PPT生成（pptTemplate2Vm）
2. 患者信息结构化（patient_structured_data）
3. 任何需要大量输出的JSON生成任务
"""

import os
import json
from typing import Dict, List, Any, Optional, Tuple

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class UniversalChunkedGenerator:
    """通用JSON分块生成器"""

    # 预定义的分块配置
    CHUNK_CONFIGS = {
        # PPT生成的分块配置
        'ppt_generation': {
            'root_key': 'pptTemplate2Vm',
            'chunks': [
                {
                    'name': '基本信息',
                    'fields': ['title', 'patient', 'diag'],
                    'priority': 1,
                    'max_tokens': 1000
                },
                {
                    'name': '治疗信息',
                    'fields': ['treatments', 'medications', 'surgeries'],
                    'priority': 2,
                    'max_tokens': 3000
                },
                {
                    'name': '检查信息',
                    'fields': ['examinations', 'lab_tests', 'vital_signs'],
                    'priority': 3,
                    'max_tokens': 3000
                },
                {
                    'name': '影像资料',
                    'fields': ['images', 'medical_images', 'scans'],
                    'priority': 4,
                    'max_tokens': 2000
                },
                {
                    'name': '时间轴和图表',
                    'fields': ['timeline', 'events', 'indicators', 'gantt', 'charts'],
                    'priority': 5,
                    'max_tokens': 2000
                }
            ]
        },

        # 患者信息结构化的分块配置
        'patient_structuring': {
            'root_key': 'patient_structured_data',
            'chunks': [
                {
                    'name': '基本信息',
                    'fields': ['patient_info', 'demographics', 'contact'],
                    'priority': 1,
                    'max_tokens': 500
                },
                {
                    'name': '诊断信息',
                    'fields': ['diagnoses', 'chief_complaint', 'present_illness'],
                    'priority': 2,
                    'max_tokens': 2000
                },
                {
                    'name': '用药信息',
                    'fields': ['medications', 'allergies', 'adverse_reactions'],
                    'priority': 3,
                    'max_tokens': 2000
                },
                {
                    'name': '检查检验',
                    'fields': ['lab_tests', 'examinations', 'imaging_studies'],
                    'priority': 4,
                    'max_tokens': 3000
                },
                {
                    'name': '治疗记录',
                    'fields': ['treatments', 'procedures', 'surgeries'],
                    'priority': 5,
                    'max_tokens': 3000
                },
                {
                    'name': '病史和随访',
                    'fields': ['medical_history', 'family_history', 'follow_ups'],
                    'priority': 6,
                    'max_tokens': 2000
                }
            ]
        }
    }

    def __init__(self, logger=None, token_manager=None):
        """初始化通用分块生成器

        Args:
            logger: 日志记录器
            token_manager: Token管理器
        """
        self.logger = logger
        self.token_manager = token_manager

    def should_use_chunking(self, task_type: str, model_name: str,
                           expected_output_size: int = None) -> bool:
        """判断是否需要使用分块生成

        Args:
            task_type: 任务类型（'ppt_generation' 或 'patient_structuring'）
            model_name: 模型名称
            expected_output_size: 预期输出大小（可选）

        Returns:
            bool: 是否需要分块
        """
        if not self.token_manager:
            return False

        # 获取模型配置
        config = self.token_manager.get_model_config(model_name)
        max_output_tokens = config['max_output_tokens']
        safe_output_limit = int(max_output_tokens * config['safe_output_ratio'])

        # 如果没有提供预期输出大小，根据任务类型估算
        if expected_output_size is None:
            if task_type == 'ppt_generation':
                expected_output_size = 10000  # PPT通常需要10K tokens
            elif task_type == 'patient_structuring':
                expected_output_size = 8000   # 患者结构化通常需要8K tokens
            else:
                expected_output_size = 5000   # 默认5K tokens

        # 如果预期输出超过安全限制的80%，建议分块
        needs_chunking = expected_output_size > safe_output_limit * 0.8

        if self.logger and needs_chunking:
            self.logger.warning(
                f"⚠️ 任务 [{task_type}] 预期输出 ({expected_output_size} tokens) "
                f"接近或超过模型限制 ({max_output_tokens} tokens)，建议使用分块生成"
            )

        return needs_chunking

    def generate_in_chunks(self, llm, task_type: str, input_data: Dict[str, Any],
                          template_or_schema: str, model_name: str = 'gemini-3-flash-preview',
                          custom_chunks: List[Dict] = None) -> Dict[str, Any]:
        """分块生成JSON数据（带上下文传递）

        Args:
            llm: LLM对象
            task_type: 任务类型（'ppt_generation' 或 'patient_structuring'）
            input_data: 输入数据（患者数据等）
            template_or_schema: 模板或Schema说明
            model_name: 模型名称
            custom_chunks: 自定义分块配置（可选）

        Returns:
            dict: 完整的JSON数据
        """
        if self.logger:
            self.logger.info("=" * 100)
            self.logger.info(f"🔀 启动分块生成模式（带上下文传递）- 任务类型: {task_type}")
            self.logger.info("=" * 100)

        # 获取分块配置
        if custom_chunks:
            chunk_config = {'chunks': custom_chunks, 'root_key': 'data'}
        else:
            chunk_config = self.CHUNK_CONFIGS.get(task_type)
            if not chunk_config:
                if self.logger:
                    self.logger.error(f"❌ 未知的任务类型: {task_type}")
                return None

        root_key = chunk_config['root_key']
        chunks = sorted(chunk_config['chunks'], key=lambda x: x['priority'])

        # 存储每个分块的结果
        chunk_results = {}

        # 🆕 累积的上下文（已生成的内容）
        accumulated_context = {}

        # 逐个生成分块
        for i, chunk in enumerate(chunks, 1):
            if self.logger:
                self.logger.info(f"\n📦 生成分块 {i}/{len(chunks)}: {chunk['name']}")
                self.logger.info(f"  ├─ 包含字段: {chunk['fields']}")
                self.logger.info(f"  ├─ 最大tokens: {chunk['max_tokens']}")
                if accumulated_context:
                    self.logger.info(f"  └─ 上下文: 已生成 {len(accumulated_context)} 个字段")

            # 🆕 生成该分块的数据（传入已生成的上下文）
            chunk_data = self._generate_single_chunk(
                llm=llm,
                chunk=chunk,
                input_data=input_data,
                template_or_schema=template_or_schema,
                root_key=root_key,
                task_type=task_type,
                previous_context=accumulated_context  # 传入上下文
            )

            if chunk_data:
                chunk_results[chunk['name']] = chunk_data

                # 🆕 更新累积上下文
                if root_key in chunk_data:
                    accumulated_context.update(chunk_data[root_key])
                else:
                    accumulated_context.update(chunk_data)

                if self.logger:
                    self.logger.info(f"  ✅ 分块生成成功")
                    self.logger.info(f"  ✅ 上下文已更新: {list(accumulated_context.keys())}")
            else:
                if self.logger:
                    self.logger.warning(f"  ⚠️ 分块生成失败，跳过")

        # 合并所有分块
        if self.logger:
            self.logger.info("\n🔗 开始合并所有分块...")

        merged_data = self._merge_chunks(chunk_results, root_key)

        if self.logger:
            self.logger.info("=" * 100)
            self.logger.info(f"✅ 分块生成完成！共生成 {len(chunk_results)} 个分块")
            self.logger.info(f"📦 {root_key} 包含字段: {list(merged_data.get(root_key, {}).keys())}")
            self.logger.info("=" * 100)

        return merged_data

    def _generate_single_chunk(self, llm, chunk: Dict, input_data: Dict[str, Any],
                               template_or_schema: str, root_key: str,
                               task_type: str, previous_context: Dict[str, Any] = None) -> Optional[Dict[str, Any]]:
        """生成单个分块

        Args:
            llm: LLM对象
            chunk: 分块配置
            input_data: 输入数据
            template_or_schema: 模板或Schema
            root_key: 根键名
            task_type: 任务类型
            previous_context: 之前已生成的上下文（用于保持一致性）

        Returns:
            dict: 分块数据
        """
        # 构建提示词
        prompt = self._build_chunk_prompt(
            chunk=chunk,
            input_data=input_data,
            template_or_schema=template_or_schema,
            root_key=root_key,
            task_type=task_type,
            previous_context=previous_context
        )

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
            chunk_data = JsonUtils.safe_parse_json(response_text, debug_prefix=f"分块_{chunk['name']}")

            return chunk_data

        except Exception as e:
            if self.logger:
                self.logger.error(f"生成分块 {chunk['name']} 时出错: {e}")
            return None

    def _build_chunk_prompt(self, chunk: Dict, input_data: Dict[str, Any],
                           template_or_schema: str, root_key: str,
                           task_type: str, previous_context: Dict[str, Any] = None) -> str:
        """构建分块生成的提示词

        Args:
            chunk: 分块配置
            input_data: 输入数据
            template_or_schema: 模板或Schema
            root_key: 根键名
            task_type: 任务类型
            previous_context: 之前已生成的上下文（用于保持一致性）

        Returns:
            str: 提示词
        """
        fields = chunk['fields']
        chunk_name = chunk['name']

        # 根据任务类型定制提示词
        if task_type == 'ppt_generation':
            task_description = "生成PPT数据"
        elif task_type == 'patient_structuring':
            task_description = "结构化患者信息"
        else:
            task_description = "生成JSON数据"

        # 🆕 构建上下文说明（如果有之前生成的内容）
        context_section = ""
        if previous_context and len(previous_context) > 0:
            context_section = f"""

**已生成的内容**（请保持一致，不要产生矛盾）:
{json.dumps(previous_context, ensure_ascii=False, indent=2)}

**上下文一致性要求**:
- 你生成的内容必须与上述已生成的内容保持逻辑一致
- 例如：如果患者诊断是"高血压"，治疗方案应该是降压药，不能是降糖药
- 如果患者年龄是45岁，不要在其他地方说50岁
- 保持所有日期、名称、数值、诊断信息的一致性
- 引用的文件名、检查项目名称必须与已生成内容一致
"""

        prompt = f"""你是一个医疗数据处理专家。现在需要{task_description}的【{chunk_name}】部分。

**任务**: 只生成以下字段的数据：{', '.join(fields)}

**完整模板/Schema**（你只需要生成上述字段）:
{template_or_schema}

**输入数据**:
{json.dumps(input_data, ensure_ascii=False, indent=2)}
{context_section}
**重要要求**:
1. 只生成 {', '.join(fields)} 这些字段
2. 严格按照模板/Schema结构输出
3. 只使用输入数据中真实存在的信息，不要编造
4. 输出格式必须是：
   {{
     "{root_key}": {{
       "field1": ...,
       "field2": ...
     }}
   }}
5. 直接输出JSON，不要包含任何解释文字
6. 不要包含Markdown代码块标记（如```json）

请输出JSON数据:"""

        return prompt

    def _merge_chunks(self, chunk_results: Dict[str, Dict[str, Any]],
                     root_key: str) -> Dict[str, Any]:
        """合并所有分块

        Args:
            chunk_results: 分块结果字典
            root_key: 根键名

        Returns:
            dict: 合并后的完整数据
        """
        merged = {root_key: {}}

        # 合并所有分块
        for chunk_name, chunk_data in chunk_results.items():
            # 如果分块数据有root_key包装，解包
            if root_key in chunk_data:
                chunk_data = chunk_data[root_key]

            # 合并到总数据中
            for key, value in chunk_data.items():
                if key not in merged[root_key]:
                    merged[root_key][key] = value
                elif isinstance(value, list) and isinstance(merged[root_key][key], list):
                    # 列表类型：合并
                    merged[root_key][key].extend(value)
                elif isinstance(value, dict) and isinstance(merged[root_key][key], dict):
                    # 字典类型：更新
                    merged[root_key][key].update(value)
                else:
                    # 其他类型：覆盖
                    merged[root_key][key] = value

        return merged

    def estimate_output_size(self, task_type: str, input_data: Dict[str, Any]) -> int:
        """估算输出大小

        Args:
            task_type: 任务类型
            input_data: 输入数据

        Returns:
            int: 估算的输出tokens数
        """
        if not self.token_manager:
            # 简单估算
            input_size = len(json.dumps(input_data, ensure_ascii=False))
            return int(input_size / 2 * 1.2)

        # 使用token_manager估算
        input_tokens = self.token_manager.estimate_tokens(input_data)

        # 根据任务类型调整估算比例
        if task_type == 'ppt_generation':
            # PPT输出通常是输入的1.0-1.5倍
            estimated_output = int(input_tokens * 1.2)
        elif task_type == 'patient_structuring':
            # 患者结构化输出通常是输入的0.8-1.2倍
            estimated_output = int(input_tokens * 1.0)
        else:
            estimated_output = int(input_tokens * 1.0)

        return estimated_output

    def create_custom_chunks(self, field_groups: List[Tuple[str, List[str], int]]) -> List[Dict]:
        """创建自定义分块配置

        Args:
            field_groups: 字段分组列表，每个元素是 (分块名称, 字段列表, 最大tokens)

        Returns:
            list: 分块配置列表

        Example:
            field_groups = [
                ('基本信息', ['name', 'age', 'gender'], 500),
                ('诊断信息', ['diagnoses', 'symptoms'], 2000),
            ]
        """
        chunks = []
        for i, (name, fields, max_tokens) in enumerate(field_groups, 1):
            chunks.append({
                'name': name,
                'fields': fields,
                'priority': i,
                'max_tokens': max_tokens
            })
        return chunks
