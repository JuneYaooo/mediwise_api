from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError, DisconnectionError
from typing import Generator, Optional
import time
import logging

from app.db.database import get_db
from app.core.security import decode_access_token, is_master_token
from app.models.user import User
import jwt

# Configure logging
logger = logging.getLogger(__name__)

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
) -> User:
    """Get the current authenticated user"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 检查是否为万能Token
    if is_master_token(token):
        # 使用万能Token时，返回一个默认的系统管理员用户
        # 查找ID为1的用户，或者第一个超级管理员用户
        admin_user = db.query(User).filter(User.is_superuser == True).first()
        if admin_user:
            logger.info(f"Master token used, authenticated as user: {admin_user.email}")
            return admin_user
        else:
            # 如果没有超级管理员，返回第一个用户
            first_user = db.query(User).first()
            if first_user:
                logger.warning(f"Master token used but no superuser found, using first user: {first_user.email}")
                return first_user
            else:
                logger.error("Master token used but no users exist in database")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="No users found in database"
                )

    # 常规Token验证流程
    # Decode token and get user_id
    token_data = decode_access_token(token)
    if token_data is None:
        raise credentials_exception

    # Get user from database with retry logic for connection issues
    max_retries = 3
    for attempt in range(max_retries):
        try:
            user = db.query(User).filter(User.id == token_data.user_id).first()
            break
        except (OperationalError, DisconnectionError) as e:
            logger.warning(f"Database connection error on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                logger.error("Max retries reached for database connection")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Database connection temporarily unavailable"
                )
            time.sleep(0.5 * (attempt + 1))  # Exponential backoff
            continue

    if user is None:
        raise credentials_exception

    # Check if user is active
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    return user


def get_current_active_superuser(
    current_user: User = Depends(get_current_user),
) -> User:
    """Get the current authenticated superuser"""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user


def get_optional_current_user(
    db: Session = Depends(get_db),
    token: Optional[str] = Depends(oauth2_scheme),
) -> Optional[User]:
    """Get the current user if authenticated, otherwise return None"""
    if token is None:
        return None

    # 检查是否为万能Token
    if is_master_token(token):
        # 使用万能Token时，返回一个默认的系统管理员用户
        admin_user = db.query(User).filter(User.is_superuser == True).first()
        if admin_user:
            logger.info(f"Master token used (optional), authenticated as user: {admin_user.email}")
            return admin_user
        else:
            # 如果没有超级管理员，返回第一个用户
            first_user = db.query(User).first()
            if first_user:
                logger.warning(f"Master token used (optional) but no superuser found, using first user: {first_user.email}")
                return first_user
            else:
                logger.error("Master token used (optional) but no users exist in database")
                return None

    # Try to decode token and get user_id
    token_data = decode_access_token(token)
    if token_data is None:
        return None

    # Get user from database with retry logic for connection issues
    max_retries = 3
    for attempt in range(max_retries):
        try:
            user = db.query(User).filter(User.id == token_data.user_id).first()
            break
        except (OperationalError, DisconnectionError) as e:
            logger.warning(f"Database connection error on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                logger.error("Max retries reached for database connection")
                return None  # Return None instead of raising exception for optional user
            time.sleep(0.5 * (attempt + 1))  # Exponential backoff
            continue

    if user is None or not user.is_active:
        return None

    return user 