#!/bin/bash
set -e

echo "=========================================="
echo "MediWise API Starting..."
echo "=========================================="

# 等待 Redis 可用
echo "⏳ Waiting for Redis..."
until redis-cli -h ${REDIS_HOST:-redis} -p ${REDIS_PORT:-36379} ping > /dev/null 2>&1; do
  echo "   Redis is unavailable - sleeping"
  sleep 2
done
echo "✅ Redis is up"

# 测试数据库连接
echo "⏳ Testing database connection..."
python3 << EOF
import sys
import psycopg2
import os
from urllib.parse import quote_plus

try:
    host = os.getenv('POSTGRES_HOST')
    port = os.getenv('POSTGRES_PORT', '5432')
    user = os.getenv('POSTGRES_USER')
    password = os.getenv('POSTGRES_PASSWORD')
    database = os.getenv('POSTGRES_DATABASE')

    conn = psycopg2.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        connect_timeout=10
    )
    conn.close()
    print("✅ Database connection successful")
except Exception as e:
    print(f"❌ Database connection failed: {e}")
    sys.exit(1)
EOF

if [ $? -ne 0 ]; then
    echo "❌ Database connection test failed. Exiting."
    exit 1
fi

# 创建必要的目录
mkdir -p /app/uploads /app/logs /app/output
echo "✅ Directories created"

echo "=========================================="
echo "🚀 Starting application..."
echo "=========================================="

# 执行传入的命令
exec "$@"
