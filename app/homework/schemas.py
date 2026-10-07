from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class HomeworkCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=20_000)
    recipient_ids: list[int] = Field(min_length=1)
    attachment_ids: list[int] = Field(default_factory=list)
    due_at: datetime | None = None
    lesson_id: int | None = None

    @field_validator("title", "description", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("recipient_ids", "attachment_ids")
    @classmethod
    def unique_ids(cls, values: list[int]) -> list[int]:
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def content_is_required(self) -> "HomeworkCreate":
        if not self.description and not self.attachment_ids:
            raise ValueError("Добавьте описание или хотя бы один файл")
        return self


class HomeworkSubmissionCreate(BaseModel):
    comment: str = Field(default="", max_length=20_000)
    attachment_ids: list[int] = Field(default_factory=list)

    @field_validator("comment", mode="before")
    @classmethod
    def strip_comment(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("attachment_ids")
    @classmethod
    def unique_ids(cls, values: list[int]) -> list[int]:
        return list(dict.fromkeys(values))

    @model_validator(mode="after")
    def content_is_required(self) -> "HomeworkSubmissionCreate":
        if not self.comment and not self.attachment_ids:
            raise ValueError("Добавьте комментарий или хотя бы один файл")
        return self


class HomeworkReviewCreate(BaseModel):
    action: Literal["REVISION_REQUIRED", "COMPLETED"]
    teacher_comment: str = Field(default="", max_length=20_000)

    @field_validator("teacher_comment", mode="before")
    @classmethod
    def strip_comment(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value
