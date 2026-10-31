from uuid import UUID
from pydantic import BaseModel, ConfigDict, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserAuthInfo(BaseModel):
    id: UUID
    email: str
    role: str

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserAuthInfo


class AuthMeResponse(BaseModel):
    id: UUID | None = None
    email: str | None = None
    role: str
    can_write: bool
    is_admin: bool

    model_config = ConfigDict(from_attributes=True)
