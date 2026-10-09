# Quality Gate v0

## Автоматический gate

Workflow `.github/workflows/quality-gate.yml` запускается на PR и push в `main` и обязан выполнить:

1. установку Python 3.12 и зависимостей `.[dev]`;
2. `python -m compileall -q app`;
3. полный `pytest`;
4. Node-тесты регистрации/авторизации/student lifecycle/session fetch;
5. PostgreSQL 16 service;
6. `alembic upgrade head`, проверку единственного head и `alembic check`.

Это реальные проверки проекта; шаги вида `echo success` отсутствуют.

## Ручной gate

- PR связан с issue и заполнен по шаблону.
- Изменение классифицировано как значимое/обычное.
- Для значимого изменения: 1 независимый approval и разрешённые замечания.
- Для UI: приложено доказательство наблюдаемого результата.
- Для schema/config/security: описаны риски и rollback/совместимость.

## Трассировка текущего значимого изменения

| Этап | Факт |
|---|---|
| Причина | В репозитории отсутствовали формализованные требования ПЗ №1, CI и шаблоны процесса. |
| Issue | [#4 — Подготовить ПЗ №1 МДК.03.02 и Quality Gate v0](https://github.com/esnstwa/TutorFlow/issues/4). |
| Branch | `codex/mdk-pz01-quality-gate`, создана от `43ce8a4`. |
| Changes | Документы ПЗ, GitHub templates, CODEOWNERS и настоящий workflow. |
| Commit | TODO после фиксации текущих изменений. |
| PR | TODO после push; должен содержать `Closes #4`. |
| Checks | Локально: compile — успешно; pytest — `184 passed`; Node.js — `40 passed`; чистая PostgreSQL 16 — `upgrade/current/check` успешно; GitHub Actions — TODO после запуска. |
| Review | TODO(external): запросить `@iver-ks`; review автора не засчитывать. |
| Merge | Запрещён до зелёного CI и независимого approval, потому что изменение значимое. |

## Ограничение enforcement

На 2026-10-09 запрос GitHub branch protection для приватного репозитория вернул `403` с требованием GitHub Pro либо публичного репозитория. Конкретное ручное действие владельца: **перевести репозиторий на тариф с branch protection или сделать его публичным, затем включить правила из `ENGINEERING_PROCESS.md` для `main`**.

Локальная PostgreSQL-проверка выполнялась в отдельном Compose-проекте и на новом томе. Существующий том основного проекта имеет неизвестную текущему репозиторию ревизию Alembic `20260916_0002`; он сохранён без изменений и не считается доказательством корректности актуальной цепочки миграций.
