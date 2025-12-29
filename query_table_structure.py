#!/usr/bin/env python3
"""直接查询数据库表结构和示例数据"""
import sys
sys.path.insert(0, '/home/ubuntu/github/mediwise_api')

from sqlalchemy import create_engine, text, inspect
from urllib.parse import quote_plus

# 数据库连接配置
POSTGRES_HOST = "112.124.15.49"
POSTGRES_PORT = "5432"
POSTGRES_USER = "mdtadmin"
POSTGRES_PASSWORD = quote_plus("mdtadmin@2025")
POSTGRES_DATABASE = "db_mdt"

DATABASE_URL = f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DATABASE}"

try:
    engine = create_engine(DATABASE_URL)

    with engine.connect() as conn:
        # 查询 bus_user_patient_access 表结构
        print("=" * 100)
        print("bus_user_patient_access 表结构:")
        print("=" * 100)
        result = conn.execute(text("""
            SELECT
                column_name,
                data_type,
                character_maximum_length,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_name = 'bus_user_patient_access'
            ORDER BY ordinal_position;
        """))

        rows = result.fetchall()
        if rows:
            print(f"{'列名':<30} {'数据类型':<20} {'长度':<10} {'允许NULL':<10} {'默认值':<30}")
            print("-" * 110)
            for row in rows:
                col_name, data_type, max_length, is_nullable, col_default = row
                length_str = str(max_length) if max_length else "-"
                default_str = str(col_default)[:30] if col_default else "-"
                print(f"{col_name:<30} {data_type:<20} {length_str:<10} {is_nullable:<10} {default_str:<30}")
        else:
            print("表不存在或无列信息")

        # 查询表中的示例数据
        print("\n" + "=" * 100)
        print("bus_user_patient_access 示例数据 (前3条):")
        print("=" * 100)
        result = conn.execute(text("SELECT * FROM bus_user_patient_access LIMIT 3;"))
        rows = result.fetchall()
        if rows:
            # 获取列名
            columns = result.keys()
            print(" | ".join([f"{col:<25}" for col in columns]))
            print("-" * 110)
            for row in rows:
                print(" | ".join([f"{str(val):<25}" for val in row]))
        else:
            print("表中无数据")

        # 查询 bus_patient_structured_data 的 created_by 字段
        print("\n" + "=" * 100)
        print("bus_patient_structured_data 表的 created_by 字段:")
        print("=" * 100)
        result = conn.execute(text("""
            SELECT
                column_name,
                data_type,
                character_maximum_length,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_name = 'bus_patient_structured_data'
              AND column_name = 'created_by'
            ORDER BY ordinal_position;
        """))

        rows = result.fetchall()
        if rows:
            print(f"{'列名':<30} {'数据类型':<20} {'长度':<10} {'允许NULL':<10} {'默认值':<30}")
            print("-" * 110)
            for row in rows:
                col_name, data_type, max_length, is_nullable, col_default = row
                length_str = str(max_length) if max_length else "-"
                default_str = str(col_default)[:30] if col_default else "-"
                print(f"{col_name:<30} {data_type:<20} {length_str:<10} {is_nullable:<10} {default_str:<30}")
        else:
            print("字段不存在")

except Exception as e:
    print(f"错误: {e}")
    import traceback
    traceback.print_exc()
