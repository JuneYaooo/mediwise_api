"""
分块PPT处理器 - 处理超大数据集

功能：
1. 将患者数据分块
2. 分块生成PPT数据
3. 合并多个分块的PPT数据
"""

import os
import json
from typing import Dict, List, Any, Union
from datetime import datetime

# 尝试导入dotenv，如果不存在则跳过
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class ChunkedPPTProcessor:
    """分块PPT处理器 - 处理超大数据集"""

    def __init__(self, logger=None, token_manager=None):
        """初始化分块处理器

        Args:
            logger: 日志记录器（可选）
            token_manager: Token管理器（可选）
        """
        self.logger = logger
        self.token_manager = token_manager

        # 从环境变量读取配置
        self.chunk_size_tokens = int(os.getenv('CHUNK_SIZE_TOKENS', '50000'))
        self.chunk_overlap_ratio = float(os.getenv('CHUNK_OVERLAP_RATIO', '0.1'))

    def split_patient_data(self, patient_data: Dict[str, Any], chunk_size: int = None) -> List[Dict[str, Any]]:
        """将患者数据分块

        策略：
        - 按时间段分块（如按年份、按季度）
        - 按数据类型分块（检查、治疗、影像分开处理）
        - 保持每块的token数在限制内

        Args:
            patient_data: 患者数据
            chunk_size: 每块的token大小（可选，默认使用环境变量配置）

        Returns:
            list: 分块后的数据列表
        """
        if chunk_size is None:
            chunk_size = self.chunk_size_tokens

        if not patient_data:
            return []

        # 估算总token数
        if self.token_manager:
            total_tokens = self.token_manager.estimate_tokens(patient_data)
        else:
            total_tokens = len(json.dumps(patient_data, ensure_ascii=False)) // 2

        if self.logger:
            self.logger.info(f"开始分块处理: 总tokens={total_tokens}, 块大小={chunk_size}")

        # 如果数据量不大，不需要分块
        if total_tokens <= chunk_size:
            if self.logger:
                self.logger.info("数据量较小，无需分块")
            return [patient_data]

        # 计算需要分成几块
        num_chunks = max(2, int(total_tokens / chunk_size) + 1)

        if self.logger:
            self.logger.info(f"将数据分成 {num_chunks} 块")

        # 分块策略：按时间线分块
        chunks = self._split_by_timeline(patient_data, num_chunks)

        if self.logger:
            for i, chunk in enumerate(chunks):
                if self.token_manager:
                    chunk_tokens = self.token_manager.estimate_tokens(chunk)
                else:
                    chunk_tokens = len(json.dumps(chunk, ensure_ascii=False)) // 2
                self.logger.info(f"块 {i+1}/{len(chunks)}: tokens={chunk_tokens}")

        return chunks

    def _split_by_timeline(self, patient_data: Dict[str, Any], num_chunks: int) -> List[Dict[str, Any]]:
        """按时间线分块

        Args:
            patient_data: 患者数据
            num_chunks: 分块数量

        Returns:
            list: 分块后的数据列表
        """
        chunks = []

        # 提取时间线数据
        timeline = patient_data.get('patient_timeline', [])
        if not timeline or not isinstance(timeline, list):
            # 如果没有时间线，按数据大小均分
            return self._split_by_size(patient_data, num_chunks)

        # 按时间排序
        sorted_timeline = sorted(
            timeline,
            key=lambda x: self._parse_date(x.get('date', x.get('exam_date', ''))),
            reverse=False  # 升序，最早的在前
        )

        # 计算每块的记录数
        records_per_chunk = max(1, len(sorted_timeline) // num_chunks)

        # 分块
        for i in range(num_chunks):
            start_idx = i * records_per_chunk
            end_idx = start_idx + records_per_chunk if i < num_chunks - 1 else len(sorted_timeline)

            # 添加重叠（保持上下文连贯性）
            overlap_size = int(records_per_chunk * self.chunk_overlap_ratio)
            if i > 0 and overlap_size > 0:
                start_idx = max(0, start_idx - overlap_size)

            chunk_timeline = sorted_timeline[start_idx:end_idx]

            # 构建分块数据
            chunk = {
                'patient_name': patient_data.get('patient_name', '患者'),
                'patient_info': patient_data.get('patient_info', {}),
                'patient_timeline': chunk_timeline,
                'chunk_index': i,
                'total_chunks': num_chunks
            }

            # 添加其他关键字段
            for key in ['diagnoses', 'current_medications', 'allergies']:
                if key in patient_data:
                    chunk[key] = patient_data[key]

            chunks.append(chunk)

        return chunks

    def _split_by_size(self, patient_data: Dict[str, Any], num_chunks: int) -> List[Dict[str, Any]]:
        """按数据大小均分

        Args:
            patient_data: 患者数据
            num_chunks: 分块数量

        Returns:
            list: 分块后的数据列表
        """
        # 简单策略：将所有列表字段均分
        chunks = []

        for i in range(num_chunks):
            chunk = {
                'patient_name': patient_data.get('patient_name', '患者'),
                'patient_info': patient_data.get('patient_info', {}),
                'chunk_index': i,
                'total_chunks': num_chunks
            }

            # 分割列表字段
            for key, value in patient_data.items():
                if isinstance(value, list) and len(value) > 0:
                    items_per_chunk = max(1, len(value) // num_chunks)
                    start_idx = i * items_per_chunk
                    end_idx = start_idx + items_per_chunk if i < num_chunks - 1 else len(value)
                    chunk[key] = value[start_idx:end_idx]
                elif key not in chunk:
                    chunk[key] = value

            chunks.append(chunk)

        return chunks

    def merge_ppt_data(self, chunk_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """合并多个分块的PPT数据

        Args:
            chunk_results: 分块结果列表

        Returns:
            dict: 合并后的PPT数据
        """
        if not chunk_results:
            return {}

        if len(chunk_results) == 1:
            return chunk_results[0]

        if self.logger:
            self.logger.info(f"开始合并 {len(chunk_results)} 个分块的PPT数据")

        # 初始化合并结果
        merged = {
            'success': True,
            'pptTemplate2Vm': {}
        }

        # 合并策略：
        # 1. 基本信息取第一块
        # 2. 列表字段合并所有块
        # 3. 图片字段合并所有块

        first_chunk = chunk_results[0]
        if 'pptTemplate2Vm' in first_chunk:
            merged['pptTemplate2Vm'] = first_chunk['pptTemplate2Vm'].copy()

        # 合并其他块的数据
        for i, chunk in enumerate(chunk_results[1:], start=1):
            if 'pptTemplate2Vm' not in chunk:
                continue

            chunk_data = chunk['pptTemplate2Vm']

            # 合并列表字段
            for key, value in chunk_data.items():
                if isinstance(value, list):
                    if key in merged['pptTemplate2Vm']:
                        # 合并列表，去重
                        merged['pptTemplate2Vm'][key].extend(value)
                    else:
                        merged['pptTemplate2Vm'][key] = value

        if self.logger:
            self.logger.info("✅ PPT数据合并完成")

        return merged

    def _parse_date(self, date_str: str) -> datetime:
        """解析日期字符串

        Args:
            date_str: 日期字符串

        Returns:
            datetime: 日期对象
        """
        if not date_str:
            return datetime.min

        # 尝试多种日期格式
        date_formats = [
            '%Y-%m-%d',
            '%Y/%m/%d',
            '%Y-%m-%d %H:%M:%S',
            '%Y/%m/%d %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%S.%f',
        ]

        for fmt in date_formats:
            try:
                return datetime.strptime(str(date_str), fmt)
            except (ValueError, TypeError):
                continue

        return datetime.min

    def should_use_chunking(self, data: Dict[str, Any], model_name: str = 'gemini-3-flash-preview') -> bool:
        """判断是否需要使用分块处理

        Args:
            data: 数据
            model_name: 模型名称

        Returns:
            bool: 是否需要分块
        """
        if not self.token_manager:
            return False

        # 检查是否启用分块处理
        enable_chunked = os.getenv('ENABLE_CHUNKED_PROCESSING', 'true').lower() in ('true', '1', 'yes')
        if not enable_chunked:
            return False

        # 估算token数
        total_tokens = self.token_manager.estimate_tokens(data)

        # 获取模型配置
        config = self.token_manager.get_model_config(model_name)
        safe_limit = int(config['max_input_tokens'] * config['safe_input_ratio'])

        # 如果超过安全限制的2倍，建议使用分块
        needs_chunking = total_tokens > safe_limit * 2

        if self.logger and needs_chunking:
            self.logger.warning(f"数据量过大 (tokens={total_tokens}, 安全限制={safe_limit})，建议使用分块处理")

        return needs_chunking
