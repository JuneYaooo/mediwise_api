from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.routers import patient_data_processing, patient_extraction, patient_ppt
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
    patient_extraction.router,
    prefix="/api/conversations",
    tags=["conversations"]
)

app.include_router(
    patient_ppt.router,
    prefix="/api",
    tags=["patient_ppt"]
)


@app.get("/")
def root():
    return {
        "message": "MediWise API Service",
        "version": "1.0.0",
        "endpoints": {
            "patient_data_processing": "/api/patient_data",
            "patient_extraction": "/api/conversations",
            "patient_ppt": "/api/patients/{patient_id}/generate_ppt"
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
        reload=True
    )
