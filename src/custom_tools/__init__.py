"""
Custom Tools for MediWise
"""

# 医疗PPT模板可以独立导入,不依赖其他模块
from src.custom_tools.medical_ppt_template import (
    MEDICAL_PPT_TEMPLATES,
    get_template_by_id,
    get_slide_schema,
    list_available_templates
)

# 医疗PPT生成工具需要 crewai_tools 和 python-pptx,按需导入
try:
    from src.custom_tools.medical_ppt_generation_tool import (
        MedicalPPTGenerationTool,
        MedicalPPTGenerationToolSchema
    )
    _HAS_PPT_TOOL = True
except ImportError:
    _HAS_PPT_TOOL = False
    MedicalPPTGenerationTool = None
    MedicalPPTGenerationToolSchema = None

# Suvalue PPT工具
try:
    from src.custom_tools.suvalue_ppt_template_tool import (
        SuvaluePPTTemplateTool,
        SuvaluePPTTemplateToolSchema
    )
    from src.custom_tools.suvalue_generate_ppt_tool import (
        SuvalueGeneratePPTTool,
        SuvalueGeneratePPTToolSchema
    )
    _HAS_SUVALUE_TOOLS = True
except ImportError:
    _HAS_SUVALUE_TOOLS = False
    SuvaluePPTTemplateTool = None
    SuvaluePPTTemplateToolSchema = None
    SuvalueGeneratePPTTool = None
    SuvalueGeneratePPTToolSchema = None

# 疾病配置工具
try:
    from src.custom_tools.get_disease_list_tool import (
        GetDiseaseListTool,
        get_disease_list_tool
    )
    from src.custom_tools.query_disease_config_tool import (
        QueryDiseaseConfigTool,
        query_disease_config_tool
    )
    _HAS_DISEASE_TOOLS = True
except ImportError:
    _HAS_DISEASE_TOOLS = False
    GetDiseaseListTool = None
    get_disease_list_tool = None
    QueryDiseaseConfigTool = None
    query_disease_config_tool = None

__all__ = [
    # Medical PPT Template
    'MEDICAL_PPT_TEMPLATES',
    'get_template_by_id',
    'get_slide_schema',
    'list_available_templates',

    # Medical PPT Generation Tool (可能为None)
    'MedicalPPTGenerationTool',
    'MedicalPPTGenerationToolSchema',

    # Suvalue PPT Tools
    'SuvaluePPTTemplateTool',
    'SuvaluePPTTemplateToolSchema',
    'SuvalueGeneratePPTTool',
    'SuvalueGeneratePPTToolSchema',

    # Disease Configuration Tools
    'GetDiseaseListTool',
    'get_disease_list_tool',
    'QueryDiseaseConfigTool',
    'query_disease_config_tool',
]

