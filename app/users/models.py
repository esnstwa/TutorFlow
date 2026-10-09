from enum import Enum

from app.models import User


class UserRole(str, Enum):
    """Public registration roles mapped to the canonical users table values."""

    TUTOR = "teacher"
    STUDENT = "student"


__all__ = ["User", "UserRole"]
