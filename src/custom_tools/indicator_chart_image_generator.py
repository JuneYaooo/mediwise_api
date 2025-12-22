"""
Indicator Chart Image Generator Tool

生成核心指标趋势图片，使用 Playwright 渲染 HTML 模板
与前端 PatientIndicatorChart 组件效果一致
"""

import json
import tempfile
import base64
from pathlib import Path
from typing import List, Dict, Optional
from playwright.sync_api import sync_playwright
from src.utils.logger import BeijingLogger

logger = BeijingLogger().get_logger()


class IndicatorChartImageGenerator:
    """核心指标趋势图片生成器"""

    def __init__(self):
        self.template_path = Path(__file__).parent.parent / "templates" / "indicator_chart_template.html"
        self.chartjs_path = Path(__file__).parent.parent / "templates" / "static" / "chart.umd.js"
        self.font_dir = Path(__file__).parent.parent / "templates" / "static"

    def _find_chinese_font(self) -> Optional[Path]:
        """查找可用的中文字体文件"""
        font_extensions = ['.ttf', '.otf', '.woff', '.woff2']
        font_patterns = [
            'chinese-font',
            'noto-sans',
            'source-han',
            'wenquanyi',
            'alibaba',
            'simhei',
            'simsun'
        ]

        for font_file in self.font_dir.glob('*'):
            if font_file.suffix.lower() in font_extensions:
                name_lower = font_file.stem.lower()
                if any(pattern in name_lower for pattern in font_patterns):
                    logger.info(f"找到中文字体文件: {font_file.name}")
                    return font_file

        logger.warning("未找到中文字体文件")
        return None

    def _generate_font_face_css(self) -> str:
        """生成@font-face CSS代码 - 使用文件路径而不是base64内联"""
        # 使用指定的中文字体路径
        font_path = Path("/home/ubuntu/font/SiYuanHeiTi-Regular/SourceHanSansSC-Regular-2.otf")

        if not font_path.exists():
            logger.warning(f"指定的字体文件不存在: {font_path}，将尝试查找其他字体")
            font_path = self._find_chinese_font()

            if not font_path:
                logger.warning("将使用系统默认字体（可能无法显示中文）")
                return "/* No custom font available */"

        try:
            # 确定字体格式
            font_format = {
                '.ttf': 'truetype',
                '.otf': 'opentype',
                '.woff': 'woff',
                '.woff2': 'woff2'
            }.get(font_path.suffix.lower(), 'truetype')

            # 使用本地文件路径而不是base64，避免文件过大导致超时
            css = f'''
@font-face {{
    font-family: 'CustomChinese';
    src: url('file://{font_path.absolute()}') format('{font_format}');
    font-weight: normal;
    font-style: normal;
    font-display: swap;
}}
'''
            logger.info(f"已生成字体CSS（文件路径模式，{font_format}格式，字体: {font_path.name}）")
            return css

        except Exception as e:
            logger.error(f"生成字体CSS失败: {e}")
            return "/* Font CSS generation failed */"

    def _prepare_html(self, indicator_series_data: List[Dict], patient_name: str = "患者") -> str:
        """
        准备 HTML 内容，注入数据、Chart.js库和字体

        Args:
            indicator_series_data: 指标序列数据列表
            patient_name: 患者姓名

        Returns:
            str: 准备好的 HTML 内容
        """
        try:
            # 读取模板
            with open(self.template_path, 'r', encoding='utf-8') as f:
                html_template = f.read()

            # 读取Chart.js库
            chartjs_code = ""
            if self.chartjs_path.exists():
                with open(self.chartjs_path, 'r', encoding='utf-8') as f:
                    chartjs_code = f.read()
                logger.info("已加载本地Chart.js库")
            else:
                logger.warning(f"本地Chart.js库不存在: {self.chartjs_path}")
                # 降级使用CDN
                chartjs_code = '''
                // 降级使用CDN
                var script = document.createElement('script');
                script.src = 'https://unpkg.com/chart.js@4.4.0/dist/chart.umd.js';
                document.head.appendChild(script);
                '''

            # 生成字体CSS
            font_css = self._generate_font_face_css()

            # 将数据转换为 JSON 字符串
            data_json = json.dumps(indicator_series_data, ensure_ascii=False)

            # 替换占位符
            html_content = html_template.replace('{{CHARTJS_PLACEHOLDER}}', chartjs_code)
            html_content = html_content.replace('{{FONT_FACE_CSS}}', font_css)
            html_content = html_content.replace('{{DATA_PLACEHOLDER}}', data_json)
            html_content = html_content.replace('{{PATIENT_NAME}}', patient_name)

            return html_content

        except Exception as e:
            logger.error(f"准备 HTML 内容失败: {e}")
            raise

    def generate_image(
        self,
        indicator_series_data: List[Dict],
        output_path: str,
        patient_name: str = "患者"
    ) -> bool:
        """
        生成核心指标趋势图片（单个指标）

        Args:
            indicator_series_data: 指标序列数据（单个指标）
                格式: [
                    {
                        "name": "指标名称",
                        "unit": "单位(可选)",
                        "normal_min": 正常范围最小值(可选),
                        "normal_max": 正常范围最大值(可选),
                        "series": [
                            {"time": "yyyy-MM-dd", "value": 数值, "is_abnormal": 布尔值},
                            ...
                        ]
                    }
                ]
            output_path: 输出图片路径
            patient_name: 患者姓名

        Returns:
            bool: 成功返回 True，失败返回 False
        """
        if not indicator_series_data or len(indicator_series_data) == 0:
            logger.warning("指标数据为空，无法生成图片")
            return False

        temp_html_path = None
        try:
            logger.info(f"开始生成核心指标趋势图片，包含 {len(indicator_series_data)} 个指标")

            # 准备 HTML
            html_content = self._prepare_html(indicator_series_data, patient_name)

            # 创建临时 HTML 文件
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as f:
                f.write(html_content)
                temp_html_path = Path(f.name)

            logger.info(f"临时 HTML 文件: {temp_html_path}")

            # 使用 Playwright 渲染（在单独线程中运行以避免 asyncio 冲突）
            import os
            import asyncio

            # 检测是否在 asyncio 事件循环中
            try:
                asyncio.get_running_loop()
                # 在事件循环中，使用线程池运行同步代码
                import concurrent.futures

                def _run_playwright():
                    return self._capture_screenshot_sync(temp_html_path, output_path)

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(_run_playwright)
                    result = future.result(timeout=30)
                    return result

            except RuntimeError:
                # 不在事件循环中，直接运行
                pass

            return self._capture_screenshot_sync(temp_html_path, output_path)

        except Exception as e:
            logger.error(f"生成核心指标趋势图片失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

            # 保留临时HTML文件用于调试
            if temp_html_path and temp_html_path.exists():
                logger.error(f"临时 HTML 文件已保留用于调试: {temp_html_path}")

            return False

        finally:
            # 成功时清理临时文件
            if temp_html_path and temp_html_path.exists():
                try:
                    # 只有当没有异常时才删除（这里不会执行删除，因为异常时会return）
                    pass
                except Exception as e:
                    logger.warning(f"删除临时 HTML 文件失败: {e}")

    def _capture_screenshot_sync(self, temp_html_path: Path, output_path: str) -> bool:
        """
        使用 Playwright 同步 API 截图（在单独线程中运行）

        Args:
            temp_html_path: 临时 HTML 文件路径
            output_path: 输出图片路径

        Returns:
            是否成功
        """
        import os

        with sync_playwright() as p:
            # 准备环境变量
            env_vars = os.environ.copy()
            env_vars.update({
                'LANG': 'zh_CN.UTF-8',
                'LC_ALL': 'zh_CN.UTF-8',
            })

            browser = p.chromium.launch(
                headless=True,
                args=[
                    '--font-render-hinting=none',
                    '--disable-gpu',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--force-device-scale-factor=1',
                    '--disable-font-subpixel-positioning',
                    '--force-color-profile=srgb',
                    '--lang=zh-CN'
                ],
                env=env_vars
            )

            estimated_height = 950

            context = browser.new_context(
                viewport={'width': 1200, 'height': estimated_height},
                device_scale_factor=2
            )

            page = context.new_page()
            page.on('console', lambda msg: logger.debug(f"Browser console: {msg.text}"))

            logger.info("加载HTML页面...")
            page.goto(f'file://{temp_html_path.absolute()}', timeout=120000, wait_until='load')
            logger.info("HTML页面资源加载完成")

            logger.info("等待Chart.js初始化...")
            page.wait_for_function('typeof Chart !== "undefined"', timeout=10000)
            logger.info("Chart.js已就绪")

            logger.info("等待图表渲染...")
            page.wait_for_selector('canvas', timeout=10000)
            logger.info("Canvas元素已创建")

            page.wait_for_selector('.charts-ready', timeout=10000)
            logger.info("图表渲染标记完成")

            page.wait_for_timeout(1000)
            logger.info("图表渲染完成")

            output_path_obj = Path(output_path)
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)

            container = page.locator('#main-container')
            container.screenshot(path=output_path, type='png')

            logger.info(f"核心指标趋势图片已生成: {output_path}")

            browser.close()

        return True

    def generate_multiple_images(
        self,
        indicator_series_data: List[Dict],
        output_dir: str,
        patient_name: str = "患者"
    ) -> List[Dict[str, str]]:
        """
        为每个指标生成独立的趋势图片

        Args:
            indicator_series_data: 指标序列数据列表
            output_dir: 输出目录路径
            patient_name: 患者姓名

        Returns:
            List[Dict]: 生成的图片信息列表，每个字典包含:
                - indicator_name: 指标名称
                - file_path: 图片文件路径
                - success: 是否成功生成
        """
        if not indicator_series_data or len(indicator_series_data) == 0:
            logger.warning("指标数据为空，无法生成图片")
            return []

        results = []
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"开始为 {len(indicator_series_data)} 个指标生成独立的趋势图片")

        for index, indicator in enumerate(indicator_series_data):
            indicator_name = indicator.get('name', f'indicator_{index}')
            # 生成安全的文件名
            safe_filename = "".join(c if c.isalnum() or c in ('_', '-') else '_' for c in indicator_name)
            output_path = output_dir_path / f"indicator_{index}_{safe_filename}.png"

            logger.info(f"正在生成指标 '{indicator_name}' 的图片...")

            # 为单个指标生成图片（作为单元素列表传递）
            success = self.generate_image([indicator], str(output_path), patient_name)

            results.append({
                "indicator_name": indicator_name,
                "file_path": str(output_path) if success else None,
                "success": success
            })

            if success:
                logger.info(f"指标 '{indicator_name}' 图片生成成功: {output_path}")
            else:
                logger.error(f"指标 '{indicator_name}' 图片生成失败")

        successful_count = sum(1 for r in results if r['success'])
        logger.info(f"图片生成完成: {successful_count}/{len(indicator_series_data)} 个指标成功")

        return results


def generate_indicator_chart_image_sync(
    indicator_series_data: List[Dict],
    output_path: str,
    patient_name: str = "患者"
) -> bool:
    """
    同步生成核心指标趋势图片的便捷函数

    Args:
        indicator_series_data: 指标序列数据
        output_path: 输出图片路径
        patient_name: 患者姓名

    Returns:
        bool: 成功返回 True，失败返回 False
    """
    generator = IndicatorChartImageGenerator()
    return generator.generate_image(indicator_series_data, output_path, patient_name)


def generate_indicator_chart_images_multiple_sync(
    indicator_series_data: List[Dict],
    output_dir: str,
    patient_name: str = "患者"
) -> List[Dict[str, str]]:
    """
    同步生成多个独立的核心指标趋势图片的便捷函数

    Args:
        indicator_series_data: 指标序列数据列表
        output_dir: 输出目录路径
        patient_name: 患者姓名

    Returns:
        List[Dict]: 生成的图片信息列表
    """
    generator = IndicatorChartImageGenerator()
    return generator.generate_multiple_images(indicator_series_data, output_dir, patient_name)


# 异步版本（如果需要）
async def generate_indicator_chart_image(
    indicator_series_data: List[Dict],
    output_path: str,
    patient_name: str = "患者"
) -> bool:
    """
    异步生成核心指标趋势图片

    Args:
        indicator_series_data: 指标序列数据
        output_path: 输出图片路径
        patient_name: 患者姓名

    Returns:
        bool: 成功返回 True，失败返回 False
    """
    # 由于 Playwright 的 sync_api 不支持异步，这里直接调用同步版本
    # 在异步上下文中可以使用 asyncio.to_thread 来避免阻塞
    import asyncio
    return await asyncio.to_thread(
        generate_indicator_chart_image_sync,
        indicator_series_data,
        output_path,
        patient_name
    )
