from typing import Any

from email_validator import EmailNotValidError, validate_email


def validated_fields(payload: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError('Некорректные данные')
    allowed = {'name', 'email', 'subject', 'grade', 'avatar'}
    if set(payload) - allowed:
        raise ValueError('Неизвестное или защищенное поле')
    if not partial and not {'name', 'email', 'subject', 'grade'} <= payload.keys():
        raise ValueError('Заполните имя, email, предмет и класс')
    result = {}
    for field, value in payload.items():
        if value is None and field in {'email', 'avatar'}:
            result[field] = None
            continue
        if not isinstance(value, str):
            raise ValueError('Поля ученика должны быть строками')
        value = value.strip()
        if field == 'name':
            parts = value.split(maxsplit=1)
            if not parts or any(len(part) > 100 for part in parts):
                raise ValueError('Имя и фамилия: не более 100 символов каждое')
            result['first_name'] = parts[0]
            result['last_name'] = parts[1] if len(parts) > 1 else ''
        elif field == 'email':
            if len(value) > 320:
                raise ValueError('Email слишком длинный')
            if value:
                try:
                    # Contact-only demo domains remain valid; real auth uses its own validators.
                    value = validate_email(value, check_deliverability=False, test_environment=True).normalized
                except EmailNotValidError as exc:
                    raise ValueError('Некорректный email') from exc
            result[field] = value or None
        else:
            maximum = {'subject': 120, 'grade': 50, 'avatar': 500}[field]
            if len(value) > maximum or (not value and field != 'avatar'):
                raise ValueError('Предмет, класс или аватар некорректны')
            result[field] = value or None
    return result
