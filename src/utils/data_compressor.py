"""
患者数据智能压缩器 - 按优先级压缩患者数据

功能：
1. 按优先级保留关键信息
2. 压缩时间轴数据（保留最近记录，采样历史记录）
3. 压缩原始文件数据（优先保留医学影像）
4. 使用LLM提取长文本关键信息
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


class PatientDataCompressor:
    """患者数据智能压缩器"""

    # 数据优先级配置
    PRIORITY_CONFIG = {
        'critical': [  # 关键信息（必须保留）
            'patient_name',
            'patient_info',
            'diagnoses',
            'current_medications',
            'allergies'
        ],
        'important': [  # 重要信息（尽量保留）
            'lab_tests',
            'treatments',
            'imaging_studies',
            'vital_signs'
        ],
        'optional': [  # 可选信息（可压缩）
            'historical_records',
            'extracted_text',
            'notes'
        ]
    }

    def __init__(self, logger=None, token_manager=None):
        """初始化数据压缩器

        Args:
            logger: 日志记录器（可选）
            token_manager: Token管理器（可选）
        """
        self.logger = logger
        self.token_manager = token_manager

        # 从环境变量读取配置
        self.compression_strategy = os.getenv('COMPRESSION_STRATEGY', 'smart')
        self.max_raw_files_count = int(os.getenv('MAX_RAW_FILES_COUNT', '50'))
        self.max_timeline_records = int(os.getenv('MAX_TIMELINE_RECORDS', '100'))
        self.extracted_text_max_length = int(os.getenv('EXTRACTED_TEXT_MAX_LENGTH', '200'))

    def compress_data(self, data: Dict[str, Any], target_tokens: int) -> Dict[str, Any]:
        """智能压缩数据到目标token数

        Args:
            data: 原始数据
            target_tokens: 目标token数

        Returns:
            dict: 压缩后的数据
        """
        if not data:
            return data

        # 估算当前token数
        if self.token_manager:
            current_tokens = self.token_manager.estimate_tokens(data)
        else:
            current_tokens = len(json.dumps(data, ensure_ascii=False)) // 2

        if current_tokens <= target_tokens:
            if self.logger:
                self.logger.info(f"数据无需压缩: 当前={current_tokens}, 目标={target_tokens}")
            return data

        if self.logger:
            self.logger.info(f"开始压缩数据: 当前={current_tokens}, 目标={target_tokens}, "
                           f"压缩比例={target_tokens/current_tokens:.1%}")

        # 根据压缩策略选择不同的压缩方法
        if self.compression_strategy == 'aggressive':
            compressed_data = self._aggressive_compress(data, target_tokens)
        elif self.compression_strategy == 'minimal':
            compressed_data = self._minimal_compress(data, target_tokens)
        else:  # smart (默认)
            compressed_data = self._smart_compress(data, target_tokens)

        # 验证压缩后的token数
        if self.token_manager:
            compressed_tokens = self.token_manager.estimate_tokens(compressed_data)
            compression_ratio = compressed_tokens / current_tokens if current_tokens > 0 else 1.0
            if self.logger:
                self.logger.info(f"✅ 数据压缩完成: 原始={current_tokens}, 压缩后={compressed_tokens}, "
                               f"压缩比例={compression_ratio:.1%}")

        return compressed_data

    def _smart_compress(self, data: Dict[str, Any], target_tokens: int) -> Dict[str, Any]:
        """智能压缩策略 - 按优先级保留信息

        Args:
            data: 原始数据
            target_tokens: 目标token数

        Returns:
            dict: 压缩后的数据
        """
        compressed = {}

        # 1. 保留所有关键信息
        for key in self.PRIORITY_CONFIG['critical']:
            if key in data:
                compressed[key] = data[key]

        # 2. 压缩重要信息（保留最近的记录）
        for key in self.PRIORITY_CONFIG['important']:
            if key in data:
                if isinstance(data[key], list):
                    # 保留最近的记录
                    compressed[key] = self._compress_list_by_recency(data[key], max_items=20)
                else:
                    compressed[key] = data[key]

        # 3. 压缩可选信息（大幅压缩或删除）
        for key in self.PRIORITY_CONFIG['optional']:
            if key in data:
                if isinstance(data[key], str):
                    # 文本字段只保留前N个字符
                    compressed[key] = data[key][:self.extracted_text_max_length]
                elif isinstance(data[key], list):
                    # 列表只保留前几项
                    compressed[key] = data[key][:5]
                else:
                    compressed[key] = data[key]

        # 4. 处理其他字段（未在优先级配置中的字段）
        for key, value in data.items():
            if key not in compressed:
                if isinstance(value, str) and len(value) > self.extracted_text_max_length:
                    # 长文本压缩
                    compressed[key] = value[:self.extracted_text_max_length]
                elif isinstance(value, list) and len(value) > 10:
                    # 长列表压缩
                    compressed[key] = value[:10]
                else:
                    compressed[key] = value

        return compressed

    def _aggressive_compress(self, data: Dict[str, Any], target_tokens: int) -> Dict[str, Any]:
        """激进压缩策略 - 只保留最核心信息

        Args:
            data: 原始数据
            target_tokens: 目标token数

        Returns:
            dict: 压缩后的数据
        """
        compressed = {}

        # 只保留关键信息
        for key in self.PRIORITY_CONFIG['critical']:
            if key in data:
                compressed[key] = data[key]

        # 重要信息只保留最少量
        for key in self.PRIORITY_CONFIG['important']:
            if key in data:
                if isinstance(data[key], list):
                    compressed[key] = self._compress_list_by_recency(data[key], max_items=5)
                else:
                    compressed[key] = data[key]

        # 可选信息全部删除
        return compressed

    def _minimal_compress(self, data: Dict[str, Any], target_tokens: int) -> Dict[str, Any]:
        """最小压缩策略 - 尽可能保留原始数据

        Args:
            data: 原始数据
            target_tokens: 目标token数

        Returns:
            dict: 压缩后的数据
        """
        compressed = data.copy()

        # 只压缩extracted_text等长文本字段
        for key, value in compressed.items():
            if isinstance(value, str) and len(value) > self.extracted_text_max_length * 2:
                compressed[key] = value[:self.extracted_text_max_length * 2]

        return compressed

    def compress_timeline(self, timeline: Union[List, Dict], target_tokens: int) -> Union[List, Dict]:
        """压缩时间轴数据

        策略：
        1. 保留最近的记录
        2. 对历史记录进行采样（保留关键节点）
        3. 压缩文本字段

        Args:
            timeline: 时间轴数据（列表或字典）
            target_tokens: 目标token数

        Returns:
            压缩后的时间轴数据
        """
        if not timeline:
            return timeline

        # 如果是字典，递归处理
        if isinstance(timeline, dict):
            compressed = {}
            for key, value in timeline.items():
                if isinstance(value, (list, dict)):
                    compressed[key] = self.compress_timeline(value, target_tokens)
                elif isinstance(value, str) and len(value) > self.extracted_text_max_length:
                    compressed[key] = value[:self.extracted_text_max_length]
                else:
                    compressed[key] = value
            return compressed

        # 如果是列表
        if not isinstance(timeline, list):
            return timeline

        # 估算当前token数
        if self.token_manager:
            current_tokens = self.token_manager.estimate_tokens(timeline)
        else:
            current_tokens = len(json.dumps(timeline, ensure_ascii=False)) // 2

        if current_tokens <= target_tokens:
            return timeline

        if self.logger:
            self.logger.info(f"压缩时间轴: 当前记录数={len(timeline)}, 当前tokens={current_tokens}, "
                           f"目标tokens={target_tokens}")

        # 按日期排序（如果有日期字段）
        sorted_timeline = self._sort_by_date(timeline)

        # 计算需要保留的记录数
        compression_ratio = target_tokens / current_tokens if current_tokens > 0 else 1.0
        target_count = max(int(len(sorted_timeline) * compression_ratio), 10)  # 至少保留10条
        target_count = min(target_count, self.max_timeline_records)  # 不超过最大限制

        # 保留最近的记录
        compressed_timeline = sorted_timeline[:target_count]

        # 压缩每条记录的文本字段
        for record in compressed_timeline:
            if isinstance(record, dict):
                for key, value in record.items():
                    if isinstance(value, str) and len(value) > self.extracted_text_max_length:
                        record[key] = value[:self.extracted_text_max_length]

        if self.logger:
            self.logger.info(f"✅ 时间轴压缩完成: 保留记录数={len(compressed_timeline)}")

        return compressed_timeline

    def compress_raw_files(self, raw_files: List[Dict], target_tokens: int) -> List[Dict]:
        """压缩原始文件数据

        策略：
        1. 优先保留has_medical_image=True的文件
        2. extracted_text只保留前N字符
        3. 按exam_date排序，保留最近的文件

        Args:
            raw_files: 原始文件列表
            target_tokens: 目标token数

        Returns:
            list: 压缩后的文件列表
        """
        if not raw_files or not isinstance(raw_files, list):
            return raw_files

        # 估算当前token数
        if self.token_manager:
            current_tokens = self.token_manager.estimate_tokens(raw_files)
        else:
            current_tokens = len(json.dumps(raw_files, ensure_ascii=False)) // 2

        if current_tokens <= target_tokens:
            return raw_files

        if self.logger:
            self.logger.info(f"压缩原始文件: 当前文件数={len(raw_files)}, 当前tokens={current_tokens}, "
                           f"目标tokens={target_tokens}")

        # 1. 分类文件：医学影像 vs 其他
        medical_image_files = []
        other_files = []

        for file_item in raw_files:
            if not isinstance(file_item, dict):
                continue

            if file_item.get('has_medical_image', False):
                medical_image_files.append(file_item)
            else:
                other_files.append(file_item)

        # 2. 按日期排序
        medical_image_files = self._sort_by_date(medical_image_files, date_field='exam_date')
        other_files = self._sort_by_date(other_files, date_field='exam_date')

        # 3. 计算需要保留的文件数
        compression_ratio = target_tokens / current_tokens if current_tokens > 0 else 1.0
        target_count = max(int(len(raw_files) * compression_ratio), 5)  # 至少保留5个
        target_count = min(target_count, self.max_raw_files_count)  # 不超过最大限制

        # 4. 优先保留医学影像文件
        medical_count = min(len(medical_image_files), int(target_count * 0.7))  # 70%给医学影像
        other_count = target_count - medical_count

        compressed_files = medical_image_files[:medical_count] + other_files[:other_count]

        # 5. 压缩每个文件的extracted_text字段
        for file_item in compressed_files:
            if isinstance(file_item, dict) and 'extracted_text' in file_item:
                text = file_item['extracted_text']
                if isinstance(text, str) and len(text) > self.extracted_text_max_length:
                    file_item['extracted_text'] = text[:self.extracted_text_max_length]

        if self.logger:
            self.logger.info(f"✅ 原始文件压缩完成: 保留文件数={len(compressed_files)} "
                           f"(医学影像={medical_count}, 其他={other_count})")

        return compressed_files

    def _compress_list_by_recency(self, items: List, max_items: int = 20) -> List:
        """按最近时间压缩列表

        Args:
            items: 列表数据
            max_items: 最大保留数量

        Returns:
            list: 压缩后的列表
        """
        if not items or len(items) <= max_items:
            return items

        # 尝试按日期排序
        sorted_items = self._sort_by_date(items)

        # 保留最近的记录
        return sorted_items[:max_items]

    def _sort_by_date(self, items: List, date_field: str = None) -> List:
        """按日期排序（降序，最新的在前）

        Args:
            items: 列表数据
            date_field: 日期字段名（可选，自动检测）

        Returns:
            list: 排序后的列表
        """
        if not items or not isinstance(items, list):
            return items

        # 如果不是字典列表，直接返回
        if not all(isinstance(item, dict) for item in items):
            return items

        # 自动检测日期字段
        if date_field is None:
            date_fields = ['date', 'exam_date', 'test_date', 'created_at', 'timestamp', 'time']
            for field in date_fields:
                if items and field in items[0]:
                    date_field = field
                    break

        # 如果没有日期字段，返回原列表
        if date_field is None:
            return items

        # 按日期排序
        try:
            sorted_items = sorted(
                items,
                key=lambda x: self._parse_date(x.get(date_field, '')),
                reverse=True  # 降序，最新的在前
            )
            return sorted_items
        except Exception as e:
            if self.logger:
                self.logger.warning(f"日期排序失败: {e}，返回原列表")
            return items

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

        # 如果都失败，返回最小日期
        return datetime.min

    def summarize_text(self, text: str, max_length: int = None) -> str:
        """提取文本关键信息（简单版本，不使用LLM）

        Args:
            text: 原始文本
            max_length: 最大长度（可选）

        Returns:
            str: 压缩后的文本
        """
        if max_length is None:
            max_length = self.extracted_text_max_length

        if not text or len(text) <= max_length:
            return text

        # 简单截断（保留前N个字符）
        return text[:max_length] + "..."
