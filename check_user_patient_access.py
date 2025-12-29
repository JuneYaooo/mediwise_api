#!/usr/bin/env python3
"""查询 bus_user_patient_access 表结构"""
from app.db.database import engine
from sqlalchemy import text

def check_table_structure():
    """查询表结构"""
    try:
        with engine.connect() as conn:
            # 查询 bus_user_patient_access 表结构
            print("=" * 80)
            print("bus_user_patient_access 表结构:")
            print("=" * 80)
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
                print(f"{'列名':<30} {'数据类型':<20} {'长度':<10} {'允许NULL':<10} {'默认值':<20}")
                print("-" * 100)
                for row in rows:
                    col_name, data_type, max_length, is_nullable, col_default = row
                    length_str = str(max_length) if max_length else "-"
                    default_str = str(col_default)[:20] if col_default else "-"
                    print(f"{col_name:<30} {data_type:<20} {length_str:<10} {is_nullable:<10} {default_str:<20}")
            else:
                print("表不存在或无列信息")

            print("\n" + "=" * 80)
            print("bus_patient_structured_data 表的 created_by 字段:")
            print("=" * 80)
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
                print(f"{'列名':<30} {'数据类型':<20} {'长度':<10} {'允许NULL':<10} {'默认值':<20}")
                print("-" * 100)
                for row in rows:
                    col_name, data_type, max_length, is_nullable, col_default = row
                    length_str = str(max_length) if max_length else "-"
                    default_str = str(col_default)[:20] if col_default else "-"
                    print(f"{col_name:<30} {data_type:<20} {length_str:<10} {is_nullable:<10} {default_str:<20}")

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_table_structure()
