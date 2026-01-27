#!/usr/bin/env python3
"""
添加 disease_names 字段到 bus_patient 表
"""
import os
import psycopg2
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def add_disease_names_field():
    """添加 disease_names 字段"""
    try:
        # 连接数据库
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST'),
            port=os.getenv('POSTGRES_PORT', '5432'),
            user=os.getenv('POSTGRES_USER'),
            password=os.getenv('POSTGRES_PASSWORD'),
            database=os.getenv('POSTGRES_DATABASE')
        )

        cursor = conn.cursor()

        # 添加字段
        sql = """
        ALTER TABLE bus_patient
        ADD COLUMN IF NOT EXISTS disease_names VARCHAR(500) NULL;
        """

        cursor.execute(sql)
        conn.commit()
        print("✅ 成功添加 disease_names 字段到 bus_patient 表")

        # 验证字段是否添加成功
        verify_sql = """
        SELECT column_name, data_type, character_maximum_length
        FROM information_schema.columns
        WHERE table_name = 'bus_patient' AND column_name = 'disease_names';
        """
        cursor.execute(verify_sql)
        row = cursor.fetchone()

        if row:
            print(f"✅ 验证成功: column_name={row[0]}, data_type={row[1]}, max_length={row[2]}")
        else:
            print("⚠️ 字段可能已存在或添加失败")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"❌ 添加字段失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    add_disease_names_field()
