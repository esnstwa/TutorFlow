# Реестр доказательств ПЗ №2 — расписание

**Срез remote-доказательств:** PR №16 на HEAD `ddf4b0258bcd2b9487d44cf06fe02a4da86da12a`; Ксения (`iver-ks`) одобрила этот SHA, `verify` завершился успешно, а GitHub показывал `REVIEW_REQUIRED`/`BLOCKED`; на этом срезе merge и тег отсутствовали. Локальные PostgreSQL/Alembic-проверки и тесты остаются отдельными от CI и от результатов, сообщённых проверяющей. Эта запись фиксирует именно указанный SHA; проверка последующего SHA отражается отдельно.

## Срез репозитория

- Ветка: `feature/0104-pz02-artem`.
- Базовый commit ветки и состояние `origin/main` на момент начала работы: `3a3f23e2743b4798b9402fa3cc7c298c3a9d834c`; изменения ПЗ №2 сделаны поверх него.
- Известный commit PR #9 входит в базовую историю (проверено `git merge-base --is-ancestor 35dd02dd3a42aad12f918f92870dbd24e80c1dca HEAD`).
- Первоначальная запись об отсутствии push и PR относится к локальному срезу до публикации; remote-состояние для проверенного SHA отражено ниже. Merge и тег на момент этого среза отсутствовали.
- Отчёт ПЗ №1 не редактировался. SHA-256 при проверке — `73d0831012bf93a1644352e4153216be68225648b35ba625323997efe52e02e6`; значение совпадает с ранее сохранённой проверкой.

## Фактические проверки

**Папка доказательств:** локальный каталог `TutorFlow-PZ02-Submission/` вне репозитория; пути `evidence/...` и `qa/...` ниже относительны к нему.

| Проверка | Фактический результат | Доказательство и границы |
|---|---|---|
| Новый контракт и SQLAlchemy-источник | 11 passed, exit 0 | `evidence/focused-calendar-pytest.log`; повтор после уточнения границ autoflush — `evidence/focused-calendar-final-docs.log`. Новый повтор 19.10.2026 с `DATABASE_URL` на изолированную PostgreSQL 16 — `evidence/focused-calendar-postgres-env-20261019.log`; сами calendar_db fixtures остаются SQLite, поэтому этот прогон не является PostgreSQL integration suite. Не проверялись production-auth и нагрузочная производительность. |
| Нет неявного autoflush при `autoflush=True` | 2 passed, exit 0; оба метода оставляют pending `Lesson` в `Session.new` | `evidence/autoflush-regression-green.log`; проверен только implicit flush в этих вызовах, не явный `flush` или произвольные побочные эффекты serializer. Адаптер сам не вызывает `flush`/`commit`/`rollback`/`close`. |
| Воспроизводимый сценарий с обеими реализациями | 1 passed, 0.08 s, exit 0 | `evidence/candidate-repro-pz02.log`; `test_shared_consumer_returns_same_calendar_for_both_sources`. |
| Совместимость ответа с базовым `calendar_events` | Точное равенство словарей во всех 5 сценариях | `qa/calendar-legacy-compat.log`; старая функция исполнена из `HEAD:app/services.py`, fixture SQLite; охвачены выборка без диапазона, включительная дата, следующий день, обратный диапазон и диапазон без уроков. Это локальная дифференциальная проверка, не отдельный постоянный pytest-тест. |
| Новые календарные тесты вместе с расписательной регрессией | 47 passed, 1 `StarletteDeprecationWarning`, exit 0 | `evidence/schedule-module-regression.log`; локальный запуск Python 3.14.7 на Windows. |
| Полный Python-набор | 296 passed, 1 `StarletteDeprecationWarning`, 46.55 s, exit 0 | Новый повтор 19.10.2026 с `DATABASE_URL` на изолированную PostgreSQL 16 — `evidence/full-pytest-postgres-env-20261019.log`; прежние логи: `evidence/full-pytest.log`, `evidence/full-pytest-final-docs.log`. Локально, не CI; не утверждается, что каждый тест обращался к PostgreSQL. |
| Отчёт ПЗ2 DOCX/PDF | DOCX package validator `ok`; финальный PDF — 15 страниц; статическое содержание совпадает с фактическими страницами; 6 подлинных снимков, рисунок 6 не создан; отчёт остаётся черновиком | `qa/docx-validate-final-mapcombined4.log`, `qa/report-verify-final-mapcombined4.log`, `qa/report-analyze-final-mapcombined4.log`, `qa/report-render-final-mapcombined4.log`, `qa/report-toc-mapcombined4.log`, `qa/report-content-check-final-mapcombined4.log`; визуально проверены страницы 1, 2, 7, 10, 12, 13 и 15. Предыдущая версия сохранена в `qa/Individual_Report_PZ02_pre-postgres-recheck_20261019.docx`. |
| Расписательная регрессия с coverage | 36 passed, 1 предупреждение, 3.52 s, exit 0 | `qa/schedule-coverage-final-pytest.log`. Coverage: 44% суммарно для `app.services` + `app.web.router` (62% и 38%); это результат измерения, а не заявленный порог. |
| JavaScript: auth/lifecycle | 34 passed, 0 failed, exit 0 | `evidence/node-test.log`. |
| JavaScript: session fetch | 6 проверок passed, exit 0 | `evidence/node-session-fetch.log`. |
| `python -m compileall -q app` | exit 0 | `evidence/compileall-pz02.log`. |
| Проверка минимального компонента | PASS, version `0.1.0`, SHA `3a3f23e2743b-dirty`; valid config exit 0, invalid config exit 2 | `qa/component-check.log`. |
| Отрицательная проверка SHA компонента | Ожидаемый отказ при `000000000000`, exit 1 | `qa/component-check-negative.log`; это проверка отрицательной ветки. |
| Wheel и runtime из установленного пакета | Сборка exit 0; runtime PASS, `health=200`, `static=200`, `css_bytes=23418`, `import=installed-wheel` | `evidence/wheel-build-final.log`, `evidence/wheel-runtime-final.log`. Изолированный staging содержит временный `app/build-info.json` со значением `3a3f23e2743b-dirty`; в рабочее дерево он не добавлялся. Wheel собран после autoflush-фикса: `qa/wheel-local-20261019-autoflush/tutorflow-0.1.0-py3-none-any.whl`. |
| PostgreSQL/Alembic (`upgrade`, `heads`, `current`, `check`) | PASS, exit 0 | Локально на новом disposable `postgres:16` контейнере с tmpfs и отдельной `tutorflow_test`: `uv run --locked --no-sync python -m alembic upgrade head`; ровно одна head `d2b3c4d5e6f7`; `alembic current` на той же head; `alembic check` — `No new upgrade operations detected.` Лог: `evidence/postgres-alembic-recheck-20261019.log`. Это локальная проверка, не GitHub CI. |
| Calendar SQLAlchemy source на PostgreSQL | PASS, exit 0; транзакция откачена, после rollback тестовых строк 0 | Rollback-only smoke на изолированной PostgreSQL 16 проверил два урока (scheduled/cancelled), исключение следующего дня, одно review-событие, детали и timezone. Лог: `evidence/postgres-calendar-smoke-20261019.log`. Не является полной PostgreSQL parity или конкурентным тестом. |
| CI Quality Gate для изменений ПЗ №2 | `verify` — success на точном HEAD `ddf4b0258bcd2b9487d44cf06fe02a4da86da12a`; run `39346524300`, завершён 20.10.2026 00:16:14 UTC | GitHub Actions, job `118380346002`. Это CI; локальные тесты и PostgreSQL-проверки в таблице выше остаются отдельными результатами. PR после этого run всё ещё заблокирован из-за `REVIEW_REQUIRED`. |
| Независимое review Р7 | Ксения (`iver-ks`) — `APPROVED` на точном HEAD `ddf4b0258bcd2b9487d44cf06fe02a4da86da12a`, review `5579348082`; сообщает об отсутствии конфликтов, незакрытых review conversations и существенных замечаний | В предыдущем review она сообщила о 47 расписательных тестах, 24 auth-регрессионных тестах, `compileall` и `git diff --check`; точные локальные команды/stdout не приложены. Р7 частично документирован, рисунок 6 отсутствует; эти границы сохранены в `REVIEW_PROTOCOL.md`. |

## Подлинные снимки отчёта

Подлинные снимки сделаны в VS Code; рисунок 4а — прямой кроп исходного скриншота для читаемости, полный screenshot сохранён отдельно. Синтетическая подмена содержимого не выполнялась.

| Рисунок | Файл | Подтверждаемое содержимое |
|---|---|---|
| 1 | `evidence/figure-01-contract-implementation.png` | Контракт, описание ошибок и фрагмент реализации `CalendarEventService`. |
| 2 | `evidence/figure-02-docstring-contract.png` | Docstring публичной операции: пример, входы и результат; совместно с рисунком 1 показывает контракт. |
| 3 | `evidence/figure-03-substitution-same-consumer.png` | SQLAlchemy- и in-memory-источники переданы одному `CalendarEventService`; тест сравнивает результат. |
| 4а | `evidence/figure-04a-calendar-branch-detail.png` (кроп); полный снимок — `evidence/figure-04a-map-source-window.png` | Подлинный фрагмент графа VS Code: `app.services`, `app.schedule.sqlalchemy_source`, `app.schedule.calendar`, `app.models` и связи между ними; полный снимок сохранён для контекста. |
| 4б | `evidence/figure-04c-module-map-planned.png` | Реестр, календарные зависимости, статусы «работает/план» и автор записей. |
| 5 | `evidence/figure-05-calendar-test-results-final.png` | Подлинный снимок VS Code с фактическим focused pytest после autoflush-фикса: 11 passed, exit 0. |
| 6 | — | Не представлен: взаимная проверка не состоялась; изображение не создавалось. |

## Статусы критериев на локальном срезе

- **Р1 — выполнено локально:** цепочка FR-07 → ответственность → операция → два существующих потребителя; внешние обязанности отделены.
- **Р2 — выполнено локально:** контракт и docstring описывают вход, результат, ошибки/порядок чтения, владение, побочные эффекты и пример.
- **Р3 — частично:** модуль реализован и интегрирован; на проверенном SHA PR №16 был открыт, `verify` прошёл, но merge блокировался `REVIEW_REQUIRED`; тега сдачи на этом срезе не было.
- **Р4 — выполнено локально:** две реализации вызываются тем же неизменённым потребителем; ограничения in-memory/SQLite указаны.
- **Р5 — выполнено локально:** карта сверена с импортами выделенного участка; план отделён от работающих компонентов.
- **Р6 — выполнено в локальном объёме:** штатные, граничные, ошибочные сценарии и отсутствие неявного autoflush в проверенных вызовах подтверждены; это не запрет явного `flush`. PostgreSQL/Alembic migration checks и rollback-only calendar smoke прошли локально; отдельный CI `verify` прошёл на указанном PR HEAD, но не подтверждает последующие SHA.
- **Р7 — частично документировано:** имеется независимое `APPROVED` Ксении на точном HEAD и сводка фактических результатов; точные локальные выводы и рисунок 6 отсутствуют, поэтому Р7 полностью не закрыт.
- **Р8 — подготовлено:** два направления сложности, вопросы и готовность описаны; воспроизводимый кандидат и авторский ADR представлены. Нагрузочные измерения не проводились.

## Неизвестные данные и открытые границы

- Студент — Исаков Артём, группа С324. Номер кафедры, преподаватель и подпись не подтверждены доступными данными и не должны выдумываться.
- Тег сдачи не создан; локальная ветка без тега не является неизменяемой версией сдачи.
- Семантика пересечения, влияние `cancelled`, касание границ и гарантия при конкурентных изменениях не вводились. В коде и локальном контексте они имеют ограничения/неоднозначность, изложенные в индивидуальном ADR; решение владельца требования требуется отдельно.
- Локальные PostgreSQL migration checks и rollback-only calendar smoke завершились успешно; CI `verify` прошёл на SHA `ddf4b0258bcd2b9487d44cf06fe02a4da86da12a`; независимое review Ксении зафиксировано, но Р7 остаётся частично документированным из-за отсутствия точных локальных выводов и рисунка 6. Нагрузочное измерение не выполнялось.
