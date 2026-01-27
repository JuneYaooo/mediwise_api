#!/usr/bin/env python3
"""
添加 disease_names 字段到 bus_patient 表
"""
import sys
import os

# 添加项目路径到 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db.database import engine
from sqlalchemy import text

def add_disease_names_field():
    """添加 disease_names 字段"""
    sql = """
    ALTER TABLE bus_patient
    ADD COLUMN IF NOT EXISTS disease_names VARCHAR(500) NULL;
    """

    try:
        with engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()
            print("✅ 成功添加 disease_names 字段到 bus_patient 表")

            # 验证字段是否添加成功
            verify_sql = """
            SELECT column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_name = 'bus_patient' AND column_name = 'disease_names';
            """
            result = conn.execute(text(verify_sql))
            row = result.fetchone()
            if row:
                print(f"✅ 验证成功: {row}")
            else:
                print("⚠️ 字段可能已存在或添加失败")

    except Exception as e:
        print(f"❌ 添加字段失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    add_disease_names_field()
