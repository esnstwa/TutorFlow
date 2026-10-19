# ПЗ №2 — фактические доказательства Ксении Ивановой

Дата локальной проверки: **19 октября 2026 года**.

## Состояние версии

- Worktree: `tutorflow-pz02-auth-contract-20261019`.
- Ветка: `feature/0104-pz02-ksenia`.
- База: `origin/main` = `3a3f23e2743b4798b9402fa3cc7c298c3a9d834c`.
- Commit для сдачи пока не создан; `HEAD` совпадает с базой, рабочие изменения незафиксированы намеренно.
- PR, push, merge и tag по ПЗ №2 не выполнялись.

## Реализация

- Новый контракт и production-реализация: `app/auth/passwords.py`.
- Потребитель: `app/auth/router.py:login` получает `PasswordVerifier` через `Depends(get_password_verifier)`.
- Совместимый фасад: `app/core/security.py:verify_password` делегирует production-провайдеру.
- Тестовая подмена: `tests/support/passwords.py:FixedPasswordVerifier`.
- Общая модульная карта дополнена в `docs/architecture.md`.
- Контракт, ADR и протокол проверки находятся в `docs/mdk01.04/pz02/`.

## Результаты команд

```text
D:/TutorFlow/.venv/Scripts/python.exe -m pytest tests/test_auth_module_contract.py -q
7 passed, 2 warnings

D:/TutorFlow/.venv/Scripts/python.exe -m pytest tests/test_auth_module_contract.py tests/test_auth_sessions.py tests/test_auth_integration.py tests/test_registration_validation.py tests/test_users_service.py -q
100 passed, 2 warnings in 6.30s

D:/TutorFlow/.venv/Scripts/python.exe -m pytest -q
292 passed, 2 warnings in 25.71s

D:/TutorFlow/.venv/Scripts/python.exe -m compileall -q app scripts tests
exit code: 0

node --test tests/auth-wizard.test.cjs tests/student-lifecycle.test.cjs
34 passed, 0 failed

node tests/test_session_fetch.cjs
6 session fetch checks passed

git diff --check
exit code: 0
```

Warnings are the pre-existing Starlette/httpx and anyio deprecation warnings emitted by the installed test stack; no test failed. The added regression test uses a non-ASCII malformed stored hash and confirms both `False` at the module boundary and generic HTTP 401 without session/cookie.

## R1–R8 status

| Требование | Фактический статус | Доказательство |
|---|---|---|
| Р1 | готово локально | `CONTRACT.md`: AUTH-LOGIN-01 → password comparison → `verify` → `login`; внешние обязанности отделены |
| Р2 | готово локально | Protocol/docstrings in `app/auth/passwords.py`; вход, результат, ошибки, порядок, владение и эффекты перечислены |
| Р3 | готово локально | `Argon2PasswordVerifier`, DI в `login`, 100 focused tests and existing auth path |
| Р4 | готово локально | same login consumer parametrized with `Argon2PasswordVerifier` and `FixedPasswordVerifier`; consumer source unchanged |
| Р5 | готово локально | factual dependency table in `docs/architecture.md`, checked against imports |
| Р6 | готово локально | 7 contract tests for both implementations + 100 focused auth tests |
| Р7 | не выполнено | independent student review has not happened; only `REVIEW_PROTOCOL.md` prepared |
| Р8 | готово локально | two complexity directions, reproducible candidate and own `ADR-002.md` |

## Ограничения

- Тестовая подмена не подтверждает исправность Argon2, БД, cookie, CSRF или PostgreSQL; это прямо указано в отчёте.
- Отсутствие R7 нельзя заменить авторской проверкой или зелёным CI.
- CI для ПЗ №2 не существует до push/PR; публикация сознательно отложена по заданию пользователя.
- Для сдачи после ревью потребуется зафиксировать рабочее дерево commit-ом и создать неизменяемый tag вида `0104-pz02-<код>-v1`; сейчас tag не создавался.
