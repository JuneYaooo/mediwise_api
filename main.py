from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.routers import patient_data_processing, patient_ppt, patient_chat
from app.db.database import engine, Base

# Create database tables
# 注释掉自动创建表：数据库表已存在，且旧模型定义可能与实际表结构不匹配
# Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="MediWise API",
    description="患者数据处理和PPT生成API服务",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(
    patient_data_processing.router,
    prefix="/api/patient_data",
    tags=["patient_data"]
)

app.include_router(
    patient_ppt.router,
    prefix="/api",
    tags=["patient_ppt"]
)

# 患者对话聊天接口 - 基于 patient_id 的多轮对话
app.include_router(
    patient_chat.router,
    prefix="/api/patients",
    tags=["patient_chat"]
)


@app.get("/")
def root():
    return {
        "message": "MediWise API Service",
        "version": "1.0.0",
        "endpoints": {
            "patient_data_processing": "/api/patient_data/process_patient_data_smart",
            "patient_data_task_status": "/api/patient_data/task_status/{task_id}",
            "patient_ppt_generate": "/api/patients/{patient_id}/generate_ppt",
            "patient_ppt_data": "/api/patients/{patient_id}/ppt_data",
            "patient_chat": "/api/patients/{patient_id}/chat"
        }
    }


@app.get("/health")
def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=9527,
        reload=True,
        workers=5
    )
