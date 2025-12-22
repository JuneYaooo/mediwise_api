import importlib.util
import sys
from typing import Any
import tempfile
import os

class ToolLoader:
    @staticmethod
    def load_tool_from_code(tool_code: str, tool_name: str) -> Any:
        """
        从代码字符串动态加载工具类

        Args:
            tool_code: 完整的工具代码字符串
            tool_name: 工具类的名称

        Returns:
            工具类
        """
        # 修复错误的导入语句：将 crewai_tools 替换为 crewai.tools
        tool_code = tool_code.replace('from crewai_tools import', 'from crewai.tools import')

        # 创建临时文件来存储代码
        with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as tmp_file:
            tmp_file.write(tool_code)
            tmp_file.flush()
            module_path = tmp_file.name

        try:
            # 动态导入模块
            spec = importlib.util.spec_from_file_location(f"dynamic_tool_{tool_name}", module_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load module for {tool_name}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)

            # 获取工具类 - 支持多种匹配方式
            tool_class = None

            # 1. 首先尝试精确匹配
            if hasattr(module, tool_name):
                tool_class = getattr(module, tool_name)
            else:
                # 2. 如果精确匹配失败，尝试去除后缀（如 TIMIScoreTool_1 -> TIMIScoreTool）
                base_name = tool_name.rstrip('_0123456789')  # 去除末尾的下划线和数字
                if hasattr(module, base_name):
                    tool_class = getattr(module, base_name)
                else:
                    # 3. 如果还是找不到，搜索模块中所有继承自BaseTool的类
                    from crewai.tools import BaseTool
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and
                            issubclass(attr, BaseTool) and
                            attr != BaseTool):
                            tool_class = attr
                            break

            if tool_class is None:
                raise AttributeError(
                    f"Cannot find tool class '{tool_name}' in module. "
                    f"Available classes: {[name for name in dir(module) if not name.startswith('_')]}"
                )

            return tool_class
        finally:
            # 清理临时文件
            os.unlink(module_path)