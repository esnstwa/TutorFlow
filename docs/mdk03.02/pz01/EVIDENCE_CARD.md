# Карточка доказательств

| Поле | Значение |
|---|---|
| Дисциплина | МДК.03.02 «Формирование требований и регламента инженерного процесса проекта» |
| Работа | ПЗ №1 |
| Проект | TutorFlow |
| Репозиторий | `esnstwa/TutorFlow` (private) |
| Исходный commit аудита | `43ce8a4` — Merge verified auth and student lifecycle into main |
| Issue | [#4](https://github.com/esnstwa/TutorFlow/issues/4) |
| Ветка | `codex/mdk-pz01-quality-gate` |
| Commit изменения | `0fb9fd9` — основной комплект; `6a5f0cd`, `032f718` — исправления CI по результатам реальных runs |
| PR | [#5 — docs: подготовить ПЗ №1 и Quality Gate v0](https://github.com/esnstwa/TutorFlow/pull/5) |
| Pipeline | [Quality Gate run 37936284338](https://github.com/esnstwa/TutorFlow/actions/runs/37936284338) — `success`, commit `032f718` |
| Независимый review | Запрошен у `@iver-ks` в PR #5; TODO(external), авторское self-review не засчитывается |
| Tag | TODO: `0302-pz01-v1` только после внешних обязательных пунктов и merge |
| Оппонирование | `PENDING OPPOSITION`, см. `OPPOSITION.md` |

## Материалы

- устав, discovery, требования 1.0 и MVP;
- регламент процесса, DoD, Quality Gate v0 и Security Baseline;
- шаблон оппонирования и индивидуального отчёта;
- GitHub issue/PR templates, CODEOWNERS, CI workflow;
- исходный код, Alembic migrations и автоматизированные тесты TutorFlow.

## Проверки

Проверено локально 2026-10-09 до фиксации commit:

- `python -m compileall -q app` — успешно;
- `python -m pytest -q` — `184 passed` (два предупреждения об устаревшем API);
- Node.js — `40 passed` в трёх существующих наборах тестов;
- `docker compose config --quiet` — успешно;
- Alembic на новой изолированной PostgreSQL 16: `upgrade head`, единственный head `d2b3c4d5e6f7`, `current` и `check` — успешно, новых операций не найдено;
- `git diff --check` и разбор пяти YAML-файлов — успешно.

GitHub Actions Quality Gate на commit `032f718` завершился успешно: compile, `184` Python-теста, `40` JavaScript-тестов и миграции на PostgreSQL 16 прошли. Два предыдущих run честно сохранены в истории: первый обнаружил недопустимый контекст пути до запуска job, второй — влияние `APP_ENV=test` на security-тест cookie; обе причины исправлены отдельными commit. Старый локальный Docker-том основного проекта содержит отсутствующую в репозитории ревизию `20260916_0002`; том не изменялся, а локальная проверка миграций выполнена на чистом изолированном томе.

## Вывод

Техническая часть ПЗ подготовлена на основе реального репозитория. Полная сдача невозможна без заполнения данных студента, подтверждения discovery заказчиком, независимого оппонирования и независимого review значимого PR.

## Вклад участников

- `TODO(student)`: ФИО, группа, конкретные файлы/решения/проверки и затраченное время.
- `TODO(teammate)`: подтверждённый вклад другого участника, если был.
- AI-инструмент: использован для аудита/черновика/проверок; студент обязан проверить содержание и уметь защитить решения.
