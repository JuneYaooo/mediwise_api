"""
治疗甘特图生成工具
支持三种渲染方式：
1. Plotly (纯Python，推荐，美观)
2. Google Charts (需要网络和浏览器)
3. ECharts (需要本地JS库和浏览器)
"""

import json
import tempfile
import base64
from pathlib import Path
from typing import List, Dict, Any, Optional
from src.utils.logger import BeijingLogger
from src.utils.font_config import FontConfig

logger = BeijingLogger().get_logger()


class TreatmentGanttChartGenerator:
    """治疗甘特图生成器"""

    def __init__(self, use_google_charts=False, use_plotly=True):
        """
        初始化甘特图生成器

        Args:
            use_google_charts: 是否使用Google Charts (True=Google Charts原生甘特图, False=ECharts自定义实现)
            use_plotly: 是否使用Plotly纯Python方案 (默认True，推荐，无需浏览器，美观度高)
        """
        self.use_plotly = use_plotly
        self.use_google_charts = use_google_charts

        # 如果使用Plotly，不需要模板文件
        if use_plotly:
            logger.info("使用 Plotly 纯Python方案生成甘特图")
            return

        if use_google_charts:
            template_name = "treatment_gantt_template_v2.html"  # Google Charts版本
        else:
            template_name = "treatment_gantt_template.html"  # ECharts版本

        self.template_path = Path(__file__).parent.parent / "templates" / template_name
        self.font_dir = Path(__file__).parent.parent / "templates" / "static"

        if not self.template_path.exists():
            raise FileNotFoundError(f"甘特图HTML模板文件不存在: {self.template_path}")

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

    def _generate_font_face_css(self, font_copy_path: Optional[Path] = None) -> str:
        """
        生成@font-face CSS代码

        Args:
            font_copy_path: 字体文件副本路径（与HTML在同一目录，避免跨域问题）
        """
        # 使用统一的字体配置查找字体
        font_path = FontConfig.find_font()

        if not font_path:
            # 尝试从本地 static 目录查找
            font_path = self._find_chinese_font()

            if not font_path:
                logger.warning("将使用系统默认字体（可能无法显示中文）")
                return "/* No custom font available */"

        try:
            # 确定字体格式
            font_format = FontConfig.get_font_format(font_path)

            # 如果提供了字体副本路径，使用相对路径引用（避免base64编码导致HTML过大）
            if font_copy_path:
                css = f'''
@font-face {{
    font-family: 'CustomChinese';
    src: url({font_copy_path.name}) format('{font_format}');
    font-weight: normal;
    font-style: normal;
    font-display: swap;
}}
'''
                logger.info(f"已生成字体CSS（本地文件引用, {font_format}格式，字体: {font_path.name}）")
            else:
                # 降级方案：使用系统字体
                css = '''
/* 使用系统默认中文字体 */
body, * {
    font-family: 'Microsoft YaHei', '微软雅黑', 'PingFang SC', 'Hiragino Sans GB', sans-serif !important;
}
'''
                logger.info("使用系统默认中文字体")

            return css

        except Exception as e:
            logger.error(f"生成字体CSS失败: {e}")
            return "/* Font CSS generation failed */"

    def _prepare_html(
        self,
        gantt_data: List[Dict[str, Any]],
        patient_name: str = "患者",
        font_copy_path: Optional[Path] = None
    ) -> str:
        """
        准备 HTML 内容，注入甘特图数据和字体

        Args:
            gantt_data: 甘特图数据列表
            patient_name: 患者姓名
            font_copy_path: 字体文件副本路径（与HTML在同一目录）

        Returns:
            str: 准备好的 HTML 内容
        """
        try:
            # 读取模板
            with open(self.template_path, 'r', encoding='utf-8') as f:
                html_template = f.read()

            # 生成字体CSS
            font_css = self._generate_font_face_css(font_copy_path)

            # 读取 ECharts 库
            echarts_path = Path(__file__).parent.parent / "templates" / "static" / "echarts.min.js"
            echarts_js = ""
            if echarts_path.exists():
                with open(echarts_path, 'r', encoding='utf-8') as f:
                    echarts_js = f.read()
                logger.info(f"已加载本地 ECharts 库: {echarts_path}")
            else:
                logger.warning(f"本地 ECharts 库不存在: {echarts_path}，将使用 CDN")

            # 将数据转换为 JSON 字符串
            data_json = json.dumps(gantt_data, ensure_ascii=False)

            # 替换占位符
            html_content = html_template.replace('{{FONT_FACE_CSS}}', font_css)
            html_content = html_content.replace('{{DATA_PLACEHOLDER}}', data_json)
            html_content = html_content.replace('{{PATIENT_NAME}}', patient_name)

            # 如果有本地 ECharts，替换 CDN 引用为内联脚本
            if echarts_js:
                html_content = html_content.replace(
                    '<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>',
                    f'<script>{echarts_js}</script>'
                )

            return html_content

        except Exception as e:
            logger.error(f"准备 HTML 内容失败: {e}")
            raise

    def _setup_kaleido_fonts(self) -> tuple[str, str]:
        """
        配置 kaleido 的字体环境

        Returns:
            (font_family, fontconfig_dir): 字体名称和 fontconfig 配置目录
        """
        import os
        import tempfile

        # 使用统一的字体配置查找字体
        font_path = FontConfig.find_font()

        if not font_path:
            logger.warning("未找到可用字体，将使用 Arial")
            return "Arial", None

        chinese_font_path = str(font_path)

        # 创建临时 fontconfig 配置
        fontconfig_dir = tempfile.mkdtemp(prefix="plotly_fonts_")
        fonts_conf_path = Path(fontconfig_dir) / "fonts.conf"

        # 写入 fontconfig XML 配置
        fonts_conf_content = f"""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <dir>{font_path.parent}</dir>
  <match target="pattern">
    <test qual="any" name="family">
      <string>sans-serif</string>
    </test>
    <edit name="family" mode="prepend" binding="strong">
      <string>Source Han Sans SC</string>
    </edit>
  </match>
  <alias>
    <family>Source Han Sans SC</family>
    <default>
      <family>sans-serif</family>
    </default>
  </alias>
</fontconfig>
"""

        with open(fonts_conf_path, 'w', encoding='utf-8') as f:
            f.write(fonts_conf_content)

        # 设置环境变量
        os.environ['FONTCONFIG_FILE'] = str(fonts_conf_path)
        os.environ['FONTCONFIG_PATH'] = fontconfig_dir

        logger.info(f"已创建 fontconfig 配置: {fonts_conf_path}")

        return "Source Han Sans SC", fontconfig_dir

    def _generate_plotly_chart(
        self,
        gantt_data: List[Dict[str, Any]],
        output_path: str,
        patient_name: str = "患者"
    ) -> bool:
        """
        使用 Plotly 生成美观的甘特图（纯Python方案）

        Args:
            gantt_data: 甘特图数据
            output_path: 输出路径
            patient_name: 患者姓名

        Returns:
            bool: 是否成功
        """
        fontconfig_dir = None
        try:
            import plotly.figure_factory as ff
            import plotly.graph_objects as go
            import pandas as pd
            from datetime import datetime

            # 配置中文字体
            font_family, fontconfig_dir = self._setup_kaleido_fonts()

            # 准备数据
            tasks = []
            for item in gantt_data:
                tasks.append({
                    'Task': item.get('task_name', '未知治疗'),
                    'Start': item.get('start_date'),
                    'Finish': item.get('end_date'),
                    'Resource': item.get('category', '其他'),
                    'Description': item.get('dosage_label', '')
                })

            # 转换为DataFrame
            df = pd.DataFrame(tasks)

            # 获取所有唯一的类别
            unique_categories = df['Resource'].unique()

            # 定义颜色映射（医疗专业配色，柔和且易区分）
            default_colors = {
                '系统治疗': 'rgb(52, 152, 219)',       # 清新蓝色 (Dodger Blue)
                '局部治疗': 'rgb(155, 89, 182)',       # 优雅紫色 (Amethyst)
                '辅助/支持治疗': 'rgb(230, 126, 34)',   # 温暖橙色 (Carrot)
                '其他治疗': 'rgb(26, 188, 156)',       # 清爽青绿 (Turquoise)
                '其他': 'rgb(149, 165, 166)'            # 中性灰蓝 (Asbestos)
            }

            # 确保所有类别都有颜色（动态补充缺失的类别）
            colors = {}
            extra_colors = [
                'rgb(241, 196, 15)',   # 明黄色 (Sun Flower)
                'rgb(46, 204, 113)',   # 翠绿色 (Emerald)
                'rgb(231, 76, 60)',    # 柔和红 (Alizarin)
                'rgb(52, 73, 94)',     # 深蓝灰 (Wet Asphalt)
                'rgb(236, 240, 241)',  # 浅灰色 (Clouds)
                'rgb(22, 160, 133)',   # 深青色 (Green Sea)
            ]

            color_idx = 0
            for cat in unique_categories:
                if cat in default_colors:
                    colors[cat] = default_colors[cat]
                else:
                    colors[cat] = extra_colors[color_idx % len(extra_colors)]
                    color_idx += 1
                    logger.warning(f"类别 '{cat}' 未在预定义颜色中，使用额外颜色")

            # 创建甘特图
            fig = ff.create_gantt(
                df,
                colors=colors,
                index_col='Resource',
                show_colorbar=True,
                group_tasks=True,
                showgrid_x=True,
                showgrid_y=True,
                title=f'{patient_name} - 治疗时间轴'
            )

            # 优化布局，使用注册的中文字体
            # 动态计算高度：更紧凑的间距
            chart_height = max(400, len(gantt_data) * 35 + 150)

            fig.update_layout(
                xaxis_type='date',
                font=dict(family=font_family, size=20, color='rgb(44, 62, 80)'),  # 增大字体到20
                title_font=dict(size=28, family=font_family, color='rgb(44, 62, 80)'),  # 增大标题到28
                height=chart_height,
                margin=dict(l=200, r=80, t=120, b=150),  # 增加底部边距以容纳图例
                plot_bgcolor='rgb(250, 250, 250)',
                paper_bgcolor='white',
                xaxis=dict(
                    gridcolor='rgb(230, 230, 230)',
                    showgrid=True,
                    showline=True,
                    linecolor='rgb(200, 200, 200)',
                    tickfont=dict(size=18, family=font_family),  # X轴刻度字体增大到18
                    side='top',  # 将X轴放在顶部
                    rangeselector=dict(visible=False),  # 隐藏范围选择器
                    rangeslider=dict(visible=False),  # 隐藏范围滑块
                ),
                yaxis=dict(
                    showgrid=False,
                    showline=True,
                    linecolor='rgb(200, 200, 200)',
                    tickfont=dict(size=18, family=font_family),  # Y轴标签字体增大到18
                ),
                legend=dict(
                    font=dict(size=18, family=font_family),  # 图例字体增大到18
                    orientation="h",  # 水平方向
                    yanchor="top",  # 锚定到顶部
                    y=-0.15,  # 放在图表下方（y<0 表示在画布外下方）
                    xanchor="center",  # 水平居中
                    x=0.5,  # 居中位置
                    bgcolor='rgba(255, 255, 255, 0.8)',  # 半透明白色背景
                    bordercolor='rgb(200, 200, 200)',
                    borderwidth=1
                )
            )

            # 创建任务名称到y坐标的映射（从图表的yaxis中获取）
            task_to_y = {}
            if fig.layout.yaxis.ticktext and fig.layout.yaxis.tickvals:
                task_to_y = {
                    text: val
                    for val, text in zip(fig.layout.yaxis.tickvals, fig.layout.yaxis.ticktext)
                }

            # 添加注释（剂量信息）- 使用智能策略：同一行只显示部分标签
            annotations_to_add = []

            # 按task_name分组，统计每个任务有多少个时间块
            task_blocks = {}
            for i, item in enumerate(gantt_data):
                task_name = item.get('task_name', '未知治疗')
                if task_name not in task_blocks:
                    task_blocks[task_name] = []

                # 优先使用 dosage_label，如果没有则使用原始剂量信息
                label_text = item.get('dosage_label', '')
                if not label_text:
                    # 如果没有剂量标签，尝试显示原始剂量信息
                    dosage = item.get('dosage', '')
                    if dosage:
                        # 截断过长的剂量信息
                        label_text = dosage[:30] + '...' if len(dosage) > 30 else dosage
                    # 注意：如果没有任何剂量信息，label_text 保持为空，不显示标签

                # 只要有标签文本就添加（不再要求 dosage_label 必须有值）
                if label_text:
                    y_coord = task_to_y.get(task_name)
                    if y_coord is None:
                        logger.warning(f"无法找到任务 '{task_name}' 的y坐标，跳过添加标签")
                        continue

                    start = pd.to_datetime(item['start_date'])
                    end = pd.to_datetime(item['end_date'])
                    mid_date = start + (end - start) / 2

                    task_blocks[task_name].append({
                        'x': mid_date,
                        'y': y_coord,
                        'text': label_text,
                        'start': start,
                        'end': end,
                        'task_name': task_name,
                        'index': i
                    })

            # 智能选择标签显示策略
            for task_name, blocks in task_blocks.items():
                blocks.sort(key=lambda x: x['x'])  # 按时间排序

                # 策略1: 如果同一行的块数量<=3，全部显示
                if len(blocks) <= 3:
                    annotations_to_add.extend(blocks)
                    logger.info(f"任务 '{task_name}' 有 {len(blocks)} 个块，全部显示标签")

                # 策略2: 如果块数量在4-8之间，显示首尾和中间
                elif len(blocks) <= 8:
                    # 显示第1个、最后1个、以及中间均匀分布的几个
                    indices_to_show = [0, len(blocks) - 1]  # 首尾
                    # 中间再选1-2个
                    if len(blocks) >= 5:
                        indices_to_show.append(len(blocks) // 2)  # 中间
                    if len(blocks) >= 7:
                        indices_to_show.append(len(blocks) // 3)  # 1/3处
                        indices_to_show.append(len(blocks) * 2 // 3)  # 2/3处

                    indices_to_show = sorted(set(indices_to_show))
                    selected_blocks = [blocks[i] for i in indices_to_show]
                    annotations_to_add.extend(selected_blocks)
                    logger.info(f"任务 '{task_name}' 有 {len(blocks)} 个块，选择显示 {len(selected_blocks)} 个标签（索引: {indices_to_show}）")

                # 策略3: 如果块数量>8，只显示首尾，并在中间显示一个汇总标签
                else:
                    # 显示第1个和最后1个
                    annotations_to_add.append(blocks[0])
                    annotations_to_add.append(blocks[-1])

                    # 在中间位置添加一个汇总标签
                    middle_index = len(blocks) // 2
                    middle_block = blocks[middle_index]

                    # 检查所有块的剂量是否相同
                    unique_dosages = set(b['text'] for b in blocks if b['text'])
                    if len(unique_dosages) == 1:
                        summary_text = f"{list(unique_dosages)[0]} (共{len(blocks)}次)"
                    else:
                        summary_text = f"(共{len(blocks)}次治疗)"

                    annotations_to_add.append({
                        'x': middle_block['x'],
                        'y': middle_block['y'],
                        'text': summary_text,
                        'start': middle_block['start'],
                        'end': middle_block['end'],
                        'task_name': task_name,
                        'index': middle_block['index']
                    })

                    logger.info(f"任务 '{task_name}' 有 {len(blocks)} 个块，显示首尾+汇总标签")


            # 检测并处理重叠标签 - 全局智能避让算法
            def estimate_label_width_hours(text, font_size=12):
                """估算标签文本在时间轴上占用的宽度（小时）"""
                # 假设平均字符宽度为0.6em，中文字符按2个字符计算
                char_count = sum(2 if '\u4e00' <= c <= '\u9fff' else 1 for c in text)
                # 简化估算：每个字符约占1小时的视觉宽度，留出余量
                return char_count * 2

            def check_overlap_smart(ann1, ann2):
                """智能检测两个标签是否会重叠（考虑文本宽度和y坐标）"""
                # 如果不在接近的y位置，不会重叠
                y_distance = abs(ann1.get('y_adjusted', ann1['y']) - ann2.get('y_adjusted', ann2['y']))
                if y_distance > 0.25:  # y轴距离大于0.25认为不会重叠
                    return False

                # 计算两个标签的时间中心和宽度
                width1 = estimate_label_width_hours(ann1['text'])
                width2 = estimate_label_width_hours(ann2['text'])

                # 计算时间差（小时）
                time_diff_hours = abs((ann1['x'] - ann2['x']).total_seconds() / 3600)

                # 如果时间差小于两个标签宽度之和的一半，则重叠
                min_distance = (width1 + width2) / 2
                return time_diff_hours < min_distance

            # 定义可用的偏移层级（从上到下交替）
            # 格式: (y_offset, arrow_length, level_name)
            offset_layers = [
                (0, 0, 'center'),           # 层0: 中心，无箭头
                (0.32, -28, 'up1'),         # 层1: 向上第1层
                (-0.32, 28, 'down1'),       # 层2: 向下第1层
                (0.58, -45, 'up2'),         # 层3: 向上第2层
                (-0.58, 45, 'down2'),       # 层4: 向下第2层
                (0.82, -62, 'up3'),         # 层5: 向上第3层
                (-0.82, 62, 'down3'),       # 层6: 向下第3层
                (1.05, -78, 'up4'),         # 层7: 向上第4层
                (-1.05, 78, 'down4'),       # 层8: 向下第4层
            ]

            # 全局贪心算法：按时间顺序处理所有标签
            # 按时间和y坐标排序（确保从左到右、从上到下处理）
            annotations_to_add.sort(key=lambda x: (x['x'], x['y']))

            # 为每个标签找到第一个不重叠的层级
            for i, ann in enumerate(annotations_to_add):
                best_layer = None

                # 尝试每一层，找到第一个不重叠的层
                for layer_idx, (y_offset, arrow_length, layer_name) in enumerate(offset_layers):
                    # 临时分配该层
                    ann['y_adjusted'] = ann['y'] + y_offset
                    ann['layer_idx'] = layer_idx

                    # 检查与之前已分配的所有标签是否重叠
                    has_conflict = False
                    for j in range(i):
                        if check_overlap_smart(ann, annotations_to_add[j]):
                            has_conflict = True
                            break

                    # 找到不冲突的层，使用它
                    if not has_conflict:
                        best_layer = (y_offset, arrow_length, layer_name)
                        break

                # 如果所有层都冲突，使用轮换策略（按序号分配）
                if best_layer is None:
                    layer_idx = (i % len(offset_layers))
                    y_offset, arrow_length, layer_name = offset_layers[layer_idx]
                    ann['y_adjusted'] = ann['y'] + y_offset
                    ann['layer_idx'] = layer_idx
                    logger.warning(f"标签 '{ann['text'][:10]}...' 无法完全避免重叠，使用轮换层级 {layer_name}")
                else:
                    y_offset, arrow_length, layer_name = best_layer

                # 存储最终的偏移信息
                ann['final_y_offset'] = y_offset
                ann['final_arrow_length'] = arrow_length

            # 统一添加所有标注到图表
            for ann in annotations_to_add:
                y_offset = ann['final_y_offset']
                arrow_length = ann['final_arrow_length']

                if y_offset == 0:
                    # 中心层，无箭头
                    fig.add_annotation(
                        x=ann['x'],
                        y=ann['y'],
                        text=ann['text'],
                        showarrow=False,
                        font=dict(size=16, color='rgb(52, 73, 94)', family=font_family, weight='bold')  # 增大到16
                    )
                else:
                    # 其他层，带箭头指向时间块
                    fig.add_annotation(
                        x=ann['x'],
                        y=ann['y'] + y_offset,
                        text=ann['text'],
                        showarrow=True,
                        arrowhead=2,
                        arrowsize=1,
                        arrowwidth=1.5,
                        arrowcolor='rgb(100, 100, 100)',
                        ax=0,
                        ay=arrow_length,
                        font=dict(size=15, color='rgb(52, 73, 94)', family=font_family)  # 增大到15
                    )

            # 保存为PNG，使用更紧凑的尺寸
            fig.write_image(output_path, width=1600, height=chart_height)
            logger.info(f"Plotly甘特图已生成: {output_path}")
            return True

        except ImportError as e:
            logger.error(f"Plotly未安装或缺少依赖: {e}")
            logger.info("请安装: pip install plotly kaleido pandas")
            return False
        except Exception as e:
            logger.error(f"生成Plotly甘特图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
        finally:
            # 清理临时 fontconfig 目录
            if fontconfig_dir and Path(fontconfig_dir).exists():
                try:
                    import shutil
                    shutil.rmtree(fontconfig_dir)
                    logger.info(f"已清理 fontconfig 临时目录: {fontconfig_dir}")
                except Exception as e:
                    logger.warning(f"清理 fontconfig 临时目录失败: {e}")

    def generate_image(
        self,
        gantt_data: List[Dict[str, Any]],
        output_path: str,
        patient_name: str = "患者"
    ) -> bool:
        """
        生成治疗甘特图图片

        Args:
            gantt_data: 甘特图数据列表，格式：
                [
                    {
                        "id": "treatment_0",
                        "task_name": "治疗类别\\n具体方法/药物",
                        "start_date": "YYYY-MM-DD",
                        "end_date": "YYYY-MM-DD",
                        "dosage_label": "剂量标签",
                        "category": "治疗类别",
                        ...
                    }
                ]
            output_path: 输出图片路径
            patient_name: 患者姓名

        Returns:
            bool: 成功返回 True，失败返回 False
        """
        if not gantt_data or len(gantt_data) == 0:
            logger.warning("甘特图数据为空，无法生成图片")
            return False

        # 统计治疗类型分布
        treatment_types = {}
        for item in gantt_data:
            t_type = item.get('treatment_type', '未分类')
            treatment_types[t_type] = treatment_types.get(t_type, 0) + 1

        logger.info(f"开始生成治疗甘特图: 共 {len(gantt_data)} 条记录, {len(treatment_types)} 个治疗类型")
        logger.info(f"治疗类型分布: {treatment_types}")

        # 如果使用Plotly，直接调用Plotly方法
        if self.use_plotly:
            return self._generate_plotly_chart(gantt_data, output_path, patient_name)

        # 浏览器渲染方式需要 playwright
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            logger.error("Playwright未安装，无法使用浏览器渲染方式")
            logger.info("请安装: pip install playwright && playwright install chromium")
            return False

        temp_html_path = None
        temp_font_path = None
        try:
            # 创建临时目录
            temp_dir = Path(tempfile.mkdtemp())

            # 复制字体文件到临时目录（避免base64编码导致HTML过大）
            font_path = FontConfig.find_font()
            if font_path:
                import shutil
                temp_font_path = temp_dir / font_path.name
                shutil.copy(font_path, temp_font_path)
                logger.info(f"已复制字体文件到临时目录: {temp_font_path}")
            else:
                temp_font_path = None
                logger.warning("未找到字体文件，将使用系统字体")

            # 准备 HTML（传入字体副本路径）
            html_content = self._prepare_html(gantt_data, patient_name, temp_font_path)

            # 创建临时 HTML 文件（放在同一目录）
            temp_html_path = temp_dir / "gantt_chart.html"
            with open(temp_html_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            # 使用 Playwright 渲染
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

                # 计算动态高度：根据治疗记录数量（确保有足够空间）
                item_height = 100
                base_height = 400
                estimated_height = max(1000, base_height + len(gantt_data) * item_height)

                context = browser.new_context(
                    viewport={'width': 2800, 'height': estimated_height},  # 增加宽度以容纳更宽的图表
                    device_scale_factor=2  # 2倍缩放以提高清晰度
                )

                page = context.new_page()

                # 加载 HTML - 等待网络资源加载
                page.goto(f'file://{temp_html_path.absolute()}', timeout=60000, wait_until='networkidle')

                # 等待网络空闲（Google Charts加载）
                try:
                    page.wait_for_load_state('networkidle', timeout=10000)
                except:
                    logger.warning("等待网络空闲超时，继续渲染")

                # 根据使用的图表库类型等待相应的初始化
                chart_lib = "ECharts" if not self.use_google_charts else "Google Charts"
                logger.info(f"等待 {chart_lib} 初始化...")

                if self.use_google_charts:
                    # Google Charts: 等待 google.visualization 对象
                    page.wait_for_function('typeof google !== "undefined" && typeof google.visualization !== "undefined"', timeout=30000)
                else:
                    # ECharts: 等待 echarts 对象
                    page.wait_for_function('typeof echarts !== "undefined"', timeout=30000)

                # 等待图表渲染完成（等待 chart-ready 类，不需要可见）
                page.wait_for_selector('.chart-ready', state='attached', timeout=30000)
                logger.info(f"{chart_lib} 甘特图渲染完成")

                # 额外等待确保图表完全渲染
                page.wait_for_timeout(2000)

                # 确保输出目录存在
                output_path_obj = Path(output_path)
                output_path_obj.parent.mkdir(parents=True, exist_ok=True)

                # 获取容器并截图
                container = page.locator('.container')
                container.screenshot(path=output_path, type='png')

                logger.info(f"治疗甘特图已生成: {output_path}")

                browser.close()

            return True

        except Exception as e:
            logger.error(f"生成治疗甘特图失败: {e}")
            import traceback
            logger.error(traceback.format_exc())

            # 保留临时HTML文件用于调试
            if temp_html_path and temp_html_path.exists():
                logger.error(f"临时 HTML 文件已保留用于调试: {temp_html_path}")

            return False

        finally:
            # 清理临时文件
            if temp_html_path and temp_html_path.exists():
                try:
                    import shutil
                    # 删除整个临时目录（包含HTML和字体文件）
                    temp_dir = temp_html_path.parent
                    if temp_dir.exists():
                        shutil.rmtree(temp_dir)
                        logger.info(f"已清理临时目录: {temp_dir}")
                except Exception as e:
                    logger.warning(f"删除临时文件失败: {e}")


def generate_treatment_gantt_chart_sync(
    gantt_data: List[Dict[str, Any]],
    output_path: str,
    patient_name: str = "患者",
    use_plotly: bool = True,
    use_google_charts: bool = False
) -> bool:
    """
    同步生成治疗甘特图的便捷函数

    Args:
        gantt_data: 甘特图数据列表
        output_path: 输出图片路径
        patient_name: 患者姓名
        use_plotly: 是否使用Plotly纯Python方案 (默认True，推荐，美观且无需浏览器)
        use_google_charts: 是否使用Google Charts原生甘特图 (需要网络和浏览器)

    Returns:
        bool: 成功返回 True，失败返回 False
    """
    generator = TreatmentGanttChartGenerator(
        use_google_charts=use_google_charts,
        use_plotly=use_plotly
    )
    return generator.generate_image(gantt_data, output_path, patient_name)


# 异步版本（如果需要）
async def generate_treatment_gantt_chart(
    gantt_data: List[Dict[str, Any]],
    output_path: str,
    patient_name: str = "患者"
) -> bool:
    """
    异步生成治疗甘特图

    Args:
        gantt_data: 甘特图数据列表
        output_path: 输出图片路径
        patient_name: 患者姓名

    Returns:
        bool: 成功返回 True，失败返回 False
    """
    import asyncio
    return await asyncio.to_thread(
        generate_treatment_gantt_chart_sync,
        gantt_data,
        output_path,
        patient_name
    )
