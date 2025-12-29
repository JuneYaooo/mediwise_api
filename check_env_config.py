#!/usr/bin/env python3
"""
环境配置检查脚本
检查 JWT 相关的环境变量是否正确配置
"""
import os
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

def check_env_config():
    """检查环境配置"""
    print("=" * 60)
    print("环境配置检查")
    print("=" * 60)

    # 检查 JWT_SECRET_KEY
    jwt_secret_key = os.getenv("JWT_SECRET_KEY", "")
    jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")

    print("\n1. JWT 外部验证配置:")
    if jwt_secret_key:
        print(f"   ✅ JWT_SECRET_KEY: 已配置 (长度: {len(jwt_secret_key)} 字符)")
    else:
        print(f"   ❌ JWT_SECRET_KEY: 未配置")
        print(f"      请在 .env 文件中添加:")
        print(f"      JWT_SECRET_KEY=your_jwt_secret_key_here")

    print(f"   ℹ️  JWT_ALGORITHM: {jwt_algorithm}")

    # 检查其他必要配置
    print("\n2. 数据库配置:")
    db_host = os.getenv("POSTGRES_HOST", "")
    db_user = os.getenv("POSTGRES_USER", "")
    db_name = os.getenv("POSTGRES_DATABASE", "")

    if db_host and db_user and db_name:
        print(f"   ✅ 数据库配置完整")
        print(f"      主机: {db_host}")
        print(f"      用户: {db_user}")
        print(f"      数据库: {db_name}")
    else:
        print(f"   ⚠️  数据库配置不完整")

    # 总结
    print("\n" + "=" * 60)
    if jwt_secret_key:
        print("✅ 环境配置检查通过")
        return True
    else:
        print("❌ 环境配置检查失败：JWT_SECRET_KEY 未配置")
        return False

if __name__ == "__main__":
    success = check_env_config()
    sys.exit(0 if success else 1)
