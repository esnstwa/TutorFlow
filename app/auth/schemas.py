import re

from pydantic import BaseModel, EmailStr, Field, ValidationInfo, field_validator

from app.users.schemas import UserCreate


class RegisterRequest(UserCreate):
    first_name: str = Field(min_length=2, max_length=30)
    password_confirmation: str = Field(max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
            raise ValueError("Пароль должен содержать буквы и цифры")
        return value

    @field_validator("first_name")
    @classmethod
    def cyrillic_name(cls, value: str) -> str:
        if re.fullmatch(r"[А-Яа-яЁё]{2,30}(?:-[А-Яа-яЁё]{2,30})?", value) is None:
            raise ValueError("Имя: 2–30 символов кириллицы или дефис")
        return value

    @field_validator("password_confirmation")
    @classmethod
    def confirmation(cls, value: str, info: ValidationInfo) -> str:
        if value != info.data.get("password"):
            raise ValueError("Пароли не совпадают")
        return value


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    remember: bool = Field(default=False, strict=True)

    @field_validator("email", mode="before")
    @classmethod
    def trim_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


FIELD_MESSAGES = {
    "email": "Введите корректный email",
    "first_name": "Имя: 2–30 символов кириллицы или дефис",
    "last_name": "Фамилия: не более 100 символов",
    "password": "Пароль: 8–128 символов, хотя бы одна буква и цифра",
    "password_confirmation": "Подтвердите пароль: пароли должны совпадать",
    "role": "Выберите роль преподавателя или ученика",
    "remember": "Значение должно быть логическим",
}
