"""
医疗病例PPT模板定义
定义了各种医疗病例PPT页面模板的结构和Schema

字符长度建议：
- 标题：不超过20个字符
- 患者姓名：不超过10个字符
- 短文本字段（性别、年龄等）：不超过20个字符
- 中等文本字段（诊断名称、检查项目等）：不超过50个字符
- 长文本字段（病史、报告内容等）：不超过200个字符
- 表格单元格：不超过100个字符
"""

from typing import Dict, Any

# 医疗PPT模板定义
MEDICAL_PPT_TEMPLATES = {
    "medical": {
        "id": "medical",
        "name": "Medical Case Report",
        "description": "医疗病例报告PPT模板，包含病例信息、诊断、检查、治疗等页面",
        "slides": [
            {
                "id": "medical:patient-info-slide",
                "name": "Patient Basic Information",
                "description": "患者基本信息页面，展示姓名、性别、年龄、既往史、个人史、本次会诊目的",
                "json_schema": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "description": "页面标题",
                            "type": "string",
                            "default": "病例信息",
                            "maxLength": 20
                        },
                        "patient_name": {
                            "description": "患者姓名",
                            "type": "string",
                            "maxLength": 10
                        },
                        "gender": {
                            "description": "性别",
                            "type": "string",
                            "maxLength": 10
                        },
                        "age": {
                            "description": "年龄",
                            "type": "string",
                            "maxLength": 20
                        },
                        "medical_history": {
                            "description": "既往史",
                            "type": "string",
                            "maxLength": 200
                        },
                        "personal_history": {
                            "description": "个人史",
                            "type": "string",
                            "maxLength": 200
                        },
                        "consultation_purpose": {
                            "description": "本次会诊目的",
                            "type": "string",
                            "maxLength": 200
                        }
                    },
                    "required": ["patient_name"]
                }
            },
            {
                "id": "medical:diagnosis-list-slide",
                "name": "Diagnosis Information",
                "description": "诊断信息页面，列表展示诊断项目和时间",
                "json_schema": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "description": "页面标题",
                            "type": "string",
                            "default": "诊断信息",
                            "maxLength": 20
                        },
                        "diagnoses": {
                            "description": "诊断列表",
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "index": {
                                        "description": "序号",
                                        "type": "integer"
                                    },
                                    "diagnosis": {
                                        "description": "诊断名称",
                                        "type": "string",
                                        "maxLength": 100
                                    },
                                    "diagnosis_time": {
                                        "description": "诊断时间",
                                        "type": "string",
                                        "maxLength": 30
                                    }
                                },
                                "required": ["diagnosis"]
                            }
                        }
                    },
                    "required": ["diagnoses"]
                }
            },
            {
                "id": "medical:lab-test-table-slide",
                "name": "Laboratory Test Results",
                "description": "实验室检查结果表格页面",
                "json_schema": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "description": "页面标题",
                            "type": "string",
                            "default": "实验室检查",
                            "maxLength": 20
                        },
                        "table_data": {
                            "description": "表格数据，每个单元格内容建议不超过100字符",
                            "type": "object",
                            "properties": {
                                "headers": {
                                    "description": "表头",
                                    "type": "array",
                                    "items": {"type": "string", "maxLength": 30},
                                    "default": ["检查项目", "开单时间", "项目名称", "结果", "报告时间"]
                                },
                                "rows": {
                                    "description": "表格行数据",
                                    "type": "array",
                                    "items": {
                                        "type": "array",
                                        "items": {"type": "string"}
                                    }
                                }
                            },
                            "required": ["rows"]
                        }
                    },
                    "required": ["table_data"]
                }
            },
            {
                "id": "medical:metric-trends-slide",
                "name": "Key Metrics Trends",
                "description": "关键指标变动趋势图页面，展示多个指标的时间序列变化",
                "json_schema": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "description": "页面标题",
                            "type": "string",
                            "default": "关键指标变动趋势",
                            "maxLength": 20
                        },
                        "metrics": {
                            "description": "指标数据列表，建议不超过3个指标以保持清晰",
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {
                                        "description": "指标名称",
                                        "type": "string",
                                        "maxLength": 30
                                    },
                                    "unit": {
                                        "description": "单位",
                                        "type": "string",
                                        "maxLength": 20
                                    },
                                    "normal_range": {
                                        "description": "正常范围",
                                        "type": "string",
                                        "maxLength": 30
                                    },
                                    "data_points": {
                                        "description": "数据点列表",
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "date": {
                                                    "description": "日期",
                                                    "type": "string",
                                                    "maxLength": 20
                                                },
                                                "value": {
                                                    "description": "数值",
                                                    "type": "number"
                                                }
                                            },
                                            "required": ["date", "value"]
                                        }
                                    }
                                },
                                "required": ["name", "data_points"]
                            }
                        }
                    },
                    "required": ["metrics"]
                }
            },
            {
                "id": "medical:imaging-table-slide",
                "name": "Imaging Examination Table",
                "description": "影像学检查表格页面",
                "json_schema": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "description": "页面标题",
                            "type": "string",
                            "default": "影像学检查",
                            "maxLength": 20
                        },
                        "table_data": {
                            "description": "表格数据，每个单元格内容建议不超过100字符",
                            "type": "object",
                            "properties": {
                                "headers": {
                                    "description": "表头",
                                    "type": "array",
                                    "items": {"type": "string", "maxLength": 30},
                                    "default": ["检查项目", "报告内容", "检查时间"]
                                },
                                "rows": {
                                    "description": "表格行数据",
                                    "type": "array",
                                    "items": {
                                        "type": "array",
                                        "items": {"type": "string"}
                                    }
                                }
                            },
                            "required": ["rows"]
                        },
                        "note": {
                            "description": "备注说明",
                            "type": "string",
                            "maxLength": 200
                        }
                    },
                    "required": ["table_data"]
                }
            },
            {
                "id": "medical:imaging-comparison-slide",
                "name": "Imaging Comparison",
                "description": "影像学对比页面，支持多张影像图片的对比展示",
                "json_schema": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "description": "页面标题",
                            "type": "string",
                            "default": "影像学检查",
                            "maxLength": 20
                        },
                        "subtitle": {
                            "description": "副标题说明",
                            "type": "string",
                            "maxLength": 50
                        },
                        "images": {
                            "description": "影像图片列表",
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "image_path": {
                                        "description": "图片路径",
                                        "type": "string"
                                    },
                                    "caption": {
                                        "description": "图片说明（如：影像图片-检查项目 检查时间）",
                                        "type": "string",
                                        "maxLength": 50
                                    }
                                },
                                "required": ["image_path"]
                            },
                            "minItems": 1,
                            "maxItems": 4
                        }
                    },
                    "required": ["images"]
                }
            },
            {
                "id": "medical:treatment-history-slide",
                "name": "Treatment History",
                "description": "治疗历史表格页面",
                "json_schema": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "description": "页面标题",
                            "type": "string",
                            "default": "治疗历史",
                            "maxLength": 20
                        },
                        "table_data": {
                            "description": "表格数据，每个单元格内容建议不超过100字符",
                            "type": "object",
                            "properties": {
                                "headers": {
                                    "description": "表头",
                                    "type": "array",
                                    "items": {"type": "string", "maxLength": 30},
                                    "default": ["治疗名称", "治疗记录", "开始时间", "结束时间"]
                                },
                                "rows": {
                                    "description": "表格行数据",
                                    "type": "array",
                                    "items": {
                                        "type": "array",
                                        "items": {"type": "string"}
                                    }
                                }
                            },
                            "required": ["rows"]
                        }
                    },
                    "required": ["table_data"]
                }
            },
            {
                "id": "medical:timeline-slide",
                "name": "Patient Disease Timeline",
                "description": "患者疾病旅程时间轴页面，展示关键时间节点",
                "json_schema": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "description": "页面标题",
                            "type": "string",
                            "default": "患者疾病旅程(汇总)",
                            "maxLength": 20
                        },
                        "timeline_image_path": {
                            "description": "时间轴图片路径（如果已有生成好的时间轴图片）",
                            "type": "string"
                        },
                        "events": {
                            "description": "时间线事件列表（如果需要自动生成时间轴）",
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "date": {
                                        "description": "事件日期",
                                        "type": "string",
                                        "maxLength": 30
                                    },
                                    "event": {
                                        "description": "事件描述",
                                        "type": "string",
                                        "maxLength": 100
                                    }
                                },
                                "required": ["date", "event"]
                            }
                        }
                    }
                }
            }
        ]
    }
}


def get_template_by_id(template_id: str) -> Dict[str, Any]:
    """
    根据模板ID获取模板信息
    
    Args:
        template_id: 模板ID
        
    Returns:
        模板信息字典
    """
    return MEDICAL_PPT_TEMPLATES.get(template_id)


def get_slide_schema(template_id: str, slide_id: str) -> Dict[str, Any]:
    """
    根据模板ID和幻灯片ID获取幻灯片schema
    
    Args:
        template_id: 模板ID
        slide_id: 幻灯片ID
        
    Returns:
        幻灯片schema字典
    """
    template = get_template_by_id(template_id)
    if not template:
        return None
    
    for slide in template.get("slides", []):
        if slide["id"] == slide_id:
            return slide
    
    return None


def list_available_templates() -> Dict[str, Any]:
    """
    列出所有可用的模板
    
    Returns:
        模板列表
    """
    return {
        "templates": [
            {
                "id": template_id,
                "name": template_data["name"],
                "description": template_data["description"],
                "slide_count": len(template_data["slides"])
            }
            for template_id, template_data in MEDICAL_PPT_TEMPLATES.items()
        ]
    }

