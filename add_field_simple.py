"""
简单的数据库字段添加脚本
"""
import sys
sys.path.insert(0, '/app')

from app.db.database import SessionLocal
from sqlalchemy import text

def add_field():
    """添加 disease_names 字段"""
    db = SessionLocal()
    try:
        sql = """
        ALTER TABLE bus_patient
        ADD COLUMN IF NOT EXISTS disease_names VARCHAR(500) NULL;
        """
        db.execute(text(sql))
        db.commit()
        print("✅ 成功添加 disease_names 字段")

        # 验证
        verify_sql = """
        SELECT column_name, data_type, character_maximum_length
        FROM information_schema.columns
        WHERE table_name = 'bus_patient' AND column_name = 'disease_names';
        """
        result = db.execute(text(verify_sql))
        row = result.fetchone()
        if row:
            print(f"✅ 验证成功: {row}")
        return True
    except Exception as e:
        print(f"❌ 失败: {e}")
        return False
    finally:
        db.close()

if __name__ == "__main__":
    success = add_field()
    sys.exit(0 if success else 1)
