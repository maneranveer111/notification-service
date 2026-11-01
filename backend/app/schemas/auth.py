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


class WorkspaceInfo(BaseModel):
    id: UUID
    name: str
    slug: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserAuthInfo
    workspace: WorkspaceInfo | None = None
    is_superadmin: bool = False


class AuthMeResponse(BaseModel):
    id: UUID | None = None
    email: str | None = None
    role: str
    can_write: bool
    is_admin: bool
    is_superadmin: bool = False
    workspace: WorkspaceInfo | None = None
    workspaces: list[WorkspaceInfo] = []

    model_config = ConfigDict(from_attributes=True)
