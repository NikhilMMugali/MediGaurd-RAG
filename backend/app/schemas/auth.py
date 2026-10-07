from pydantic import BaseModel, Field

from app.models.user import RoleEnum


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=255)
    role: RoleEnum


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    full_name: str
    role: RoleEnum
    department: str | None = None


class CurrentUserResponse(BaseModel):
    username: str
    full_name: str
    role: RoleEnum
    department: str | None = None
