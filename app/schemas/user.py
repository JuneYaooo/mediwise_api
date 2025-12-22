from pydantic import BaseModel, Field, EmailStr, validator, root_validator, model_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


class UserBase(BaseModel):
    phone: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool = True


class UserCreate(UserBase):
    password: str
    invitation_code: str
    
    @validator('phone')
    def phone_must_be_valid(cls, v):
        # Basic phone number validation - can be enhanced as needed
        if not v.isdigit() or len(v) < 10:
            raise ValueError('Invalid phone number format')
        return v


class UserLogin(BaseModel):
    phone: str
    credential: str  # Can be password or invitation code

    @validator('phone')
    def validate_phone(cls, v):
        # Validate phone number
        if not v.isdigit() or len(v) < 10:
            raise ValueError('Please provide a valid phone number')
        return v


class UserVerifyCode(BaseModel):
    phone: str
    invitation_code: str


class UserUpdate(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    password: Optional[str] = None


class UserInDB(UserBase):
    id: str
    is_superuser: bool = False
    created_at: datetime
    updated_at: datetime

    class Config:
        model_config = {
            "from_attributes": True
        }


class User(UserInDB):
    pass


class InvitationCodeBase(BaseModel):
    code: str
    expires_at: datetime


class InvitationCodeCreate(InvitationCodeBase):
    pass


class InvitationCodeInDB(InvitationCodeBase):
    id: str
    is_used: bool = False
    used_by: Optional[str] = None
    used_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        model_config = {
            "from_attributes": True
        }


class InvitationCode(InvitationCodeInDB):
    pass


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    user_id: Optional[str] = None


class UnifiedAuth(BaseModel):
    phone: str
    pass_code: str  # Can be either password or invitation code

    @validator('phone')
    def validate_phone(cls, v):
        # Validate phone number
        if not v.isdigit() or len(v) < 10:
            raise ValueError('Please provide a valid phone number')
        return v


class TokenPayload(BaseModel):
    sub: Optional[str] = None
    exp: Optional[int] = None


class UnifiedAuthResponse(BaseModel):
    access_token: str
    token_type: str
    is_new_user: bool
    user_info: User 