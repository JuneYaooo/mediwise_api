# src/utils/json_utils.py
import json
import re
from typing import Any, Dict, Optional, Union

class JsonUtils:
    @staticmethod
    def parse_json(json_str: str, fix_format: bool = True) -> Dict:
        """
        解析JSON字符串，可选择尝试修复常见格式问题
        
        Args:
            json_str: JSON字符串
            fix_format: 是否尝试修复格式问题
            
        Returns:
            解析后的JSON对象
            
        Raises:
            ValueError: 如果JSON无法解析
        """
        # 检查输入是否为空或仅包含空白字符
        if not json_str or not json_str.strip():
            raise ValueError("输入的JSON字符串为空")
            
        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            if not fix_format:
                raise ValueError(f"JSON解析错误: {str(e)}") from e
                
            # 尝试修复并重新解析
            fixed_json = JsonUtils.fix_json_format(json_str)
            if fixed_json:
                return JsonUtils.parse_json(fixed_json, fix_format=False)
            else:
                raise ValueError(f"无法修复JSON格式: {str(e)}") from e
    
    @staticmethod
    def fix_json_format(json_str: str) -> Optional[str]:
        """
        尝试修复常见的JSON格式问题

        Args:
            json_str: 可能格式不正确的JSON字符串

        Returns:
            修复后的JSON字符串，如果无法修复则返回None
        """
        # 0. 替换中文标点符号为英文标点符号
        # 这是常见问题，特别是当LLM在中文上下文中生成JSON时
        chinese_punctuation_map = {
            '，': ',',   # 中文逗号 -> 英文逗号
            '：': ':',   # 中文冒号 -> 英文冒号
            '；': ';',   # 中文分号 -> 英文分号
            '（': '(',   # 中文左括号 -> 英文左括号
            '）': ')',   # 中文右括号 -> 英文右括号
            '【': '[',   # 中文左方括号 -> 英文左方括号
            '】': ']',   # 中文右方括号 -> 英文右方括号
            '｛': '{',   # 全角左大括号 -> 英文左大括号
            '｝': '}',   # 全角右大括号 -> 英文右大括号
        }

        for cn_punct, en_punct in chinese_punctuation_map.items():
            json_str = json_str.replace(cn_punct, en_punct)

        # 尝试解析修复后的JSON
        try:
            json.loads(json_str)
            return json_str
        except:
            pass  # 继续尝试其他修复方法

        # 1. 去除JSON开头可能存在的非JSON文本
        try:
            # 找到第一个 { 或 [ 的位置作为JSON开始
            start_brace = json_str.find('{')
            start_bracket = json_str.find('[')
            
            # 如果两者都存在，使用最靠前的那个
            if start_brace >= 0 and start_bracket >= 0:
                start_pos = min(start_brace, start_bracket)
            # 如果只有一个存在
            elif start_brace >= 0:
                start_pos = start_brace
            elif start_bracket >= 0:
                start_pos = start_bracket
            else:
                start_pos = -1
                
            # 如果找到了起始位置且不在第一个字符
            if start_pos > 0:
                json_str = json_str[start_pos:]
                try:
                    json.loads(json_str)
                    return json_str
                except:
                    pass  # 继续尝试其他修复方法
        except:
            pass

        # 2. 修复属性名没有引号的问题
        try:
            # 使用正则表达式为没有引号的键添加双引号
            # 匹配没有双引号的键，后面跟着冒号
            fixed = re.sub(r'([{,])\s*([a-zA-Z0-9_]+)\s*:', r'\1"\2":', json_str)
            json.loads(fixed)  # 测试是否可解析
            return fixed
        except:
            pass

        # 3. 处理单引号而不是双引号的情况
        try:
            # 将单引号替换为双引号，但跳过嵌套的引号
            fixed = json_str.replace("'", '"')
            json.loads(fixed)
            return fixed
        except:
            pass

        # 4. 处理尾部逗号问题
        try:
            # 删除对象和数组末尾多余的逗号
            fixed = re.sub(r',\s*([}\]])', r'\1', json_str)
            json.loads(fixed)
            return fixed
        except:
            pass

        # 5. 处理JavaScript注释
        try:
            # 删除单行注释
            fixed = re.sub(r'//.*?(\n|$)', r'\1', json_str)
            # 删除多行注释
            fixed = re.sub(r'/\*.*?\*/', '', fixed, flags=re.DOTALL)
            json.loads(fixed)
            return fixed
        except:
            pass

        # 6. 处理可能被包裹在其他文本中的JSON
        try:
            # 尝试匹配最长的可能是JSON的部分
            match = re.search(r'({.*})', json_str, re.DOTALL)
            if match:
                candidate = match.group(1)
                json.loads(candidate)
                return candidate
        except:
            pass
            
        return None

    @staticmethod
    def safe_json_load(file_path: str, default_value: Any = None) -> Any:
        """
        安全地从文件加载JSON，处理可能出现的异常
        
        Args:
            file_path: JSON文件路径
            default_value: 如果加载失败返回的默认值
            
        Returns:
            解析后的JSON对象，或者默认值
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                return JsonUtils.parse_json(content)
        except (IOError, ValueError) as e:
            print(f"无法加载JSON文件 {file_path}: {str(e)}")
            return default_value

    @staticmethod
    def safe_json_dump(data: Any, file_path: str, indent: int = 2) -> bool:
        """
        安全地将数据保存为JSON文件
        
        Args:
            data: 要保存的数据
            file_path: 保存的文件路径
            indent: JSON缩进
            
        Returns:
            是否成功保存
        """
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=indent)
            return True
        except Exception as e:
            print(f"无法保存JSON到 {file_path}: {str(e)}")
            return False

    @staticmethod
    def extract_json_from_text(text: str) -> Optional[str]:
        """
        从文本中提取JSON字符串

        Args:
            text: 可能包含JSON的文本

        Returns:
            提取的JSON字符串，如果未找到则返回None
        """
        # 检查输入是否为空
        if not text or not isinstance(text, str):
            return None

        # 先尝试整个文本是否是有效的JSON
        try:
            json.loads(text)
            return text
        except:
            pass

        # 🆕 优先处理 markdown 代码块（LLM常见输出格式）
        # 匹配 ```json ... ``` 或 ``` ... ```
        json_code_blocks = re.findall(r'```(?:json)?\s*([\s\S]*?)```', text, re.DOTALL)
        for block in json_code_blocks:
            block = block.strip()
            if not block:
                continue
            try:
                json.loads(block)
                return block
            except:
                # 尝试修复并验证
                fixed = JsonUtils.fix_json_format(block)
                if fixed:
                    try:
                        json.loads(fixed)
                        return fixed
                    except:
                        pass

        # 尝试查找 { 和匹配的 } 之间的内容（处理嵌套）
        # 从最长的可能JSON开始尝试
        json_candidates = []

        # 找到所有的 { 位置
        open_positions = [pos for pos, char in enumerate(text) if char == '{']

        for start_pos in open_positions:
            # 从此位置开始找匹配的右括号
            depth = 0
            for i in range(start_pos, len(text)):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:  # 找到匹配的右括号
                        json_candidates.append(text[start_pos:i+1])
                        break

        # 类似地处理数组
        open_positions = [pos for pos, char in enumerate(text) if char == '[']

        for start_pos in open_positions:
            # 从此位置开始找匹配的右括号
            depth = 0
            for i in range(start_pos, len(text)):
                if text[i] == '[':
                    depth += 1
                elif text[i] == ']':
                    depth -= 1
                    if depth == 0:  # 找到匹配的右括号
                        json_candidates.append(text[start_pos:i+1])
                        break

        # 按长度从大到小排序候选项（更长的JSON更有可能是完整的）
        json_candidates.sort(key=len, reverse=True)

        # 尝试解析每个候选项
        for candidate in json_candidates:
            try:
                json.loads(candidate)
                return candidate
            except:
                # 尝试修复并验证
                fixed = JsonUtils.fix_json_format(candidate)
                if fixed:
                    try:
                        json.loads(fixed)
                        return fixed
                    except:
                        pass

        # 回退到旧方法：使用简单正则表达式
        try:
            # 尝试查找 { 和 } 之间的内容
            matches = re.findall(r'({.*?})', text, re.DOTALL)
            for match in matches:
                try:
                    json.loads(match)
                    return match
                except:
                    # 尝试修复并验证
                    fixed = JsonUtils.fix_json_format(match)
                    if fixed:
                        try:
                            json.loads(fixed)
                            return fixed
                        except:
                            pass
            
            # 尝试查找 [ 和 ] 之间的内容
            matches = re.findall(r'(\[.*?\])', text, re.DOTALL)
            for match in matches:
                try:
                    json.loads(match)
                    return match
                except:
                    # 尝试修复并验证
                    fixed = JsonUtils.fix_json_format(match)
                    if fixed:
                        return fixed
        except:
            pass
        
        return None

    @staticmethod
    def safe_parse_json(input_data: Union[str, Dict, Any], debug_prefix: str = "") -> Dict:
        """
        安全解析JSON，具有完整的错误处理。如果输入已经是字典，则直接返回。
        集成了所有常见的JSON解析错误处理步骤，避免在代码中重复try-except块。

        Args:
            input_data: 要解析的数据，可以是字符串或已经是字典的对象
            debug_prefix: 调试输出的前缀，用于区分不同的调用位置

        Returns:
            解析后的字典，如果解析失败则返回空字典 {}
            注意：如果解析结果是列表，也会原样返回列表（虽然类型注解是Dict）
        """
        # 如果已经是字典类型，直接返回
        if isinstance(input_data, dict):
            return input_data

        # 如果已经是列表类型，直接返回（调用方需要处理列表情况）
        if isinstance(input_data, list):
            print(f"\033[93m[{debug_prefix}警告] 输入已经是列表类型，直接返回\033[0m")
            return input_data

        # 检查空输入
        if input_data is None or (isinstance(input_data, str) and not input_data.strip()):
            print(f"\033[91m[{debug_prefix}JSON解析错误] 输入为空\033[0m")
            return {}

        # 如果不是字符串，尝试转换为字符串
        if not isinstance(input_data, str):
            try:
                input_data = str(input_data)
            except Exception as e:
                print(f"\033[91m[{debug_prefix}无法转换为字符串] {str(e)}\033[0m")
                return {}

        # 先尝试解码Unicode转义序列
        try:
            # 处理可能存在的Unicode转义序列，如 \u4e2d\u6587
            if '\\u' in input_data:
                input_data = input_data.encode().decode('unicode_escape')
        except Exception as e:
            print(f"\033[93m[{debug_prefix}Unicode解码警告] {str(e)}\033[0m")
            # 如果Unicode解码失败，继续使用原始数据
            pass

        # 尝试直接解析
        try:
            result = JsonUtils.parse_json(input_data)
            # 递归处理结果中可能存在的Unicode编码问题
            decoded_result = JsonUtils._decode_unicode_in_dict(result)
            # 如果解析结果是列表，打印警告（调用方需要处理）
            if isinstance(decoded_result, list):
                print(f"\033[93m[{debug_prefix}警告] JSON解析结果是列表类型，调用方需要处理\033[0m")
            return decoded_result
        except ValueError as e:
            print(f"\033[91m[{debug_prefix}JSON解析错误] {str(e)}\033[0m")

            # 尝试从文本中提取JSON
            json_str = JsonUtils.extract_json_from_text(input_data)
            if json_str:
                try:
                    result = JsonUtils.parse_json(json_str, fix_format=True)
                    decoded_result = JsonUtils._decode_unicode_in_dict(result)
                    # 如果解析结果是列表，打印警告
                    if isinstance(decoded_result, list):
                        print(f"\033[93m[{debug_prefix}警告] 从文本提取的JSON是列表类型，调用方需要处理\033[0m")
                    return decoded_result
                except Exception as e2:
                    print(f"\033[91m[{debug_prefix}JSON修复后依然出错] {str(e2)}\033[0m")
                    print(f"\033[93m[{debug_prefix}提取的JSON内容] {json_str[:300]}...\033[0m" if len(json_str) > 300 else f"\033[93m[{debug_prefix}提取的JSON内容] {json_str}\033[0m")
            else:
                print(f"\033[91m[{debug_prefix}无法从文本中提取JSON] {input_data[:200]}...\033[0m" if len(input_data) > 200 else f"\033[91m[{debug_prefix}无法从文本中提取JSON] {input_data}\033[0m")

        # 如果所有解析尝试都失败，返回空字典
        return {}

    @staticmethod
    def _decode_unicode_in_dict(obj):
        """
        递归解码字典中的Unicode转义序列
        
        Args:
            obj: 要处理的对象（字典、列表、字符串等）
            
        Returns:
            解码后的对象
        """
        if isinstance(obj, dict):
            return {key: JsonUtils._decode_unicode_in_dict(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [JsonUtils._decode_unicode_in_dict(item) for item in obj]
        elif isinstance(obj, str):
            try:
                # 处理Unicode转义序列
                if '\\u' in obj:
                    # 使用正则表达式匹配并替换Unicode转义序列
                    import re
                    def replace_unicode(match):
                        try:
                            return chr(int(match.group(1), 16))
                        except ValueError:
                            return match.group(0)  # 如果转换失败，返回原字符串
                    
                    # 匹配 \uXXXX 格式的Unicode转义序列
                    return re.sub(r'\\u([0-9a-fA-F]{4})', replace_unicode, obj)
                return obj
            except Exception:
                return obj
        else:
            return obj 