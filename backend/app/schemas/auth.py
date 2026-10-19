from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.security import MAX_PASSWORD_BYTES, validate_password_bytes


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    # P1-E 修复：max_length 与 validate_password_bytes 的 72 字节限制保持一致
    # （ASCII 字符 1 字节/字符，中文 3 字节/字符；max_length 按字符数限制）
    password: str = Field(min_length=8, max_length=MAX_PASSWORD_BYTES)

    @field_validator("password")
    @classmethod
    def check_password_bytes(cls, v: str) -> str:
        validate_password_bytes(v)
        return v


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_BYTES)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=2048)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=MAX_PASSWORD_BYTES)
    new_password: str = Field(min_length=8, max_length=MAX_PASSWORD_BYTES)

    @field_validator("new_password")
    @classmethod
    def check_password_bytes(cls, v: str) -> str:
        validate_password_bytes(v)
        return v


class RequestPasswordResetRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    new_password: str = Field(min_length=8, max_length=MAX_PASSWORD_BYTES)
    reset_token: str = Field(min_length=32, max_length=2048)

    @field_validator("new_password")
    @classmethod
    def check_password_bytes(cls, v: str) -> str:
        validate_password_bytes(v)
        return v


class UpdateProfileRequest(BaseModel):
    nickname: str | None = Field(default=None, min_length=1, max_length=50)
    email: EmailStr | None = None


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    nickname: str | None = None


class RegisterResponse(BaseModel):
    id: int
    username: str


class TokenResponse(BaseModel):
    """``/auth/refresh`` 的响应体（**只含** access token）。

    M1 修复（ROUND_18）：原模型带 ``refresh_token``，端点 ``return ok(tokens)``
    会把轮换后的长效令牌明文回传，抵消 httpOnly Cookie 的保护 —— 任何 XSS 只需
    ``fetch('/auth/refresh', {credentials:'include'})`` 即可拿到它并外带。
    现模型层不再声明该字段：即便处理函数误传，FastAPI 的响应模型也会把它过滤掉
    （契约由结构保证，不依赖调用方自觉）。
    """

    access_token: str
    token_type: str = "bearer"


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    refresh_token: str | None = None
    user: UserBrief


class MessageResponse(BaseModel):
    message: str


class LogoutResponse(MessageResponse):
    revoked_count: int = 0


class ProfileResponse(BaseModel):
    id: int
    username: str
    email: EmailStr | None = None
    nickname: str | None = None
    role: str | None = None
