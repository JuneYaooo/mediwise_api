"""
Token管理器 - 负责token计数、限制检查、数据压缩判断

功能：
1. 估算文本的token数量
2. 检查输入数据是否超过模型限制
3. 提供压缩建议
"""

import os
import json
from typing import Dict, Any, Union

# 尝试导入dotenv，如果不存在则跳过
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv不是必需的，可以直接使用环境变量


class TokenManager:
    """Token管理器 - 负责token计数、限制检查、数据压缩"""

    # 模型配置（从环境变量读取，带默认值）
    MODEL_CONFIGS = {
        'gemini-3-flash-preview': {
            'max_input_tokens': int(os.getenv('MODEL_MAX_INPUT_TOKENS', '1000000')),
            'max_output_tokens': int(os.getenv('MODEL_MAX_OUTPUT_TOKENS', '65535')),
            'safe_input_ratio': float(os.getenv('TOKEN_SAFE_INPUT_RATIO', '0.7')),
            'safe_output_ratio': float(os.getenv('TOKEN_SAFE_OUTPUT_RATIO', '0.9'))
        },
        'deepseek-chat': {
            'max_input_tokens': 64000,  # DeepSeek 支持64K上下文
            'max_output_tokens': 8192,   # 输出限制8K
            'safe_input_ratio': 0.7,
            'safe_output_ratio': 0.9
        },
        'qwen2.5-72b-instruct': {
            'max_input_tokens': 128000,  # Qwen2.5-72B 支持128K上下文
            'max_output_tokens': 8192,   # 输出限制8K
            'safe_input_ratio': 0.7,
            'safe_output_ratio': 0.9
        },
        'gpt-4': {
            'max_input_tokens': 128000,
            'max_output_tokens': 4096,
            'safe_input_ratio': 0.7,
            'safe_output_ratio': 0.9
        },
        'gpt-4-turbo': {
            'max_input_tokens': 128000,
            'max_output_tokens': 4096,
            'safe_input_ratio': 0.7,
            'safe_output_ratio': 0.9
        },
        'claude-3-opus': {
            'max_input_tokens': 200000,
            'max_output_tokens': 4096,
            'safe_input_ratio': 0.7,
            'safe_output_ratio': 0.9
        },
        'claude-3-sonnet': {
            'max_input_tokens': 200000,
            'max_output_tokens': 4096,
            'safe_input_ratio': 0.7,
            'safe_output_ratio': 0.9
        }
    }

    def __init__(self, logger=None):
        """初始化Token管理器

        Args:
            logger: 日志记录器（可选）
        """
        self.logger = logger

    def estimate_tokens(self, text: Union[str, dict, list]) -> int:
        """估算文本token数

        估算规则：
        - 中文：约1.5字符/token
        - 英文：约4字符/token
        - 混合文本：使用2字符/token作为平均值

        Args:
            text: 文本内容（字符串、字典或列表）

        Returns:
            int: 估算的token数量
        """
        # 如果是字典或列表，先转换为JSON字符串
        if isinstance(text, (dict, list)):
            text = json.dumps(text, ensure_ascii=False)
        elif not isinstance(text, str):
            text = str(text)

        # 统计中文字符数
        chinese_chars = sum(1 for char in text if '\u4e00' <= char <= '\u9fff')
        # 统计总字符数
        total_chars = len(text)
        # 英文字符数
        english_chars = total_chars - chinese_chars

        # 估算token数
        # 中文：1.5字符/token，英文：4字符/token
        estimated_tokens = int(chinese_chars / 1.5 + english_chars / 4)

        return estimated_tokens

    def get_model_config(self, model_name: str) -> Dict[str, Any]:
        """获取模型配置

        Args:
            model_name: 模型名称

        Returns:
            dict: 模型配置信息
        """
        # 如果模型不在配置中，使用gemini-3-flash-preview的配置作为默认值
        if model_name not in self.MODEL_CONFIGS:
            if self.logger:
                self.logger.warning(f"模型 {model_name} 未在配置中，使用默认配置")
            return self.MODEL_CONFIGS['gemini-3-flash-preview']

        return self.MODEL_CONFIGS[model_name]

    def check_input_limit(self, data: Union[str, dict, list], model_name: str) -> Dict[str, Any]:
        """检查输入数据是否超过限制

        Args:
            data: 输入数据（字符串、字典或列表）
            model_name: 模型名称

        Returns:
            dict: 检查结果
                - within_limit: bool, 是否在限制内
                - total_tokens: int, 总token数
                - limit: int, 限制token数
                - safe_limit: int, 安全限制token数
                - compression_needed: bool, 是否需要压缩
                - compression_ratio: float, 建议压缩比例
        """
        # 获取模型配置
        config = self.get_model_config(model_name)

        # 估算token数
        total_tokens = self.estimate_tokens(data)

        # 计算限制
        max_input_tokens = config['max_input_tokens']
        safe_input_ratio = config['safe_input_ratio']
        safe_limit = int(max_input_tokens * safe_input_ratio)

        # 判断是否需要压缩
        within_limit = total_tokens <= max_input_tokens
        compression_needed = total_tokens > safe_limit

        # 计算建议压缩比例
        compression_ratio = 1.0
        if compression_needed:
            compression_ratio = safe_limit / total_tokens

        result = {
            'within_limit': within_limit,
            'total_tokens': total_tokens,
            'limit': max_input_tokens,
            'safe_limit': safe_limit,
            'compression_needed': compression_needed,
            'compression_ratio': compression_ratio,
            'usage_ratio': total_tokens / max_input_tokens
        }

        if self.logger:
            if compression_needed:
                self.logger.warning(
                    f"📊 Token检查: 当前={total_tokens}, 安全限制={safe_limit}, "
                    f"最大限制={max_input_tokens}, 使用率={result['usage_ratio']:.1%}, "
                    f"建议压缩比例={compression_ratio:.1%}"
                )
            else:
                self.logger.info(
                    f"📊 Token检查: 当前={total_tokens}, 安全限制={safe_limit}, "
                    f"使用率={result['usage_ratio']:.1%} ✅"
                )

        return result

    def check_output_limit(self, expected_output_size: int, model_name: str) -> Dict[str, Any]:
        """检查预期输出是否超过限制

        Args:
            expected_output_size: 预期输出token数
            model_name: 模型名称

        Returns:
            dict: 检查结果
        """
        config = self.get_model_config(model_name)
        max_output_tokens = config['max_output_tokens']
        safe_output_ratio = config['safe_output_ratio']
        safe_limit = int(max_output_tokens * safe_output_ratio)

        within_limit = expected_output_size <= max_output_tokens
        needs_chunking = expected_output_size > safe_limit

        result = {
            'within_limit': within_limit,
            'expected_tokens': expected_output_size,
            'limit': max_output_tokens,
            'safe_limit': safe_limit,
            'needs_chunking': needs_chunking,
            'usage_ratio': expected_output_size / max_output_tokens
        }

        if self.logger:
            if needs_chunking:
                self.logger.warning(
                    f"📤 输出Token检查: 预期={expected_output_size}, 安全限制={safe_limit}, "
                    f"最大限制={max_output_tokens}, 使用率={result['usage_ratio']:.1%}, "
                    f"建议分块输出"
                )
            else:
                self.logger.info(
                    f"📤 输出Token检查: 预期={expected_output_size}, 安全限制={safe_limit}, "
                    f"使用率={result['usage_ratio']:.1%} ✅"
                )

        return result

    def calculate_compression_target(self, current_tokens: int, model_name: str,
                                    target_ratio: float = None) -> int:
        """计算压缩目标token数

        Args:
            current_tokens: 当前token数
            model_name: 模型名称
            target_ratio: 目标比例（可选，默认使用safe_input_ratio）

        Returns:
            int: 目标token数
        """
        config = self.get_model_config(model_name)

        if target_ratio is None:
            target_ratio = config['safe_input_ratio']

        max_input_tokens = config['max_input_tokens']
        target_tokens = int(max_input_tokens * target_ratio)

        if self.logger:
            compression_ratio = target_tokens / current_tokens if current_tokens > 0 else 1.0
            self.logger.info(
                f"🎯 压缩目标: 当前={current_tokens}, 目标={target_tokens}, "
                f"压缩比例={compression_ratio:.1%}"
            )

        return target_tokens
