"""
使用大模型提取患者治疗数据的工具
从患者的结构化数据中智能提取治疗信息
"""

import json
from typing import Any, List, Dict, Optional
from src.llms import general_llm
from src.utils.logger import BeijingLogger

logger = BeijingLogger().get_logger()


class TreatmentExtractorLLM:
    """使用大模型提取治疗数据"""

    def __init__(self, treatment_config: Optional[List[Dict[str, Any]]] = None):
        self.llm = general_llm
        self.treatment_config = treatment_config or []

    def extract_treatments(self, patient_data: Any, chunk_size: int = 50000) -> List[Dict[str, Any]]:
        """
        使用大模型从患者数据中提取治疗信息

        Args:
            patient_data: 患者数据（可以是dict、list或str）
            chunk_size: 每次处理的数据块大小（字符数）

        Returns:
            治疗数据列表，格式：
            [
                {
                    "date": "YYYY-MM-DD",
                    "end_date": "YYYY-MM-DD" (可选),
                    "treatment_text": "治疗描述",
                    "dosage": "剂量信息",
                    "duration": "治疗时长",
                    "category": "治疗类别",
                    "treatment_type": "具体治疗方式",
                    "matched_drug": "匹配到的具体药物名",
                    "source_file": "来源文件名或ID"
                }
            ]
        """
        try:
            # 处理数据格式
            if isinstance(patient_data, str):
                try:
                    # 尝试解析JSON字符串
                    patient_data = json.loads(patient_data)
                    logger.info("成功解析JSON字符串格式的患者数据")
                except:
                    logger.warning("患者数据是字符串但不是有效的JSON，将直接使用")

            # 将数据转换为字符串供LLM分析
            if isinstance(patient_data, (dict, list)):
                data_str = json.dumps(patient_data, ensure_ascii=False, indent=2)
            else:
                data_str = str(patient_data)

            logger.info(f"准备使用大模型提取治疗数据，总数据长度: {len(data_str)} 字符")

            # 如果数据超过chunk_size，则分块处理
            if len(data_str) > chunk_size:
                logger.info(f"患者数据过长({len(data_str)}字符)，将分块处理（每块{chunk_size}字符）")
                return self._extract_treatments_in_chunks(data_str, chunk_size)
            else:
                # 数据不长，直接处理
                return self._extract_from_single_chunk(data_str)

        except Exception as e:
            logger.error(f"使用大模型提取治疗数据失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _extract_from_single_chunk(self, data_str: str) -> List[Dict[str, Any]]:
        """
        从单个数据块中提取治疗信息

        Args:
            data_str: 患者数据字符串

        Returns:
            治疗数据列表
        """
        try:
            logger.info(f"处理单个数据块，长度: {len(data_str)} 字符")

            # 构建提示词
            prompt = self._build_extraction_prompt(data_str)

            # 打印完整的prompt用于调试
            logger.info(f"=== 发送给大模型的完整Prompt（前1000字符） ===\n{prompt[:1000]}\n... (总长度: {len(prompt)} 字符)")

            # 调用大模型
            logger.info("正在调用大模型提取治疗数据...")
            response = self.llm.call([{"role": "user", "content": prompt}])

            logger.info(f"大模型响应长度: {len(response)} 字符")
            logger.info(f"=== 大模型原始响应（完整） ===\n{response}\n=== 响应结束 ===")

            # 解析响应
            treatments = self._parse_llm_response(response)
            logger.info(f"从数据块中提取了 {len(treatments)} 条治疗记录")

            # 打印每条治疗记录的dosage_label字段
            for idx, t in enumerate(treatments):
                logger.info(f"  记录{idx+1}: dosage_label='{t.get('dosage_label', '')}', dosage='{t.get('dosage', '')}'")

            return treatments

        except Exception as e:
            logger.error(f"从数据块提取治疗信息失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _extract_treatment_texts_from_chunk(self, data_str: str) -> List[str]:
        """
        从数据块中提取治疗相关的文本描述（不需要结构化，只提取文本）

        Args:
            data_str: 患者数据字符串

        Returns:
            治疗文本描述列表
        """
        try:
            logger.debug(f"从数据块提取治疗文本，长度: {len(data_str)} 字符")

            # 简化的提示词：只提取文本描述
            prompt = f"""请从以下患者数据中识别所有涉及治疗的内容，只需要文本描述即可。

包括但不限于：
- 手术治疗
- 药物治疗（化疗、靶向、免疫等）
- 介入治疗
- 放射治疗
- 辅助支持治疗
- 其他治疗

请返回治疗相关的文本片段（每行一个），保留原始描述和上下文信息（如日期、剂量等）。

患者数据：
```
{data_str}
```

请只返回治疗相关的文本描述，每行一个，不需要JSON格式：
"""

            # 调用大模型
            response = self.llm.call([{"role": "user", "content": prompt}])

            # 解析响应（按行分割）
            treatment_texts = [
                line.strip()
                for line in response.strip().split('\n')
                if line.strip() and not line.strip().startswith('-') and len(line.strip()) > 10
            ]

            logger.debug(f"从数据块提取了 {len(treatment_texts)} 段治疗描述")
            return treatment_texts

        except Exception as e:
            logger.error(f"从数据块提取治疗文本失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _extract_treatments_in_chunks(self, data_str: str, chunk_size: int) -> List[Dict[str, Any]]:
        """
        将长数据分块处理，然后合并结果（支持并发处理）

        Args:
            data_str: 患者数据字符串
            chunk_size: 每块大小

        Returns:
            合并后的治疗数据列表
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        all_treatment_texts = []  # 只收集治疗文本描述

        # 智能分块：尝试在合适的位置分割（如换行、标点等）
        chunks = self._smart_split_data(data_str, chunk_size)

        logger.info(f"将数据分为 {len(chunks)} 块进行文本提取（最大5并发）")

        # 使用线程池并发处理，最大5个并发
        max_workers = min(5, len(chunks))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有任务，使用简化的文本提取
            future_to_chunk = {
                executor.submit(self._extract_treatment_texts_from_chunk, chunk): i
                for i, chunk in enumerate(chunks)
            }

            # 处理完成的任务
            for future in as_completed(future_to_chunk):
                chunk_idx = future_to_chunk[future]
                try:
                    chunk_texts = future.result()
                    logger.info(f"第 {chunk_idx+1}/{len(chunks)} 块提取了 {len(chunk_texts)} 段治疗描述")
                    all_treatment_texts.extend(chunk_texts)
                except Exception as e:
                    logger.error(f"处理第 {chunk_idx+1} 块时出错: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

        # 将所有治疗文本合并为一个整体文本
        logger.info(f"所有块共提取了 {len(all_treatment_texts)} 段治疗描述，使用大模型进行整体提取和整合...")
        combined_text = "\n\n".join(all_treatment_texts)

        # 打印合并后的文本内容以便调试
        logger.info(f"=== 合并后的治疗文本内容（用于最终提取） ===\n{combined_text}\n=== 内容结束 ===")

        # 使用大模型对整合后的文本进行最终提取（包含完整的分类、去重、整合）
        final_treatments = self._extract_from_single_chunk(combined_text)

        # 直接去重拼接，不使用大模型合并
        deduplicated = self._simple_deduplicate(final_treatments)
        logger.info(f"去重后得到 {len(deduplicated)} 条治疗记录")

        return deduplicated

    def _smart_split_data(self, data_str: str, chunk_size: int) -> List[str]:
        """
        智能分割数据，尽量在合适的位置分割

        Args:
            data_str: 数据字符串
            chunk_size: 目标块大小

        Returns:
            分割后的数据块列表
        """
        if len(data_str) <= chunk_size:
            return [data_str]

        chunks = []
        start = 0

        while start < len(data_str):
            # 确定当前块的结束位置
            end = start + chunk_size

            if end >= len(data_str):
                # 最后一块
                chunks.append(data_str[start:])
                break

            # 尝试在合适的位置分割（向后查找100个字符范围内的换行符）
            search_end = min(end + 100, len(data_str))
            split_pos = end

            # 优先在换行符处分割
            for i in range(end, search_end):
                if data_str[i] == '\n':
                    split_pos = i + 1
                    break
            else:
                # 如果没有换行符，尝试在标点符号处分割
                for i in range(end, search_end):
                    if data_str[i] in ',.;!?，。；！？、':
                        split_pos = i + 1
                        break

            chunks.append(data_str[start:split_pos])
            start = split_pos

        return chunks

    def _simple_deduplicate(self, treatments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        简单去重治疗记录（不使用大模型，直接去重拼接）

        Args:
            treatments: 治疗记录列表

        Returns:
            去重后的治疗记录列表
        """
        if not treatments:
            return []

        # 使用字典进行去重，key为 (date, treatment_text, category, treatment_type, matched_drug)
        unique_treatments = {}

        for treatment in treatments:
            date = treatment.get('date', '')
            treatment_text = treatment.get('treatment_text', '').strip()
            category = treatment.get('category', '')
            treatment_type = treatment.get('treatment_type', '')
            matched_drug = treatment.get('matched_drug', '').strip()
            source_file = treatment.get('source_file', '').strip()

            if not date or not treatment_text:
                continue

            # 创建唯一键：使用日期、治疗文本、分类、治疗类型、匹配药物
            key = (
                date,
                treatment_text.lower(),
                category,
                treatment_type,
                matched_drug.lower()
            )

            # 如果已存在，保留信息更完整的那个（优先保留有source_file的）
            if key in unique_treatments:
                existing = unique_treatments[key]
                # 比较信息完整度（有更多非空字段的保留）
                existing_fields = sum(1 for v in existing.values() if v)
                new_fields = sum(1 for v in treatment.values() if v)

                # 优先保留有source_file的记录
                if source_file and not existing.get('source_file'):
                    unique_treatments[key] = treatment
                elif new_fields > existing_fields:
                    unique_treatments[key] = treatment
            else:
                unique_treatments[key] = treatment

        # 按日期排序
        result = sorted(unique_treatments.values(), key=lambda x: x.get('date', ''))

        return result

    def _llm_merge_treatments(self, treatments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        使用大模型智能整合治疗记录

        主要功能：
        1. 合并重复或相似的治疗记录
        2. 整合同一疗程的不同描述
        3. 去除冗余信息，保留最完整准确的记录

        Args:
            treatments: 初步去重后的治疗记录列表

        Returns:
            整合后的治疗记录列表
        """
        try:
            # 将治疗列表转为JSON字符串
            treatments_json = json.dumps(treatments, ensure_ascii=False, indent=2)

            prompt = f"""请对以下治疗记录列表进行智能整合，要求：

1. **合并重复记录**：如果多条记录描述的是同一次治疗（日期相同或相近，治疗内容相似），请合并为一条记录
2. **整合相同治疗**：如果是相同治疗方案的不同描述（如"T+A方案"和"阿替利珠单抗+贝伐珠单抗"），请整合为一条，保留最详细的描述
3. **去除冗余**：去除信息重复或冗余的记录
4. **保留完整信息**：合并时保留所有有用信息（剂量、疗程等）

治疗记录列表：
```json
{treatments_json}
```

请返回整合后的治疗记录列表，格式与输入相同（JSON数组），只返回JSON，不要其他解释：
[
  {{
    "date": "YYYY-MM-DD",
    "end_date": "YYYY-MM-DD",
    "treatment_text": "治疗描述",
    "dosage": "剂量信息",
    "duration": "治疗时长"
  }},
  ...
]
"""

            logger.info("正在调用大模型整合治疗记录...")
            response = self.llm.call([{"role": "user", "content": prompt}])

            # 解析响应
            merged = self._parse_llm_response(response)

            if merged and len(merged) > 0:
                logger.info(f"大模型成功整合治疗记录: {len(treatments)} -> {len(merged)}")
                return merged
            else:
                logger.warning("大模型整合失败，返回原始记录")
                return treatments

        except Exception as e:
            logger.error(f"使用大模型整合治疗记录失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return treatments

    def _build_extraction_prompt(self, data_str: str) -> str:
        """
        构建提取治疗信息的提示词

        Args:
            data_str: 患者数据字符串

        Returns:
            提示词字符串
        """
        # 构建治疗分类配置表格
        treatment_config_table = ""
        fixed_combinations = []  # 固定搭配组合

        if self.treatment_config:
            treatment_config_table = "\n\n## 治疗分类配置表（请严格按此分类）\n\n"
            treatment_config_table += "| 治疗类别 | 具体治疗方式 | 常见方法/药物 |\n"
            treatment_config_table += "|---------|------------|-------------|\n"

            for config in self.treatment_config:
                category = config.get('category', '-')
                treatment_type = config.get('treatment_type', '-')
                methods_drugs = config.get('methods_drugs', '-')

                # 处理 NaN 和空值
                if str(treatment_type) in ['nan', 'NaN', 'None']:
                    treatment_type = '-'
                if str(methods_drugs) in ['nan', 'NaN', 'None', '-']:
                    methods_drugs = '-'

                treatment_config_table += f"| {category} | {treatment_type} | {methods_drugs} |\n"

                # 识别固定搭配（包含+号或多个药物的组合）
                if '+' in str(methods_drugs) or '（' in str(methods_drugs):
                    fixed_combinations.append({
                        'category': category,
                        'treatment_type': treatment_type,
                        'combination': methods_drugs
                    })

        # 构建固定搭配说明
        fixed_combo_note = ""
        if fixed_combinations:
            fixed_combo_note = "\n\n## 固定治疗组合（请识别并保持一致）\n\n"
            fixed_combo_note += "以下是固定搭配的治疗组合，出现时应归为同一类：\n"
            for combo in fixed_combinations:
                fixed_combo_note += f"- **{combo['combination']}** → {combo['category']} - {combo['treatment_type']}\n"
            fixed_combo_note += "\n**重要**：当识别到这些固定搭配时，应该：\n"
            fixed_combo_note += "1. 将组合中的药物归为同一治疗类型\n"
            fixed_combo_note += "2. 例如「阿替利珠单抗+贝伐珠单抗」应归为「靶免治疗」，而不是分别归类\n"
            fixed_combo_note += "3. matched_drug 字段应填写完整的组合名称，如「阿替利珠单抗+贝伐珠单抗」\n"

        prompt = f"""请从以下患者数据中提取所有治疗相关的信息，并按照配置表进行分类。

{treatment_config_table}
{fixed_combo_note}

**提取和分类规则：**

1. **提取治疗记录**：识别所有治疗活动（手术、药物、介入、放疗等）
2. **分类要求**：
   - 必须严格按照配置表中的分类进行归类
   - **优先识别固定搭配组合**（如 T+A、阿替利珠单抗+贝伐珠单抗等）
   - 对于固定搭配，整体归为一类，不要拆分
   - 如果没有匹配到固定搭配，再根据单个药物进行分类
   - 对于配置表中没有的治疗，归为"其他治疗 - 未分类"

3. **固定搭配识别规则**：
   - 「阿替利珠单抗+贝伐珠单抗」或「T+A」→ 系统治疗 - 靶免治疗（不要拆分为免疫和靶向）
   - 「信迪利单抗+贝伐珠单抗类似物」→ 系统治疗 - 靶免治疗
   - 「阿帕替尼+卡瑞利珠单抗」→ 系统治疗 - 靶免治疗
   - 「纳武利尤+伊匹木单抗」→ 系统治疗 - 靶免治疗（或根据配置表中的分类）
   - 如果不是配置表中的固定搭配，再按单个药物分别提取

4. **特别注意**：
   - TACE、TAE、HAIC → 局部治疗 - 经动脉介入治疗
   - 只有非固定搭配的组合药物才需要分别提取为多条记录

**对于每条治疗记录，请提取以下信息：**

```json
{{
  "date": "YYYY-MM-DD",  // 必填，治疗开始日期
  "end_date": "YYYY-MM-DD",  // 可选，治疗结束日期
  "treatment_text": "治疗的完整描述",  // 必填，保留原始描述
  "dosage": "剂量信息",  // 可选，如：阿替利珠单抗1200mg+贝伐珠单抗700mg
  "dosage_label": "剂量标签（简化格式）",  // 可选，用于甘特图显示的简化剂量标签
  "duration": "治疗时长",  // 可选，如：持续3周
  "category": "治疗类别",  // 必填，从配置表中选择
  "treatment_type": "具体治疗方式",  // 必填，从配置表中选择
  "matched_drug": "匹配到的具体药物名或组合名",  // 必填，固定搭配填组合名（如「阿替利珠单抗+贝伐珠单抗」）
  "source_file": "来源文件名或ID"  // 可选，如果数据中有来源文件信息，请提取
}}
```

**dosage_label 生成规则（重要！）：**
- **前提**：只有在 `dosage` 字段有值的情况下才生成 `dosage_label`
- **单药治疗**：只显示剂量，不显示药名。例如：`200mg`
- **联合用药（2-3种药物）**：使用药名首字+剂量，用`+`连接。例如：
  - 信迪利单抗200mg + 贝伐珠单抗1227mg → `信200mg+贝1227mg`
  - 阿替利珠单抗1200mg + 贝伐珠单抗700mg → `阿1200mg+贝700mg`
- **首字冲突处理**：如果多个药物首字相同，使用前两字区分。例如：
  - 阿替利珠单抗 + 阿帕替尼 → `阿替1200mg+阿帕300mg`
- **超过3种药物**：只显示"(共N种药物)"，不列举具体剂量
- **无剂量信息**：`dosage` 和 `dosage_label` 都留空 `""`

**重要提示：**
- 只提取有明确日期的治疗记录
- 日期格式必须是YYYY-MM-DD
- category、treatment_type、matched_drug 必须填写
- 优先识别固定搭配，固定搭配不要拆分
- matched_drug 对于固定搭配要填写完整组合名
- **dosage_label 必须严格按照上述规则生成**（单药只显示剂量，联合用药使用首字缩写）

患者数据：
```
{data_str}
```

请只返回JSON数组，不要包含其他解释文字：
[
  {{
    "date": "2023-01-15",
    "end_date": "2023-01-16",
    "treatment_text": "第1次TACE联合T+A方案（阿替利珠单抗+贝伐珠单抗）",
    "dosage": "阿替利珠单抗1200mg+贝伐珠单抗700mg",
    "dosage_label": "阿1200mg+贝700mg",
    "duration": "",
    "category": "系统治疗",
    "treatment_type": "靶免治疗",
    "matched_drug": "阿替利珠单抗+贝伐珠单抗",
    "source_file": "病历文件.pdf"
  }}
]

如果数据中没有任何带日期的治疗记录，请返回空数组：[]
"""
        return prompt

    def _parse_llm_response(self, response: str) -> List[Dict[str, Any]]:
        """
        解析大模型的响应

        Args:
            response: 大模型的响应文本

        Returns:
            治疗数据列表
        """
        try:
            # 清理响应文本
            response = response.strip()

            # 尝试提取JSON部分
            # 处理markdown代码块
            if "```json" in response:
                start = response.find("```json") + 7
                end = response.find("```", start)
                if end > start:
                    response = response[start:end].strip()
            elif "```" in response:
                start = response.find("```") + 3
                end = response.find("```", start)
                if end > start:
                    response = response[start:end].strip()

            # 尝试找到JSON数组的起始和结束
            if not response.startswith('['):
                start_idx = response.find('[')
                if start_idx >= 0:
                    response = response[start_idx:]

            if not response.endswith(']'):
                end_idx = response.rfind(']')
                if end_idx >= 0:
                    response = response[:end_idx + 1]

            # 解析JSON
            treatments = json.loads(response)

            if not isinstance(treatments, list):
                logger.warning(f"大模型返回的不是列表格式，而是: {type(treatments)}")
                return []

            # 验证和清理数据
            cleaned_treatments = []
            for idx, treatment in enumerate(treatments):
                if not isinstance(treatment, dict):
                    logger.warning(f"跳过第{idx}条记录：不是字典格式")
                    continue

                # 确保必需字段存在
                cleaned_treatment = {
                    "date": treatment.get("date", ""),
                    "end_date": treatment.get("end_date", ""),
                    "treatment_text": treatment.get("treatment_text", ""),
                    "dosage": treatment.get("dosage", ""),
                    "dosage_label": treatment.get("dosage_label", ""),  # 新增：LLM生成的简化剂量标签
                    "duration": treatment.get("duration", ""),
                    "category": treatment.get("category", "其他治疗"),
                    "treatment_type": treatment.get("treatment_type", "未分类"),
                    "matched_drug": treatment.get("matched_drug", treatment.get("treatment_text", "")),
                    "source_file": treatment.get("source_file", "")  # 新增：来源文件
                }

                # 至少要有治疗描述和日期
                if cleaned_treatment["treatment_text"] and cleaned_treatment["date"]:
                    cleaned_treatments.append(cleaned_treatment)
                else:
                    logger.warning(f"跳过第{idx}条记录：缺少必需字段（date或treatment_text）")

            return cleaned_treatments

        except json.JSONDecodeError as e:
            logger.error(f"解析大模型响应JSON失败: {e}")
            logger.error(f"响应内容: {response[:500]}")
            return []
        except Exception as e:
            logger.error(f"处理大模型响应时出错: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []


def extract_treatments_with_llm(patient_data: Any) -> List[Dict[str, Any]]:
    """
    便捷函数：使用大模型提取治疗数据

    Args:
        patient_data: 患者数据

    Returns:
        治疗数据列表
    """
    extractor = TreatmentExtractorLLM()
    return extractor.extract_treatments(patient_data)
