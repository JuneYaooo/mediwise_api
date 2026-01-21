"""
LLM重试处理器 - 处理token超限错误和自动重试

功能：
1. 带自动压缩的LLM调用
2. 处理token超限错误
3. 自动重试机制
4. 处理输出截断问题
"""

import os
import json
import time
from typing import Dict, Any, Callable, Optional

# 尝试导入dotenv，如果不存在则跳过
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class TokenLimitError(Exception):
    """Token限制错误"""
    pass


class LLMRetryHandler:
    """LLM调用重试处理器 - 处理token超限错误"""

    def __init__(self, logger=None, token_manager=None, data_compressor=None):
        """初始化重试处理器

        Args:
            logger: 日志记录器（可选）
            token_manager: Token管理器（可选）
            data_compressor: 数据压缩器（可选）
        """
        self.logger = logger
        self.token_manager = token_manager
        self.data_compressor = data_compressor

    def call_with_auto_compression(self, llm, prompt: str, data: Dict[str, Any],
                                   model_name: str = 'gemini-3-flash-preview',
                                   max_retries: int = 3) -> Any:
        """带自动压缩的LLM调用

        流程：
        1. 首次尝试完整数据
        2. 如果token超限，自动压缩30%后重试
        3. 如果仍超限，压缩50%后重试
        4. 如果仍超限，抛出异常

        Args:
            llm: LLM对象
            prompt: 提示词
            data: 数据
            model_name: 模型名称
            max_retries: 最大重试次数

        Returns:
            LLM响应

        Raises:
            TokenLimitError: Token超限错误
        """
        compression_ratios = [1.0, 0.7, 0.5, 0.3]  # 压缩比例序列

        last_error = None

        for retry_count in range(max_retries):
            try:
                # 获取当前压缩比例
                compression_ratio = compression_ratios[min(retry_count, len(compression_ratios) - 1)]

                # 如果需要压缩
                if compression_ratio < 1.0 and self.token_manager and self.data_compressor:
                    if self.logger:
                        self.logger.info(f"🔄 重试 {retry_count + 1}/{max_retries}: 使用压缩比例 {compression_ratio:.1%}")

                    # 计算目标token数
                    config = self.token_manager.get_model_config(model_name)
                    target_tokens = int(config['max_input_tokens'] * config['safe_input_ratio'] * compression_ratio)

                    # 压缩数据
                    compressed_data = self.data_compressor.compress_data(data, target_tokens)

                    # 重新构建prompt（使用压缩后的数据）
                    # 注意：这里假设prompt中包含data的JSON表示
                    # 实际使用时可能需要根据具体情况调整
                    current_data = compressed_data
                else:
                    current_data = data

                # 检查token限制
                if self.token_manager:
                    # 估算prompt + data的总token数
                    total_input = prompt + json.dumps(current_data, ensure_ascii=False)
                    check_result = self.token_manager.check_input_limit(total_input, model_name)

                    if not check_result['within_limit']:
                        if self.logger:
                            self.logger.error(f"❌ Token超限: {check_result['total_tokens']} > {check_result['limit']}")
                        raise TokenLimitError(f"输入超过模型限制: {check_result['total_tokens']} tokens")

                # 调用LLM
                if self.logger:
                    self.logger.info(f"📤 调用LLM (尝试 {retry_count + 1}/{max_retries})...")

                response = self._call_llm(llm, prompt)

                if self.logger:
                    self.logger.info(f"✅ LLM调用成功")

                return response

            except TokenLimitError as e:
                last_error = e
                if self.logger:
                    self.logger.warning(f"⚠️ Token超限，准备重试: {e}")

                # 如果已经是最后一次重试，抛出异常
                if retry_count >= max_retries - 1:
                    raise

                # 等待一小段时间后重试
                time.sleep(1)

            except Exception as e:
                # 检查是否是token相关错误
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in ['token', 'length', 'limit', 'too long', 'context']):
                    last_error = TokenLimitError(f"LLM调用失败（可能是token超限）: {e}")
                    if self.logger:
                        self.logger.warning(f"⚠️ 检测到token相关错误，准备重试: {e}")

                    # 如果已经是最后一次重试，抛出异常
                    if retry_count >= max_retries - 1:
                        raise last_error

                    # 等待一小段时间后重试
                    time.sleep(1)
                else:
                    # 非token相关错误，直接抛出
                    raise

        # 如果所有重试都失败，抛出最后一个错误
        if last_error:
            raise last_error
        else:
            raise Exception("LLM调用失败，原因未知")

    def _call_llm(self, llm, prompt: str) -> Any:
        """调用LLM

        Args:
            llm: LLM对象
            prompt: 提示词

        Returns:
            LLM响应
        """
        # 尝试不同的调用方式
        try:
            # CrewAI LLM 对象直接调用
            response = llm.call(prompt)
            return str(response)
        except AttributeError:
            # 如果是 LangChain LLM，使用 invoke
            try:
                response = llm.invoke(prompt)
                return response.content if hasattr(response, 'content') else str(response)
            except Exception as e:
                if self.logger:
                    self.logger.error(f"LLM调用失败: {e}")
                raise

    def is_output_complete(self, response: Any) -> bool:
        """检查输出是否完整

        Args:
            response: LLM响应

        Returns:
            bool: 是否完整
        """
        if not response:
            return False

        response_text = str(response)

        # 检查JSON是否完整
        try:
            # 尝试提取JSON
            from src.utils.json_utils import JsonUtils
            json_str = JsonUtils.extract_json_from_text(response_text)
            if json_str:
                parsed = json.loads(json_str)
                # 检查是否有pptTemplate2Vm字段
                if 'pptTemplate2Vm' in parsed or 'template_json' in parsed:
                    return True
        except Exception:
            pass

        # 检查是否有截断标记
        truncation_markers = [
            '...',
            '[truncated]',
            '[省略]',
            '（省略）',
            'output truncated',
            'response truncated'
        ]

        for marker in truncation_markers:
            if marker in response_text.lower():
                if self.logger:
                    self.logger.warning(f"⚠️ 检测到输出截断标记: {marker}")
                return False

        return True

    def complete_truncated_output(self, partial_response: Any, llm, context: Dict[str, Any]) -> Any:
        """补全被截断的输出

        Args:
            partial_response: 部分响应
            llm: LLM对象
            context: 上下文信息

        Returns:
            完整响应
        """
        if self.logger:
            self.logger.info("🔧 尝试补全被截断的输出...")

        # 构建补全提示词
        prompt = f"""之前的输出被截断了，请继续完成剩余部分。

已有的部分输出：
{str(partial_response)[-1000:]}  # 只取最后1000字符

请继续输出剩余的JSON数据，确保输出完整的JSON结构。
只输出JSON，不要包含任何解释文字。"""

        try:
            # 调用LLM补全
            completion = self._call_llm(llm, prompt)

            # 尝试合并
            merged = self._merge_responses(partial_response, completion)

            if self.logger:
                self.logger.info("✅ 输出补全成功")

            return merged

        except Exception as e:
            if self.logger:
                self.logger.error(f"❌ 输出补全失败: {e}")
            # 返回原始部分响应
            return partial_response

    def _merge_responses(self, partial: Any, completion: Any) -> Any:
        """合并部分响应和补全响应

        Args:
            partial: 部分响应
            completion: 补全响应

        Returns:
            合并后的响应
        """
        # 简单策略：拼接字符串
        partial_str = str(partial)
        completion_str = str(completion)

        # 如果partial以不完整的JSON结束，尝试智能合并
        if partial_str.rstrip().endswith(',') or partial_str.rstrip().endswith('{') or partial_str.rstrip().endswith('['):
            merged = partial_str + completion_str
        else:
            merged = partial_str + '\n' + completion_str

        return merged
