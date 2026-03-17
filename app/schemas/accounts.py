from pydantic import BaseModel, EmailStr, field_validator

from app.database import account_validators


class BaseLoginSchema(BaseModel):
    email: EmailStr
    password: str

    model_config = {
        "from_attributes": "True"
    }

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        return v.lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        return account_validators.validate_password_strength(v)


class UserRegistrationRequestSchema(BaseLoginSchema):
    pass


class ResetPasswordRequestSchema(BaseModel):
    email: EmailStr


class CompleteResetPasswordRequestSchema(BaseModel):
    token: str


class UserLoginSchema(BaseLoginSchema):
    pass


class UserLoginResponseSchema(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"


class UserRegistrationResponseSchema(BaseModel):
    id: int
    email: EmailStr

    model_config = {
        "from_attributes": "True"
    }


class UserActivationRequestSchema(BaseModel):
    email: EmailStr
    token: str


class MessageResponseSchema(BaseModel):
    message: str


class TokenRefreshRequestSchema(BaseModel):
    refresh_token: str


class TokenRefreshResponseSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"
