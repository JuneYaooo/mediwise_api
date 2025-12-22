from typing import List, Dict, Union, Optional
from datetime import datetime
from pydantic import BaseModel, Field

# 除了intent其他都是可选字段    
class IntentDeterminationSchema(BaseModel):
    intent: str  # 如"问诊"、"查看病历"、"开药"等
    query: Optional[str] = None  # 患者的问题
    symptoms: Optional[List[str]] = None  # 症状列表
    medical_history: Optional[Dict] = None  # 病史记录
    current_medications: Optional[List[str]] = None  # 当前用药
    need_emergency: Optional[bool] = None  # 是否需要紧急处理
    patient_info: Optional[str] = None  # 患者信息详细描述，包含患者，患者主诉之类的
    adr: Optional[List[str]] = None  # 不良反应列表
    disease: Optional[List[str]] = None  # 疾病列表
    drug: Optional[List[str]] = None  # 药物列表
    surgery: Optional[List[str]] = None  # 手术列表
    labtest: Optional[List[str]] = None  # 检验列表
    examine: Optional[List[str]] = None  # 检查列表
    drug_query: Optional[str] = None  # 药品查询
    user_requirement: Optional[str] = None  # 用户需要
    choose_functions: Optional[str] = None 

class DiagnosisSchema(BaseModel):
    diagnosis_code: str  # 诊断编码
    diagnosis_name: str  # 诊断名称
    diagnosis_description: Optional[str] = None  # 诊断描述
    severity: str  # 严重程度
    confidence: float  # 诊断置信度

class Doctor(BaseModel):
    doctor_id: str
    name: str
    title: str  # 职称
    department: str  # 科室
    specialty: List[str]  # 专长

class Patient(BaseModel):
    patient_id: str
    name: str
    age: int
    gender: str
    medical_history: Optional[List[Dict]] = None
    allergies: Optional[List[str]] = None
    current_medications: Optional[List[str]] = None

class MedicalRecord(BaseModel):
    record_id: str
    patient: Patient
    doctor: Doctor
    visit_date: datetime
    symptoms: List[str]
    diagnosis: List[DiagnosisSchema]
    treatment_plan: str
    prescriptions: Optional[List[Dict]] = None
    follow_up: Optional[str] = None

class ConsultationResultSchema(BaseModel):
    total_records: int
    medical_records: List[MedicalRecord]

class MedicalContentSchema(BaseModel):
    consultation_records: List[MedicalRecord]

class DiagnosisResponseSchema(BaseModel):
    reply: str  # 医生的诊断回复
    recommendations: List[str]  # 建议
    prescriptions: Optional[List[Dict]] = None  # 处方
    follow_up_plan: Optional[str] = None  # 随访计划

class TranslationSchema(BaseModel):
    translated_content: str  # 翻译后的医疗内容
