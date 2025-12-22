"""
患者时间旅程图片生成工具
使用Playwright渲染前端样式的S型患者时间旅程图，并生成图片
"""

import json
import os
import uuid
import base64
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright
from src.utils.logger import BeijingLogger

logger = BeijingLogger().get_logger()


class PatientJourneyImageGenerator:
    """患者时间旅程图片生成器 - 使用Playwright渲染前端样式"""

    def __init__(self):
        self.template_path = Path(__file__).parent.parent / "templates" / "patient_journey_template.html"
        self.font_dir = Path(__file__).parent.parent / "templates" / "static"

        if not self.template_path.exists():
            raise FileNotFoundError(f"HTML模板文件不存在: {self.template_path}")

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
        """生成@font-face CSS代码"""
        # 使用指定的中文字体路径
        font_path = Path("/home/ubuntu/font/SiYuanHeiTi-Regular/SourceHanSansSC-Regular-2.otf")

        if not font_path.exists():
            logger.warning(f"指定的字体文件不存在: {font_path}，将尝试查找其他字体")
            font_path = self._find_chinese_font()

            if not font_path:
                logger.warning("将使用系统默认字体（可能无法显示中文）")
                return "/* No custom font available */"

        try:
            # 读取字体文件并转换为base64
            with open(font_path, 'rb') as f:
                font_data = f.read()

            font_base64 = base64.b64encode(font_data).decode('utf-8')

            # 确定字体格式
            font_format = {
                '.ttf': 'truetype',
                '.otf': 'opentype',
                '.woff': 'woff',
                '.woff2': 'woff2'
            }.get(font_path.suffix.lower(), 'truetype')

            css = f'''
@font-face {{
    font-family: 'CustomChinese';
    src: url(data:font/{font_format};base64,{font_base64}) format('{font_format}');
    font-weight: normal;
    font-style: normal;
    font-display: swap;
}}
'''
            logger.info(f"已生成字体CSS（{len(font_base64)} bytes, {font_format}格式，字体: {font_path.name}）")
            return css

        except Exception as e:
            logger.error(f"生成字体CSS失败: {e}")
            return "/* Font CSS generation failed */"

    def _prepare_html(self, patient_journey_data: List[Dict[str, Any]], patient_name: str) -> str:
        """
        准备HTML内容，注入患者数据和字体

        Args:
            patient_journey_data: 患者旅程数据
            patient_name: 患者姓名

        Returns:
            处理后的HTML字符串
        """
        with open(self.template_path, 'r', encoding='utf-8') as f:
            html_template = f.read()

        # 生成字体CSS
        font_css = self._generate_font_face_css()

        # 将数据转换为JSON字符串并注入到HTML中
        data_json = json.dumps(patient_journey_data, ensure_ascii=False)

        # 替换占位符
        html_content = html_template.replace('{{FONT_FACE_CSS}}', font_css)
        html_content = html_content.replace('{{DATA_PLACEHOLDER}}', data_json)
        html_content = html_content.replace('{{PATIENT_NAME}}', patient_name)

        return html_content

    async def generate_image(
        self,
        patient_journey_data: List[Dict[str, Any]],
        output_path: str,
        patient_name: str = "患者",
        viewport_width: int = 3000,
        viewport_height: int = 1500
    ) -> bool:
        """
        生成患者时间旅程图片

        Args:
            patient_journey_data: 患者旅程数据列表，格式：
                [{"date": "2023-01-01", "type": "主疾病", "text": "...", "chief_surgeon": "..."}]
            output_path: 输出图片路径
            patient_name: 患者姓名
            viewport_width: 视口宽度
            viewport_height: 视口高度（会根据内容自动调整）

        Returns:
            是否成功生成
        """
        try:
            if not patient_journey_data:
                logger.warning("患者旅程数据为空，无法生成图片")
                return False

            # 确保输出目录存在
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # 准备HTML内容
            html_content = self._prepare_html(patient_journey_data, patient_name)

            # 创建临时HTML文件
            temp_html_path = Path(output_path).parent / f"temp_{uuid.uuid4().hex}.html"
            with open(temp_html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            logger.info(f"临时HTML文件已创建: {temp_html_path}")

            # 使用Playwright渲染并截图
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--font-render-hinting=none',
                        '--disable-gpu',
                        '--disable-dev-shm-usage',
                        '--no-sandbox',
                        '--force-color-profile=srgb',
                        '--lang=zh-CN'
                    ]
                )

                # 创建上下文和页面
                context = await browser.new_context(
                    viewport={'width': viewport_width, 'height': viewport_height},
                    device_scale_factor=2  # 2倍缩放，提高清晰度
                )
                page = await context.new_page()

                # 添加控制台日志监听（用于调试）
                page.on('console', lambda msg: logger.debug(f"Browser console: {msg.text}"))

                # 加载HTML文件 - 等待网络资源和外部字体加载
                logger.info("加载HTML页面...")
                await page.goto(f'file://{temp_html_path.absolute()}', timeout=30000, wait_until='networkidle')
                logger.info("HTML页面加载完成")

                # 等待Google Fonts加载
                try:
                    await page.wait_for_load_state('networkidle', timeout=5000)
                except:
                    logger.warning("等待网络空闲超时，继续渲染")

                # 等待页面渲染完成
                await page.wait_for_timeout(2000)  # 等待2秒确保字体和渲染完成
                logger.info("页面渲染完成")

                # 获取实际内容高度和宽度
                chart_container = page.locator('#chartContainer')
                chart_box = await chart_container.bounding_box()

                if chart_box:
                    chart_height = chart_box['height']
                    chart_width = chart_box['width']
                else:
                    chart_height = viewport_height
                    chart_width = viewport_width

                # 截取整个容器（包含padding以确保不裁剪）
                container = page.locator('.container')
                await container.screenshot(path=output_path, type='png', omit_background=True)

                logger.info(f"患者时间旅程图片已生成: {output_path}")

                # 关闭浏览器
                await browser.close()

            # 删除临时HTML文件
            if temp_html_path.exists():
                temp_html_path.unlink()
                logger.info(f"临时HTML文件已删除: {temp_html_path}")

            return True

        except Exception as e:
            logger.error(f"生成患者时间旅程图片失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False


async def generate_patient_journey_image(
    patient_journey_data: List[Dict[str, Any]],
    output_path: str,
    patient_name: str = "患者"
) -> bool:
    """
    异步便捷函数：生成患者时间旅程图片

    Args:
        patient_journey_data: 患者旅程数据
        output_path: 输出图片路径
        patient_name: 患者姓名

    Returns:
        是否成功生成
    """
    generator = PatientJourneyImageGenerator()
    return await generator.generate_image(patient_journey_data, output_path, patient_name)


def generate_patient_journey_image_sync(
    patient_journey_data: List[Dict[str, Any]],
    output_path: str,
    patient_name: str = "患者"
) -> bool:
    """
    同步便捷函数：生成患者时间旅程图片

    Args:
        patient_journey_data: 患者旅程数据
        output_path: 输出图片路径
        patient_name: 患者姓名

    Returns:
        是否成功生成
    """
    generator = PatientJourneyImageGenerator()
    return asyncio.run(generator.generate_image(patient_journey_data, output_path, patient_name))
