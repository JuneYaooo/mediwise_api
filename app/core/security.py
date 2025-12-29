import bcrypt
from jose import jwt, JWTError
from datetime import datetime, timedelta
from typing import Optional, Any, Dict
import os
from dotenv import load_dotenv

from app.schemas.user import TokenData

# Load environment variables
load_dotenv()

# Security settings
SECRET_KEY = os.getenv("SECRET_KEY", "very-strong-secret-key-replace-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "2880"))  # 48 hours (2 days) by default

# Master token for special access (永久有效的万能Token)
MASTER_TOKEN = os.getenv("MASTER_TOKEN", "")

# JWT 验证密钥（用于外部系统的 token 验证）
# 支持 RS256 和 HS256 算法
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")  # 可以是 HS256 或 RS256


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash"""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a new access token"""
    to_encode = data.copy()
    expires = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expires})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[TokenData]:
    """Decode an access token and return the user ID if valid"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            return None
        token_data = TokenData(user_id=user_id)
        return token_data
    except JWTError:
        return None


def decode_external_token(token: str) -> Optional[Dict[str, Any]]:
    """
    解码外部系统的 JWT token（支持 HS256 和 RS256）

    Args:
        token: JWT token 字符串

    Returns:
        如果验证成功，返回 payload 字典，包含 user_id 等信息
        如果验证失败，返回 None
    """
    try:
        # 尝试使用配置的算法和密钥解码
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])

        # 提取 user_id（可能在 sub、user_id、userId 等字段中）
        user_id = payload.get("sub") or payload.get("user_id") or payload.get("userId")

        if user_id:
            return {
                "user_id": str(user_id),
                "payload": payload
            }
        return None
    except JWTError as e:
        # Token 验证失败
        return None


def is_master_token(token: str) -> bool:
    """
    验证是否为万能Token

    Args:
        token: 待验证的token字符串

    Returns:
        如果是有效的万能token则返回True，否则返回False
    """
    if not MASTER_TOKEN or not token:
        return False
    return token == MASTER_TOKEN 