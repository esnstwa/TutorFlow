"""PZ-02 tests owned by Kseniya for registration contracts.

These are schema-level tests. Existing auth integration/session tests cover the
already-proven persistence, cookie, CSRF, login/logout, and role-routing paths;
this file adds the missing boundary and malformed-input matrix without touching
shared fixtures or seed data.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.auth.schemas import RegisterRequest
from app.users.models import UserRole
from tests.data.registration_kseniya import (
    BASE_REGISTRATION,
    CONFIRMATIONS,
    EMAIL_BOUNDARIES,
    INVALID_NAMES,
    PASSWORDS,
    ROLE_STUDENT,
    ROLE_TEACHER,
    ROLE_UNKNOWN,
    VALID_NAMES,
)


def _payload(**changes: object) -> dict[str, object]:
    payload: dict[str, object] = dict(BASE_REGISTRATION)
    payload.update(changes)
    return payload


def _error_fields(error: ValidationError) -> set[str]:
    return {str(item["loc"][0]) for item in error.errors() if item["loc"]}


def _assert_invalid(payload: object, expected_field: str) -> None:
    with pytest.raises(ValidationError) as raised:
        RegisterRequest.model_validate(payload)

    assert expected_field in _error_fields(raised.value)


@pytest.mark.parametrize(
    ("role", "expected_role"),
    [
        pytest.param(ROLE_TEACHER, UserRole.TUTOR, id="TC-REG-01-teacher"),
        pytest.param(ROLE_STUDENT, UserRole.STUDENT, id="TC-REG-02-student"),
    ],
)
def test_reg_valid_roles_are_preserved(role: str, expected_role: UserRole) -> None:
    """FR-01 / TC-REG-01..02: both public roles form a valid request."""
    request = RegisterRequest.model_validate(_payload(role=role))

    assert request.role is expected_role
    assert request.email == BASE_REGISTRATION["email"]


@pytest.mark.parametrize(
    "role",
    [
        pytest.param(ROLE_UNKNOWN, id="TC-REG-03-unknown-role"),
        pytest.param(None, id="TC-REG-04-missing-role"),
    ],
)
def test_reg_invalid_or_missing_role_is_rejected(role: object) -> None:
    """FR-01 / TC-REG-03..04: only teacher/student are accepted."""
    payload = _payload(role=role)
    if role is None:
        payload.pop("role")

    _assert_invalid(payload, "role")


@pytest.mark.parametrize(
    ("name", "case_id"),
    [
        pytest.param(INVALID_NAMES["length_1"], "TC-REG-05", id="TC-REG-05-name-length-1"),
        pytest.param(VALID_NAMES["length_2"], "TC-REG-06", id="TC-REG-06-name-length-2"),
        pytest.param(VALID_NAMES["length_30"], "TC-REG-07", id="TC-REG-07-name-length-30"),
        pytest.param(INVALID_NAMES["length_31"], "TC-REG-08", id="TC-REG-08-name-length-31"),
    ],
)
def test_reg_name_length_boundary_matches_schema_contract(name: str, case_id: str) -> None:
    """TC-REG-05..08: check the backend 2..30 schema boundary.

    The 31-character case checks only RegisterRequest. It deliberately does not
    assert what the browser should do, because register.js currently truncates
    user input and the product UX contract is unresolved.
    """
    if len(name) in {2, 30}:
        request = RegisterRequest.model_validate(_payload(first_name=name))
        assert request.first_name == name
    else:
        _assert_invalid(_payload(first_name=name), "first_name")
    assert case_id.startswith("TC-REG-")


@pytest.mark.parametrize(
    "name",
    [
        pytest.param(VALID_NAMES["hyphen"], id="TC-REG-09-valid-hyphen"),
    ],
)
def test_reg_name_accepts_one_hyphen_between_nonempty_parts(name: str) -> None:
    """TC-REG-09: a single valid hyphenated Cyrillic name is accepted."""
    request = RegisterRequest.model_validate(_payload(first_name=name))

    assert request.first_name == name


@pytest.mark.parametrize(
    "name",
    [
        pytest.param(INVALID_NAMES["hyphen_left_part_too_short"], id="TC-REG-10-short-left-part"),
        pytest.param(INVALID_NAMES["hyphen_right_part_empty"], id="TC-REG-11-empty-right-part"),
        pytest.param(INVALID_NAMES["leading_hyphen"], id="TC-REG-12-leading-hyphen"),
        pytest.param(INVALID_NAMES["more_than_one_hyphen"], id="TC-REG-13-two-hyphens"),
        pytest.param(INVALID_NAMES["latin"], id="TC-REG-14-latin-name"),
    ],
)
def test_reg_invalid_name_alphabet_or_hyphen_shape_is_rejected(name: str) -> None:
    """TC-REG-10..14: invalid alphabet and hyphen classes fail validation."""
    _assert_invalid(_payload(first_name=name), "first_name")


@pytest.mark.parametrize(
    ("password", "is_valid"),
    [
        pytest.param(PASSWORDS["length_7"], False, id="TC-REG-15-password-length-7"),
        pytest.param(PASSWORDS["length_8"], True, id="TC-REG-16-password-length-8"),
        pytest.param(PASSWORDS["length_128"], True, id="TC-REG-17-password-length-128"),
        pytest.param(PASSWORDS["length_129"], False, id="TC-REG-18-password-length-129"),
    ],
)
def test_reg_password_length_boundary(password: str, is_valid: bool) -> None:
    """TC-REG-15..18: password length is 8..128 characters."""
    payload = _payload(password=password, password_confirmation=password)

    if is_valid:
        request = RegisterRequest.model_validate(payload)
        assert request.password == password
    else:
        _assert_invalid(payload, "password")


@pytest.mark.parametrize(
    "password",
    [
        pytest.param(PASSWORDS["without_letter"], id="TC-REG-19-no-letter"),
        pytest.param(PASSWORDS["without_digit"], id="TC-REG-20-no-digit"),
    ],
)
def test_reg_password_requires_letter_and_digit(password: str) -> None:
    """TC-REG-19..20: composition validator rejects incomplete passwords."""
    _assert_invalid(
        _payload(password=password, password_confirmation=password),
        "password",
    )


@pytest.mark.parametrize(
    ("confirmation", "is_valid"),
    [
        pytest.param(CONFIRMATIONS["matching"], True, id="TC-REG-21-confirmation-match"),
        pytest.param(CONFIRMATIONS["different"], False, id="TC-REG-22-confirmation-differs"),
        pytest.param(CONFIRMATIONS["empty"], False, id="TC-REG-23-confirmation-empty"),
    ],
)
def test_reg_password_confirmation_contract(confirmation: str, is_valid: bool) -> None:
    """TC-REG-21..23: confirmation must equal the password."""
    payload = _payload(password=PASSWORDS["valid"], password_confirmation=confirmation)

    if is_valid:
        request = RegisterRequest.model_validate(payload)
        assert request.password_confirmation == PASSWORDS["valid"]
    else:
        _assert_invalid(payload, "password_confirmation")


@pytest.mark.parametrize(
    ("email", "is_valid"),
    [
        pytest.param(EMAIL_BOUNDARIES[253], True, id="TC-REG-24-email-length-253"),
        pytest.param(EMAIL_BOUNDARIES[254], True, id="TC-REG-25-email-length-254"),
        pytest.param(EMAIL_BOUNDARIES[255], False, id="TC-REG-26-email-length-255"),
    ],
)
def test_reg_email_length_technical_schema_boundary(email: str, is_valid: bool) -> None:
    """TC-REG-24..26: verify EmailStr's technical 254-character boundary.

    PZ-01 does not define a separate product email-length requirement, so this
    test documents the current schema contract rather than inventing a new FR.
    """
    payload = _payload(email=email)

    if is_valid:
        request = RegisterRequest.model_validate(payload)
        assert str(request.email) == email
    else:
        _assert_invalid(payload, "email")


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(None, id="TC-REG-27-null-payload"),
        pytest.param([], id="TC-REG-28-array-payload"),
        pytest.param("registration", id="TC-REG-29-scalar-payload"),
        pytest.param({}, id="TC-REG-30-empty-object"),
        pytest.param({"first_name": "Анна"}, id="TC-REG-31-incomplete-object"),
    ],
)
def test_reg_non_object_or_incomplete_input_is_rejected(payload: object) -> None:
    """TC-REG-27..31: malformed structures cannot form a registration request."""
    with pytest.raises((ValidationError, TypeError)):
        RegisterRequest.model_validate(payload)
