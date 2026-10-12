"""Synthetic registration data for Kseniya's PZ-02 test design.

This module contains data builders only. It does not define pytest fixtures,
HTTP clients, database setup, or production behavior.
"""

from __future__ import annotations

ROLE_TEACHER = "teacher"
ROLE_STUDENT = "student"
ROLE_UNKNOWN = "admin"

EMAIL_VALID = "kseniya.teacher@example.com"
EMAIL_DUPLICATE = " KSENIYA.TEACHER@EXAMPLE.COM "
EMAIL_INVALID = "kseniya.example.test"


def email_of_length(total_length: int) -> str:
    """Build a deterministic structurally valid-looking boundary address.

    The domain uses labels no longer than 63 characters. The application
    schema accepts lengths 253 and 254 and rejects 255; the product-level
    contract still needs to confirm whether this is the intended rule.
    """
    if total_length not in {253, 254, 255}:
        raise ValueError("Only the planned email boundary lengths are allowed")
    # 'a@' + three 63-char labels + three dots + final label.
    final_label_length = total_length - 194
    return "a@" + ".".join(
        ("a" * 63, "b" * 63, "c" * 63, "d" * final_label_length)
    )


EMAIL_BOUNDARIES = {
    253: email_of_length(253),
    254: email_of_length(254),
    255: email_of_length(255),
}

VALID_NAMES = {
    "length_2": "Ан",
    "length_30": "А" * 30,
    "hyphen": "Анна-Мария",
}

INVALID_NAMES = {
    "length_1": "А",
    "length_31": "А" * 31,
    "latin": "Anna",
    "hyphen_left_part_too_short": "А-Мя",
    "hyphen_right_part_empty": "Анна-",
    "leading_hyphen": "-Анна",
    "more_than_one_hyphen": "Анна-Мария-Ева",
}

PASSWORDS = {
    "length_7": "A1" + "b" * 5,
    "length_8": "A1" + "b" * 6,
    "length_128": "A1" + "b" * 126,
    "length_129": "A1" + "b" * 127,
    "without_letter": "12345678",
    "without_digit": "abcdefgh",
    "valid": "Example123",
}

CONFIRMATIONS = {
    "matching": PASSWORDS["valid"],
    "different": "Example124",
    "empty": "",
}

BASE_REGISTRATION = {
    "first_name": "Анна",
    "last_name": "",
    "email": EMAIL_VALID,
    "password": PASSWORDS["valid"],
    "password_confirmation": CONFIRMATIONS["matching"],
    "role": ROLE_TEACHER,
}

REGISTRATION_VARIANTS = {
    "teacher": {**BASE_REGISTRATION, "role": ROLE_TEACHER},
    "student": {
        **BASE_REGISTRATION,
        "email": "kseniya.student@example.com",
        "role": ROLE_STUDENT,
    },
    "missing_role": {key: value for key, value in BASE_REGISTRATION.items() if key != "role"},
    "unknown_role": {**BASE_REGISTRATION, "role": ROLE_UNKNOWN},
    "duplicate_email": {**BASE_REGISTRATION, "email": EMAIL_DUPLICATE},
    "invalid_email": {**BASE_REGISTRATION, "email": EMAIL_INVALID},
}

# These values are deliberately data-only. The 31-character name and the
# 253/254/255 email boundary must not receive an assertion until the contract
# owner confirms the intended product behavior.
CONTRACT_REQUIRES_CLARIFICATION = {
    "name_length_31": INVALID_NAMES["length_31"],
    "email_length_253": EMAIL_BOUNDARIES[253],
    "email_length_254": EMAIL_BOUNDARIES[254],
    "email_length_255": EMAIL_BOUNDARIES[255],
}
