"""
输出分块生成器 - 处理输出长度限制小的模型

功能：
1. 将PPT生成任务拆分成多个子任务
2. 每个子任务生成PPT的一部分
3. 合并所有部分生成完整PPT
"""

import os
import json
from typing import Dict, List, Any, Optional

# 尝试导入dotenv
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class OutputChunkedGenerator:
    """输出分块生成器 - 处理输出长度限制"""

    # PPT数据结构分块策略
    PPT_CHUNKS = {
        'basic_info': {
            'name': '基本信息',
            'fields': ['title', 'patient', 'diag'],
            'priority': 1,
            'estimated_tokens': 500
        },
        'treatments': {
            'name': '治疗信息',
            'fields': ['treatments', 'medications'],
            'priority': 2,
            'estimated_tokens': 2000
        },
        'examinations': {
            'name': '检查信息',
            'fields': ['examinations', 'lab_tests'],
            'priority': 3,
            'estimated_tokens': 2000
        },
        'images': {
            'name': '影像资料',
            'fields': ['images', 'medical_images'],
            'priority': 4,
            'estimated_tokens': 1500
        },
        'timeline': {
            'name': '时间轴',
            'fields': ['timeline', 'events'],
            'priority': 5,
            'estimated_tokens': 1000
        },
        'charts': {
            'name': '图表数据',
            'fields': ['indicators', 'gantt', 'charts'],
            'priority': 6,
            'estimated_tokens': 1000
        }
    }

    def __init__(self, logger=None, token_manager=None):
        """初始化输出分块生成器

        Args:
            logger: 日志记录器
            token_manager: Token管理器
        """
        self.logger = logger
        self.token_manager = token_manager

    def should_use_chunked_output(self, model_name: str, expected_output_size: int = None) -> bool:
        """判断是否需要使用分块输出

        Args:
            model_name: 模型名称
            expected_output_size: 预期输出大小（可选）

        Returns:
            bool: 是否需要分块输出
        """
        if not self.token_manager:
            return False

        # 获取模型配置
        config = self.token_manager.get_model_config(model_name)
        max_output_tokens = config['max_output_tokens']
        safe_output_limit = int(max_output_tokens * config['safe_output_ratio'])

        # 如果没有提供预期输出大小，估算一个
        if expected_output_size is None:
            # 估算：完整PPT数据通常需要8000-15000 tokens
            expected_output_size = 10000

        # 如果预期输出超过安全限制的80%，建议分块
        needs_chunking = expected_output_size > safe_output_limit * 0.8

        if self.logger and needs_chunking:
            self.logger.warning(
                f"⚠️ 预期输出 ({expected_output_size} tokens) 接近或超过模型限制 ({max_output_tokens} tokens)，"
                f"建议使用分块生成"
            )

        return needs_chunking

    def generate_ppt_in_chunks(self, llm, patient_data: Dict[str, Any],
                               template_info: Dict[str, Any],
                               model_name: str = 'gemini-3-flash-preview') -> Dict[str, Any]:
        """分块生成PPT数据

        Args:
            llm: LLM对象
            patient_data: 患者数据
            template_info: 模板信息
            model_name: 模型名称

        Returns:
            dict: 完整的PPT数据
        """
        if self.logger:
            self.logger.info("=" * 100)
            self.logger.info("🔀 启动分块生成模式")
            self.logger.info("=" * 100)

        # 获取模型配置
        config = self.token_manager.get_model_config(model_name) if self.token_manager else {}
        max_output_tokens = config.get('max_output_tokens', 4096)

        # 按优先级排序分块
        sorted_chunks = sorted(
            self.PPT_CHUNKS.items(),
            key=lambda x: x[1]['priority']
        )

        # 存储每个分块的结果
        chunk_results = {}

        # 逐个生成分块
        for chunk_id, chunk_config in sorted_chunks:
            if self.logger:
                self.logger.info(f"\n📦 生成分块 {chunk_config['priority']}/{len(sorted_chunks)}: {chunk_config['name']}")
                self.logger.info(f"  ├─ 包含字段: {chunk_config['fields']}")
                self.logger.info(f"  └─ 预估tokens: {chunk_config['estimated_tokens']}")

            # 生成该分块的数据
            chunk_data = self._generate_chunk(
                llm=llm,
                chunk_id=chunk_id,
                chunk_config=chunk_config,
                patient_data=patient_data,
                template_info=template_info,
                max_output_tokens=max_output_tokens
            )

            if chunk_data:
                chunk_results[chunk_id] = chunk_data
                if self.logger:
                    self.logger.info(f"  ✅ 分块生成成功")
            else:
                if self.logger:
                    self.logger.warning(f"  ⚠️ 分块生成失败，跳过")

        # 合并所有分块
        if self.logger:
            self.logger.info("\n🔗 开始合并所有分块...")

        merged_ppt_data = self._merge_chunks(chunk_results)

        if self.logger:
            self.logger.info("=" * 100)
            self.logger.info(f"✅ 分块生成完成！共生成 {len(chunk_results)} 个分块")
            self.logger.info("=" * 100)

        return merged_ppt_data

    def _generate_chunk(self, llm, chunk_id: str, chunk_config: Dict[str, Any],
                       patient_data: Dict[str, Any], template_info: Dict[str, Any],
                       max_output_tokens: int) -> Optional[Dict[str, Any]]:
        """生成单个分块

        Args:
            llm: LLM对象
            chunk_id: 分块ID
            chunk_config: 分块配置
            patient_data: 患者数据
            template_info: 模板信息
            max_output_tokens: 最大输出tokens

        Returns:
            dict: 分块数据
        """
        # 构建针对该分块的提示词
        prompt = self._build_chunk_prompt(
            chunk_id=chunk_id,
            chunk_config=chunk_config,
            patient_data=patient_data,
            template_info=template_info
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
            chunk_data = JsonUtils.safe_parse_json(response_text, debug_prefix=f"分块{chunk_id}")

            return chunk_data

        except Exception as e:
            if self.logger:
                self.logger.error(f"生成分块 {chunk_id} 时出错: {e}")
            return None

    def _build_chunk_prompt(self, chunk_id: str, chunk_config: Dict[str, Any],
                           patient_data: Dict[str, Any], template_info: Dict[str, Any]) -> str:
        """构建分块生成的提示词

        Args:
            chunk_id: 分块ID
            chunk_config: 分块配置
            patient_data: 患者数据
            template_info: 模板信息

        Returns:
            str: 提示词
        """
        fields = chunk_config['fields']
        chunk_name = chunk_config['name']

        # 从模板中提取该分块相关的字段说明
        template_json_str = template_info.get('template_json', '{}')

        prompt = f"""你是一个医疗数据转换专家。现在需要生成PPT的【{chunk_name}】部分。

**任务**: 只生成以下字段的数据：{', '.join(fields)}

**模板说明**（完整模板，但你只需要生成上述字段）:
{template_json_str}

**患者数据**:
{json.dumps(patient_data, ensure_ascii=False, indent=2)}

**重要要求**:
1. 只生成 {', '.join(fields)} 这些字段
2. 严格按照模板结构输出
3. 只使用患者数据中真实存在的信息
4. 直接输出JSON格式，不要包含任何解释文字
5. 不要包含Markdown代码块标记（如```json）

请输出JSON数据:"""

        return prompt

    def _merge_chunks(self, chunk_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """合并所有分块

        Args:
            chunk_results: 分块结果字典

        Returns:
            dict: 合并后的完整PPT数据
        """
        merged = {
            'pptTemplate2Vm': {}
        }

        # 按优先级顺序合并
        for chunk_id in sorted(chunk_results.keys(),
                              key=lambda x: self.PPT_CHUNKS[x]['priority']):
            chunk_data = chunk_results[chunk_id]

            # 如果分块数据有pptTemplate2Vm包装，解包
            if 'pptTemplate2Vm' in chunk_data:
                chunk_data = chunk_data['pptTemplate2Vm']

            # 合并到总数据中
            for key, value in chunk_data.items():
                if key not in merged['pptTemplate2Vm']:
                    merged['pptTemplate2Vm'][key] = value
                elif isinstance(value, list) and isinstance(merged['pptTemplate2Vm'][key], list):
                    # 列表类型：合并
                    merged['pptTemplate2Vm'][key].extend(value)
                elif isinstance(value, dict) and isinstance(merged['pptTemplate2Vm'][key], dict):
                    # 字典类型：更新
                    merged['pptTemplate2Vm'][key].update(value)
                else:
                    # 其他类型：覆盖
                    merged['pptTemplate2Vm'][key] = value

        return merged

    def estimate_output_size(self, patient_data: Dict[str, Any]) -> int:
        """估算输出大小

        Args:
            patient_data: 患者数据

        Returns:
            int: 估算的输出tokens数
        """
        # 简单估算：基于输入数据量
        if not self.token_manager:
            # 如果没有token_manager，使用简单估算
            input_size = len(json.dumps(patient_data, ensure_ascii=False))
            # 假设输出是输入的1.5倍
            return int(input_size / 2 * 1.5)

        # 使用token_manager估算
        input_tokens = self.token_manager.estimate_tokens(patient_data)

        # 估算输出tokens（通常是输入的0.8-1.2倍）
        estimated_output = int(input_tokens * 1.0)

        return estimated_output

    def get_chunk_strategy(self, model_name: str) -> str:
        """获取分块策略建议

        Args:
            model_name: 模型名称

        Returns:
            str: 策略建议
        """
        if not self.token_manager:
            return "无法获取策略建议（缺少token_manager）"

        config = self.token_manager.get_model_config(model_name)
        max_output = config['max_output_tokens']

        if max_output >= 32000:
            return "large_output"  # 大输出模型，通常不需要分块
        elif max_output >= 8000:
            return "medium_output"  # 中等输出，可能需要分块
        else:
            return "small_output"  # 小输出模型，强烈建议分块
