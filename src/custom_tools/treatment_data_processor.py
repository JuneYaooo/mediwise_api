"""
治疗数据处理工具
从患者信息中提取治疗数据，并根据配置文件分类整理，生成甘特图所需的数据格式
"""

import pandas as pd
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
from src.utils.logger import BeijingLogger
from src.custom_tools.treatment_extractor_llm import TreatmentExtractorLLM

logger = BeijingLogger().get_logger()


class TreatmentDataProcessor:
    """治疗数据处理器"""

    def __init__(self, config_path: str = "./app/config/treatment_config.xlsx"):
        """
        初始化处理器

        Args:
            config_path: 治疗配置Excel文件路径
        """
        self.config_path = Path(config_path)
        self.treatment_config = None
        self.llm_extractor = None  # 延迟初始化
        self._load_config()

    def _load_config(self):
        """加载治疗配置文件"""
        try:
            if not self.config_path.exists():
                logger.error(f"治疗配置文件不存在: {self.config_path}")
                return

            df = pd.read_excel(self.config_path)
            logger.info(f"成功加载治疗配置文件，共 {len(df)} 行配置")

            # 将配置转换为字典列表便于查询
            self.treatment_config = []
            for _, row in df.iterrows():
                config_item = {
                    "category": str(row.get("治疗类别", "")).strip() if pd.notna(row.get("治疗类别")) else None,
                    "treatment_type": str(row.get("具体治疗方式", "")).strip() if pd.notna(row.get("具体治疗方式")) else None,
                    "methods_drugs": str(row.get("具体方法/药物（化学名 & 商品名）", "")).strip() if pd.notna(row.get("具体方法/药物（化学名 & 商品名）")) else None
                }
                # 只添加有效配置
                if config_item["category"] or config_item["treatment_type"] or config_item["methods_drugs"]:
                    self.treatment_config.append(config_item)

            logger.info(f"解析了 {len(self.treatment_config)} 条有效治疗配置")

            # 初始化 LLM 提取器，传入配置
            self.llm_extractor = TreatmentExtractorLLM(treatment_config=self.treatment_config)
            logger.info("已将治疗配置传递给大模型提取器")

        except Exception as e:
            logger.error(f"加载治疗配置文件失败: {e}")
            import traceback
            logger.error(traceback.format_exc())


    def _extract_treatments_from_patient_data(self, patient_data: Any) -> List[Dict[str, Any]]:
        """
        使用大模型从患者数据中提取治疗信息

        Args:
            patient_data: 患者数据（可以是dict、list等多种格式）

        Returns:
            治疗事件列表，每个事件包含：
            {
                "date": "YYYY-MM-DD",
                "end_date": "YYYY-MM-DD",
                "treatment_text": "治疗描述",
                "dosage": "剂量信息（如果有）",
                "duration": "治疗时长（如果有）"
            }
        """
        logger.info("使用大模型提取患者治疗数据...")

        try:
            # 确保 LLM 提取器已初始化
            if not self.llm_extractor:
                logger.warning("LLM提取器未初始化，使用默认配置初始化")
                self.llm_extractor = TreatmentExtractorLLM(treatment_config=self.treatment_config)

            # 使用大模型提取治疗数据（支持分块处理）
            treatments = self.llm_extractor.extract_treatments(patient_data)
            logger.info(f"大模型成功提取了 {len(treatments)} 条治疗记录")
            return treatments

        except Exception as e:
            logger.error(f"使用大模型提取治疗数据失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _get_category_order(self, category: str) -> int:
        """
        获取治疗类别在配置中的顺序

        Args:
            category: 治疗类别

        Returns:
            顺序索引（越小越靠前）
        """
        if not self.treatment_config:
            return 999

        # 在配置中查找第一个匹配的类别
        for idx, config in enumerate(self.treatment_config):
            if config["category"] == category:
                return idx

        # 如果没找到，返回一个大数值（排在最后）
        return 999

    def process_patient_treatments(self, patient_data: Any) -> List[Dict[str, Any]]:
        """
        处理患者治疗数据，生成甘特图所需的数据格式

        Args:
            patient_data: 患者数据

        Returns:
            甘特图数据列表，每个项目包含：
            {
                "id": 唯一标识,
                "task_name": "治疗类别\\n具体方法/药物",
                "start_date": "YYYY-MM-DD",
                "end_date": "YYYY-MM-DD",
                "dosage_label": "剂量标签",
                "category": "治疗类别",
                "treatment_type": "具体治疗方式",
                "methods_drugs": "具体方法/药物",
                "matched_drug": "匹配到的具体药物名",
                "raw_treatment_text": "原始治疗文本",
                "source_file": "来源文件名或ID"
            }
        """
        # 简化日志：只打印关键信息
        logger.info(f"开始处理患者治疗数据 (输入类型: {type(patient_data).__name__})")

        # 使用大模型提取治疗数据（已经包含分类信息）
        treatments = self._extract_treatments_from_patient_data(patient_data)

        if not treatments:
            logger.warning("未找到治疗数据")
            return []

        logger.info(f"成功提取 {len(treatments)} 条治疗记录")

        # 格式化为甘特图数据
        gantt_data = []
        for idx, treatment in enumerate(treatments):
            try:
                # 大模型已经返回了分类信息
                category = treatment.get("category", "其他治疗")
                treatment_type = treatment.get("treatment_type", "未分类")
                matched_drug = treatment.get("matched_drug", treatment["treatment_text"])

                # 优化任务名称显示：治疗类别\n匹配的具体药物（简化显示）
                # 智能换行：如果药物名称太长，在合适的位置换行
                def smart_line_break(text, max_length=20):
                    """在合适的位置添加换行符"""
                    if len(text) <= max_length:
                        return text

                    # 尝试在标点符号处换行
                    break_chars = ['、', '，', ',', '；', ';', '：', ':', '联合', '及', '和']
                    for i in range(max_length, len(text)):
                        if text[i] in break_chars or (i > 0 and text[i-1] in break_chars):
                            return text[:i] + '\n' + smart_line_break(text[i:], max_length)

                    # 如果没有合适的断点，在max_length处强制换行
                    if len(text) > max_length * 2:
                        return text[:max_length] + '\n' + smart_line_break(text[max_length:], max_length)

                    return text

                # 对药物名称进行智能换行
                matched_drug_formatted = smart_line_break(matched_drug, max_length=20)

                # 如果总长度超过60字符，截断
                if len(matched_drug) > 60:
                    matched_drug_formatted = matched_drug[:60] + "..."

                task_name = f"{category}\n{matched_drug_formatted}"

                # 处理日期
                start_date = treatment.get("date")
                end_date = treatment.get("end_date")

                # 如果没有结束日期，按单天处理（开始日期+1天）
                if not end_date and start_date:
                    from datetime import datetime, timedelta
                    try:
                        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                        end_dt = start_dt + timedelta(days=1)
                        end_date = end_dt.strftime("%Y-%m-%d")
                        logger.debug(f"治疗 '{matched_drug}' 只有开始日期，按单天处理（+1天）")
                    except:
                        # 如果日期解析失败，使用开始日期
                        end_date = start_date

                # 如果开始日期和结束日期相同，强制结束日期+1天（防止甘特图条太细）
                if start_date and end_date and start_date == end_date:
                    from datetime import datetime, timedelta
                    try:
                        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
                        end_dt = start_dt + timedelta(days=1)
                        end_date = end_dt.strftime("%Y-%m-%d")
                        logger.debug(f"治疗 '{matched_drug}' 开始和结束日期相同，自动调整结束日期（+1天）")
                    except Exception as e:
                        logger.warning(f"调整相同日期失败: {e}")
                        pass

                # 处理剂量标签（优先使用LLM生成的dosage_label）
                dosage_label = treatment.get("dosage_label", "")  # 优先使用LLM生成的简化标签

                # 如果LLM没有生成dosage_label，使用后处理逻辑（降级方案）
                if not dosage_label and treatment.get("dosage"):
                    import re
                    dosage_text = treatment['dosage']

                    # 解析剂量信息：提取"药名+剂量"的模式
                    # 匹配模式如：阿替利珠单抗1200mg、贝伐珠单抗700mg
                    drug_dosage_pattern = r'([^\d\+]+?)(\d+\.?\d*\s*(?:mg|g|ml|μg|ug|片|粒|支|次|IU|U))'
                    matches = re.findall(drug_dosage_pattern, dosage_text)

                    if matches:
                        # 如果只有一种药物，只显示剂量
                        if len(matches) == 1:
                            dosage_label = matches[0][1]  # 只显示剂量部分
                        else:
                            # 联合用药：提取所有药名首字
                            drug_names = [m[0].strip() for m in matches]
                            dosages = [m[1] for m in matches]

                            # 检查是否有首字冲突
                            first_chars = [name[0] if name else '' for name in drug_names]

                            # 构建简化标签
                            simplified_parts = []
                            for i, (name, dosage) in enumerate(zip(drug_names, dosages)):
                                if not name:
                                    simplified_parts.append(dosage)
                                    continue

                                # 检查当前药名的首字是否与其他药名冲突
                                first_char = name[0]
                                has_conflict = sum(1 for c in first_chars if c == first_char) > 1

                                # 如果有冲突，使用前两字；否则使用首字
                                if has_conflict and len(name) >= 2:
                                    simplified_parts.append(f"{name[:2]}{dosage}")
                                else:
                                    simplified_parts.append(f"{first_char}{dosage}")

                            dosage_label = '+'.join(simplified_parts)
                    else:
                        # 如果无法解析，尝试只提取数字+单位
                        dosage_matches = re.findall(r'\d+\.?\d*\s*(?:mg|g|ml|μg|ug|片|粒|支|次|IU|U)', dosage_text)
                        if dosage_matches:
                            # 如果只有一个剂量，直接显示
                            if len(dosage_matches) == 1:
                                dosage_label = dosage_matches[0]
                            else:
                                # 多个剂量，用+连接
                                dosage_label = '+'.join(dosage_matches)
                        else:
                            # 降级方案：截断显示
                            dosage_label = dosage_text[:30] + "..." if len(dosage_text) > 30 else dosage_text

                gantt_item = {
                    "id": f"treatment_{idx}",
                    "task_name": task_name,
                    "start_date": start_date,
                    "end_date": end_date,
                    "dosage_label": dosage_label,
                    "category": category,
                    "treatment_type": treatment_type,
                    "methods_drugs": matched_drug,  # 使用matched_drug作为methods_drugs
                    "matched_drug": matched_drug,
                    "raw_treatment_text": treatment["treatment_text"],
                    "source_file": treatment.get("source_file", "")  # 新增：来源文件
                }

                gantt_data.append(gantt_item)

            except Exception as e:
                logger.error(f"处理治疗数据项失败: {e}, 数据: {treatment}")
                continue

        # 排序：按治疗类别顺序（配置文件顺序）+ 日期顺序
        gantt_data_sorted = sorted(
            gantt_data,
            key=lambda x: (
                self._get_category_order(x.get("category", "其他治疗")),  # 首先按类别顺序
                x.get("start_date", "9999-99-99")  # 其次按开始日期
            )
        )

        # 统计治疗类别分布
        category_counts = {}
        for item in gantt_data_sorted:
            category = item.get("category", "其他治疗")
            category_counts[category] = category_counts.get(category, 0) + 1

        logger.info(f"治疗数据处理完成: 共 {len(gantt_data_sorted)} 条记录")
        logger.info(f"类别分布: {category_counts}")
        return gantt_data_sorted


def process_patient_treatments_for_gantt(patient_data: Any, config_path: str = "./app/config/treatment_config.xlsx") -> List[Dict[str, Any]]:
    """
    便捷函数：处理患者治疗数据生成甘特图数据

    Args:
        patient_data: 患者数据
        config_path: 治疗配置文件路径

    Returns:
        甘特图数据列表
    """
    processor = TreatmentDataProcessor(config_path)
    return processor.process_patient_treatments(patient_data)
