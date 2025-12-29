#!/usr/bin/env python3
"""查询 bus_user_patient_access 表是否存在及其结构"""
import sys
sys.path.insert(0, '/home/ubuntu/github/mediwise_api')

try:
    from sqlalchemy import create_engine, text, inspect
    from urllib.parse import quote_plus

    # 数据库连接配置
    POSTGRES_HOST = "112.124.15.49"
    POSTGRES_PORT = "5432"
    POSTGRES_USER = "mdtadmin"
    POSTGRES_PASSWORD = quote_plus("mdtadmin@2025")
    POSTGRES_DATABASE = "db_mdt"

    DATABASE_URL = f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DATABASE}"

    engine = create_engine(DATABASE_URL, echo=False)

    with engine.connect() as conn:
        # 检查表是否存在
        result = conn.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = 'bus_user_patient_access'
            );
        """))
        exists = result.scalar()

        if exists:
            print("✅ bus_user_patient_access 表已存在")
            print("\n表结构:")
            print("=" * 110)

            # 查询表结构
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
            print(f"{'列名':<30} {'数据类型':<20} {'长度':<10} {'允许NULL':<10} {'默认值':<30}")
            print("-" * 110)
            for row in rows:
                col_name, data_type, max_length, is_nullable, col_default = row
                length_str = str(max_length) if max_length else "-"
                default_str = str(col_default)[:30] if col_default else "-"
                print(f"{col_name:<30} {data_type:<20} {length_str:<10} {is_nullable:<10} {default_str:<30}")

            # 查询示例数据
            print("\n示例数据 (前3条):")
            print("=" * 110)
            result = conn.execute(text("SELECT * FROM bus_user_patient_access LIMIT 3;"))
            rows = result.fetchall()
            if rows:
                columns = result.keys()
                print(" | ".join([f"{col:<20}" for col in columns[:5]]))  # 只显示前5列
                print("-" * 110)
                for row in rows:
                    print(" | ".join([f"{str(val):<20}" for val in row[:5]]))
            else:
                print("表中暂无数据")
        else:
            print("❌ bus_user_patient_access 表不存在，需要创建")

except ImportError as e:
    print(f"导入错误: {e}")
    print("尝试使用系统 Python 和已安装的包")
except Exception as e:
    print(f"查询错误: {e}")
    import traceback
    traceback.print_exc()
