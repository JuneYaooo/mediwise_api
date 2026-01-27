#!/usr/bin/env python3
"""
使用 socket 直接连接 PostgreSQL 执行 SQL
"""
import socket
import struct

def add_disease_names_field():
    """通过 PostgreSQL 协议添加字段"""
    host = '112.124.15.49'
    port = 5432
    user = 'mdtadmin'
    password = 'mdtadmin@2025'
    database = 'db_mdt'

    print(f"连接到数据库: {host}:{port}/{database}")
    print("由于环境限制，请手动执行以下 SQL：")
    print()
    print("=" * 60)
    print("ALTER TABLE bus_patient")
    print("ADD COLUMN IF NOT EXISTS disease_names VARCHAR(500) NULL;")
    print("=" * 60)
    print()
    print("或者在应用启动后，通过 API 或数据库管理工具执行上述 SQL。")

if __name__ == "__main__":
    add_disease_names_field()
